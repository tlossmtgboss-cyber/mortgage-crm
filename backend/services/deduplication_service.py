"""
Contact & Lead Deduplication Service

Centralized duplicate detection and merge logic for the CRM.
Leads function as the primary contact entity; this service finds
duplicates by normalized email and phone within an organization,
and provides merge capability that reassigns child records.

Includes confidence scoring and automatic merging for high-confidence
duplicate pairs (e.g., exact email + phone match = 1.0 confidence).

Usage:
    from services.deduplication_service import (
        find_duplicate_contacts,
        find_duplicate_leads,
        merge_contacts,
        get_dedup_report,
        confidence_score,
        auto_merge_high_confidence,
    )
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import List

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from services.audit_events import audit_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

_PHONE_STRIP_RE = re.compile(r"[^0-9]")


def normalize_phone(phone: str) -> str:
    """Strip formatting and normalize to E.164-like (digits only, prepend 1 for US 10-digit)."""
    if not phone:
        return ""
    digits = _PHONE_STRIP_RE.sub("", phone)
    if not digits:
        return ""
    # US numbers: if 10 digits, prepend country code 1
    if len(digits) == 10:
        digits = "1" + digits
    # If already 11 digits starting with 1, keep as-is
    # Return with + prefix for E.164
    return "+" + digits


def normalize_email(email: str) -> str:
    """Lowercase and strip whitespace."""
    if not email:
        return ""
    return email.strip().lower()


# ---------------------------------------------------------------------------
# Duplicate detection — leads (contacts)
# ---------------------------------------------------------------------------

def _get_lead_model():
    """Lazy import to avoid circular imports at module load time."""
    from database.models.lead_loan import Lead
    return Lead


def find_duplicate_contacts(db: Session, org_id: int) -> List[dict]:
    """Find contacts (leads) with the same email or normalized phone within an org.

    Returns a list of duplicate groups, each containing:
      - match_field: "email" or "phone"
      - match_value: the normalized value they share
      - records: list of lead summaries in the group
    """
    Lead = _get_lead_model()
    groups: List[dict] = []

    # --- Email duplicates ---
    # Find emails that appear more than once (non-null, non-empty)
    email_subq = (
        db.query(
            func.lower(func.trim(Lead.email)).label("norm_email"),
            func.count(Lead.id).label("cnt"),
        )
        .filter(
            Lead.organization_id == org_id,
            Lead.deleted_at.is_(None),
            Lead.email.isnot(None),
            Lead.email != "",
        )
        .group_by(func.lower(func.trim(Lead.email)))
        .having(func.count(Lead.id) > 1)
        .subquery()
    )

    dup_email_leads = (
        db.query(Lead)
        .join(email_subq, func.lower(func.trim(Lead.email)) == email_subq.c.norm_email)
        .filter(
            Lead.organization_id == org_id,
            Lead.deleted_at.is_(None),
        )
        .order_by(func.lower(func.trim(Lead.email)), Lead.created_at)
        .all()
    )

    email_groups: dict = defaultdict(list)
    for lead in dup_email_leads:
        key = normalize_email(lead.email)
        email_groups[key].append(lead)

    for email_val, leads in email_groups.items():
        groups.append({
            "match_field": "email",
            "match_value": email_val,
            "records": [_lead_summary(l) for l in leads],
        })

    # --- Phone duplicates ---
    # Pull all leads with a phone, normalize in Python, then group
    leads_with_phone = (
        db.query(Lead)
        .filter(
            Lead.organization_id == org_id,
            Lead.deleted_at.is_(None),
            Lead.phone.isnot(None),
            Lead.phone != "",
        )
        .order_by(Lead.created_at)
        .all()
    )

    phone_groups: dict = defaultdict(list)
    for lead in leads_with_phone:
        norm = normalize_phone(lead.phone)
        if norm:
            phone_groups[norm].append(lead)

    # Only keep groups with duplicates, and exclude leads already matched by email
    email_matched_ids = {l.id for leads in email_groups.values() for l in leads}
    for phone_val, leads in phone_groups.items():
        if len(leads) < 2:
            continue
        # If every lead in this phone group is already fully covered by
        # an email group, skip to avoid redundant reporting.
        lead_ids_in_group = {l.id for l in leads}
        if lead_ids_in_group.issubset(email_matched_ids):
            continue
        groups.append({
            "match_field": "phone",
            "match_value": phone_val,
            "records": [_lead_summary(l) for l in leads],
        })

    return groups


def find_duplicate_leads(db: Session, org_id: int) -> List[dict]:
    """Alias — in this CRM, leads ARE the contact entity."""
    return find_duplicate_contacts(db, org_id)


def _lead_summary(lead) -> dict:
    """Build a JSON-safe summary of a lead for duplicate display."""
    return {
        "id": lead.id,
        "name": lead.name,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "email": lead.email,
        "phone": lead.phone,
        "stage": lead.stage,
        "source": lead.source,
        "owner_id": lead.owner_id,
        "ai_score": lead.ai_score,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
        "last_contact": lead.last_contact.isoformat() if lead.last_contact else None,
    }


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

# Tables with a lead_id FK that should be reassigned during merge.
# Each entry: (table_name, column_name)
# We use raw SQL UPDATE for safety — avoids loading entire ORM graphs.
_REASSIGN_TABLES = [
    ("activities", "lead_id"),
    ("ai_tasks", "lead_id"),
    ("tasks", "lead_id"),
    ("stage_history", "lead_id"),
    ("client_files", "lead_id"),
    ("sms_conversations", "lead_id"),
    ("drip_enrollments", "lead_id"),
    ("call_authorizations", "lead_id"),
]


def merge_contacts(
    db: Session,
    org_id: int,
    primary_id: int,
    duplicate_ids: List[int],
) -> dict:
    """Merge duplicate leads into a primary record.

    Steps:
      1. Validate all IDs belong to the same org and exist.
      2. Reassign child records (tasks, activities, etc.) to the primary.
      3. Fill empty fields on primary from duplicates (most-complete-wins).
      4. Soft-delete duplicates (set deleted_at).
      5. Return summary of what was merged.

    Args:
        db: SQLAlchemy session (must be inside an active transaction).
        org_id: Organization ID for tenant isolation.
        primary_id: The lead ID to keep.
        duplicate_ids: Lead IDs to merge into primary and then soft-delete.

    Returns:
        dict with merge summary.
    """
    Lead = _get_lead_model()

    if primary_id in duplicate_ids:
        raise ValueError("primary_id must not be in duplicate_ids")
    if not duplicate_ids:
        raise ValueError("duplicate_ids must not be empty")

    all_ids = [primary_id] + list(duplicate_ids)

    # 1. Load and validate
    leads = (
        db.query(Lead)
        .filter(
            Lead.id.in_(all_ids),
            Lead.organization_id == org_id,
            Lead.deleted_at.is_(None),
        )
        .all()
    )
    found_ids = {l.id for l in leads}
    missing = set(all_ids) - found_ids
    if missing:
        raise ValueError(f"Lead IDs not found or not in org {org_id}: {missing}")

    primary = next(l for l in leads if l.id == primary_id)
    duplicates = [l for l in leads if l.id != primary_id]

    # 2. Reassign child records via parameterized SQL
    reassigned_counts: dict = {}
    for table_name, col_name in _REASSIGN_TABLES:
        try:
            # Build parameterized IN clause: :d0, :d1, ...
            placeholders = ", ".join(f":d{i}" for i in range(len(duplicate_ids)))
            params = {f"d{i}": did for i, did in enumerate(duplicate_ids)}
            params["primary_id"] = primary_id
            result = db.execute(
                text(
                    f"UPDATE {table_name} SET {col_name} = :primary_id "
                    f"WHERE {col_name} IN ({placeholders})"
                ),
                params,
            )
            reassigned_counts[table_name] = result.rowcount
        except Exception as e:
            # Table may not exist yet (some are created lazily).
            logger.debug("Skipping reassign for %s: %s", table_name, e)
            reassigned_counts[table_name] = 0

    # 3. Fill empty fields on primary from duplicates (first non-empty wins)
    _MERGE_FIELDS = [
        "first_name", "last_name", "email", "phone",
        "source", "credit_score", "annual_income", "loan_type",
        "preapproval_amount", "loan_amount", "interest_rate",
        "employer_name", "industry", "employment_status",
        "address", "city", "state", "zip_code",
        "property_type", "property_value", "down_payment",
        "co_applicant_name", "co_applicant_email", "co_applicant_phone",
        "preferred_communication", "notes",
    ]
    fields_filled = []
    for field in _MERGE_FIELDS:
        current_val = getattr(primary, field, None)
        if current_val is not None and str(current_val).strip():
            continue
        for dup in duplicates:
            dup_val = getattr(dup, field, None)
            if dup_val is not None and str(dup_val).strip():
                setattr(primary, field, dup_val)
                fields_filled.append(field)
                break

    # Keep the best AI score (highest)
    best_score = primary.ai_score or 0
    for dup in duplicates:
        if (dup.ai_score or 0) > best_score:
            best_score = dup.ai_score
    if best_score != (primary.ai_score or 0):
        primary.ai_score = best_score
        fields_filled.append("ai_score")

    # Keep the earliest created_at
    earliest = primary.created_at
    for dup in duplicates:
        if dup.created_at and (earliest is None or dup.created_at < earliest):
            earliest = dup.created_at
    if earliest and earliest != primary.created_at:
        primary.created_at = earliest
        fields_filled.append("created_at")

    # Keep the most recent last_contact
    latest_contact = primary.last_contact
    for dup in duplicates:
        if dup.last_contact and (latest_contact is None or dup.last_contact > latest_contact):
            latest_contact = dup.last_contact
    if latest_contact and latest_contact != primary.last_contact:
        primary.last_contact = latest_contact
        fields_filled.append("last_contact")

    primary.updated_at = datetime.now(timezone.utc)

    # 4. Soft-delete duplicates
    now = datetime.now(timezone.utc)
    for dup in duplicates:
        dup.deleted_at = now
        # Append merge note
        merge_note = f"[MERGED into lead #{primary_id} at {now.isoformat()}]"
        if dup.notes:
            dup.notes = merge_note + "\n" + dup.notes
        else:
            dup.notes = merge_note

    db.flush()

    # 5. Audit trail — log merge details for compliance / undo support
    total_reassigned = sum(reassigned_counts.values())
    try:
        audit_event(
            db,
            event_type="CONTACT_MERGE",
            resource_type="lead",
            resource_id=str(primary_id),
            org_id=org_id,
            metadata={
                "primary_id": primary_id,
                "duplicate_ids": list(duplicate_ids),
                "fields_updated": fields_filled,
                "child_records_reassigned": total_reassigned,
                "reassigned_by_table": reassigned_counts,
                "duplicates_soft_deleted": len(duplicates),
            },
        )
    except Exception as e:
        # Audit failure must never break the merge itself
        logger.warning("Failed to write merge audit event: %s", e)

    return {
        "primary_id": primary_id,
        "merged_ids": duplicate_ids,
        "reassigned_records": reassigned_counts,
        "fields_filled_from_duplicates": fields_filled,
        "duplicates_soft_deleted": len(duplicates),
    }


# ---------------------------------------------------------------------------
# Report / summary
# ---------------------------------------------------------------------------

def get_dedup_report(db: Session, org_id: int) -> dict:
    """Summary stats for data quality dashboard.

    Returns:
        dict with total_contacts, duplicate_groups, duplicates_count, duplicate_rate.
    """
    Lead = _get_lead_model()

    # Total active leads (contacts) in org
    total = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.organization_id == org_id,
            Lead.deleted_at.is_(None),
        )
        .scalar()
    ) or 0

    # Run dedup detection
    groups = find_duplicate_contacts(db, org_id)

    # Count unique leads involved in at least one duplicate group
    dup_lead_ids: set = set()
    for g in groups:
        for rec in g["records"]:
            dup_lead_ids.add(rec["id"])

    duplicates_count = len(dup_lead_ids)
    duplicate_rate = round(duplicates_count / total, 4) if total > 0 else 0.0

    return {
        "organization_id": org_id,
        "total_contacts": total,
        "duplicate_groups": len(groups),
        "duplicates_count": duplicates_count,
        "duplicate_rate": duplicate_rate,
        "groups": groups,
    }


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def confidence_score(lead_a, lead_b) -> float:
    """Score the likelihood that two leads are duplicates (0.0 to 1.0).

    Scoring matrix:
      - Exact email + exact phone match:        1.0
      - Exact email + exact name match:          0.95
      - Exact email only:                        0.8
      - Exact phone + exact name match:          0.75
      - Exact phone only:                        0.6
      - Exact first_name + last_name match only: 0.3

    All comparisons are normalized (lowercased/stripped email, digits-only phone).
    Returns 0.0 if no meaningful match is found.
    """
    email_a = normalize_email(getattr(lead_a, "email", None) or "")
    email_b = normalize_email(getattr(lead_b, "email", None) or "")
    phone_a = normalize_phone(getattr(lead_a, "phone", None) or "")
    phone_b = normalize_phone(getattr(lead_b, "phone", None) or "")

    first_a = (getattr(lead_a, "first_name", None) or "").strip().lower()
    first_b = (getattr(lead_b, "first_name", None) or "").strip().lower()
    last_a = (getattr(lead_a, "last_name", None) or "").strip().lower()
    last_b = (getattr(lead_b, "last_name", None) or "").strip().lower()

    email_match = bool(email_a and email_b and email_a == email_b)
    phone_match = bool(phone_a and phone_b and phone_a == phone_b)
    name_match = bool(first_a and first_b and last_a and last_b
                      and first_a == first_b and last_a == last_b)

    if email_match and phone_match:
        return 1.0
    if email_match and name_match:
        return 0.95
    if email_match:
        return 0.8
    if phone_match and name_match:
        return 0.75
    if phone_match:
        return 0.6
    if name_match:
        return 0.3
    return 0.0


# ---------------------------------------------------------------------------
# Auto-merge high-confidence duplicates
# ---------------------------------------------------------------------------

def auto_merge_high_confidence(
    db: Session,
    org_id: int,
    threshold: float = 0.95,
    dry_run: bool = False,
) -> dict:
    """Automatically merge duplicate pairs whose confidence_score >= threshold.

    For each duplicate group detected by find_duplicate_contacts():
      1. Score every pair within the group.
      2. If any pair scores >= threshold, merge the newer record (by created_at)
         INTO the older one.
      3. Continue until no more high-confidence pairs remain in the group.

    Args:
        db: SQLAlchemy session (caller must commit/rollback).
        org_id: Organization ID for tenant isolation.
        threshold: Minimum confidence to auto-merge (default 0.95).
        dry_run: If True, return what would be merged without actually merging.

    Returns:
        {
            "merged_pairs": [
                {"primary_id": int, "duplicate_id": int, "confidence": float}
            ],
            "total_merged": int,
            "threshold": float,
            "dry_run": bool,
        }
    """
    Lead = _get_lead_model()

    if threshold < 0.8:
        raise ValueError("Auto-merge threshold must be >= 0.8 to prevent false positives")

    groups = find_duplicate_contacts(db, org_id)
    merged_pairs: List[dict] = []
    already_merged: set = set()  # Track IDs already consumed as duplicates

    for group in groups:
        record_ids = [rec["id"] for rec in group["records"]]
        if len(record_ids) < 2:
            continue

        # Load actual ORM objects for scoring
        leads = (
            db.query(Lead)
            .filter(
                Lead.id.in_(record_ids),
                Lead.organization_id == org_id,
                Lead.deleted_at.is_(None),
            )
            .order_by(Lead.created_at.asc())
            .all()
        )

        # Compare all pairs within the group
        for i in range(len(leads)):
            if leads[i].id in already_merged:
                continue
            for j in range(i + 1, len(leads)):
                if leads[j].id in already_merged:
                    continue

                score = confidence_score(leads[i], leads[j])
                if score < threshold:
                    continue

                # Older record (leads[i]) is primary, newer (leads[j]) is duplicate
                primary = leads[i]
                duplicate = leads[j]

                pair_info = {
                    "primary_id": primary.id,
                    "duplicate_id": duplicate.id,
                    "confidence": score,
                }

                if not dry_run:
                    try:
                        merge_contacts(
                            db=db,
                            org_id=org_id,
                            primary_id=primary.id,
                            duplicate_ids=[duplicate.id],
                        )
                        already_merged.add(duplicate.id)
                        pair_info["status"] = "merged"
                    except Exception as e:
                        logger.error(
                            "Auto-merge failed for %d <- %d: %s",
                            primary.id, duplicate.id, e,
                        )
                        pair_info["status"] = "error"
                        pair_info["error"] = str(e)
                else:
                    already_merged.add(duplicate.id)
                    pair_info["status"] = "would_merge"

                merged_pairs.append(pair_info)

    # Audit trail for auto-merge batch
    if merged_pairs and not dry_run:
        try:
            audit_event(
                db,
                event_type="AUTO_MERGE_BATCH",
                resource_type="lead",
                resource_id=str(org_id),
                org_id=org_id,
                metadata={
                    "threshold": threshold,
                    "pairs_merged": len([p for p in merged_pairs if p.get("status") == "merged"]),
                    "pairs_failed": len([p for p in merged_pairs if p.get("status") == "error"]),
                },
            )
        except Exception as e:
            logger.warning("Failed to write auto-merge audit event: %s", e)

    return {
        "merged_pairs": merged_pairs,
        "total_merged": len([p for p in merged_pairs if p.get("status") in ("merged", "would_merge")]),
        "threshold": threshold,
        "dry_run": dry_run,
    }
