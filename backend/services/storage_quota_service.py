"""
Storage Quota Enforcement Service — MTR-004

Hard storage quota enforcement per organization:
- Tracks cumulative storage usage per tenant
- Rejects uploads when quota exceeded
- Provides usage queries for dashboard
"""
import logging
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Default storage quotas per subscription tier (in bytes)
TIER_STORAGE_QUOTAS = {
    "lead_management": 5 * 1024 * 1024 * 1024,      # 5 GB
    "lead_and_active": 25 * 1024 * 1024 * 1024,      # 25 GB
    "full_pipeline": 100 * 1024 * 1024 * 1024,        # 100 GB
    "trial": 1 * 1024 * 1024 * 1024,                  # 1 GB
    "default": 5 * 1024 * 1024 * 1024,                # 5 GB
}


def get_org_storage_quota(db: Session, org_id: int) -> int:
    """Get storage quota for organization based on subscription tier."""
    row = db.execute(text("""
        SELECT tier FROM organization_subscriptions
        WHERE organization_id = :org_id AND status IN ('active', 'trial')
        ORDER BY created_at DESC LIMIT 1
    """), {"org_id": org_id}).fetchone()

    tier = row[0] if row else "default"
    return TIER_STORAGE_QUOTAS.get(tier, TIER_STORAGE_QUOTAS["default"])


def get_org_storage_used(db: Session, org_id: int) -> int:
    """Get current storage used by organization (sum of all document sizes)."""
    row = db.execute(text("""
        SELECT COALESCE(SUM(file_size_bytes), 0)
        FROM tenant_storage_usage
        WHERE organization_id = :org_id AND is_deleted = false
    """), {"org_id": org_id}).fetchone()
    return int(row[0]) if row else 0


def check_storage_quota(db: Session, org_id: int, file_size_bytes: int) -> Tuple[bool, Dict]:
    """
    Check if an upload would exceed the organization's storage quota.

    Returns:
        (allowed: bool, details: dict)
    """
    quota = get_org_storage_quota(db, org_id)
    used = get_org_storage_used(db, org_id)
    remaining = quota - used
    would_use = used + file_size_bytes

    allowed = would_use <= quota

    details = {
        "quota_bytes": quota,
        "quota_gb": round(quota / (1024 ** 3), 2),
        "used_bytes": used,
        "used_gb": round(used / (1024 ** 3), 2),
        "remaining_bytes": max(remaining, 0),
        "remaining_gb": round(max(remaining, 0) / (1024 ** 3), 2),
        "file_size_bytes": file_size_bytes,
        "would_use_bytes": would_use,
        "usage_pct": round((used / quota) * 100, 1) if quota > 0 else 0,
        "allowed": allowed,
    }

    if not allowed:
        details["error"] = (
            f"Storage quota exceeded. Used {details['used_gb']} GB of {details['quota_gb']} GB. "
            f"Upload of {round(file_size_bytes / (1024 ** 2), 1)} MB would exceed quota by "
            f"{round((would_use - quota) / (1024 ** 2), 1)} MB."
        )
        logger.warning(f"Storage quota exceeded for org {org_id}: {details['used_gb']}GB / {details['quota_gb']}GB")

    return allowed, details


def record_storage_usage(db: Session, org_id: int, storage_key: str,
                         file_size_bytes: int, file_type: str = "document",
                         uploaded_by_id: Optional[int] = None):
    """Record a new file upload in storage tracking."""
    db.execute(text("""
        INSERT INTO tenant_storage_usage
            (organization_id, storage_key, file_size_bytes, file_type,
             uploaded_by_id, is_deleted, created_at)
        VALUES
            (:org_id, :key, :size, :ftype, :user_id, false, NOW())
        ON CONFLICT (storage_key) DO UPDATE SET
            file_size_bytes = EXCLUDED.file_size_bytes,
            is_deleted = false
    """), {
        "org_id": org_id, "key": storage_key,
        "size": file_size_bytes, "ftype": file_type,
        "user_id": uploaded_by_id,
    })


def mark_storage_deleted(db: Session, storage_key: str):
    """Mark a file as deleted in storage tracking."""
    db.execute(text("""
        UPDATE tenant_storage_usage SET is_deleted = true WHERE storage_key = :key
    """), {"key": storage_key})


def get_storage_summary(db: Session, org_id: int) -> Dict:
    """Get storage usage summary for organization."""
    quota = get_org_storage_quota(db, org_id)
    used = get_org_storage_used(db, org_id)

    # Breakdown by file type
    breakdown = db.execute(text("""
        SELECT file_type, COUNT(*) as file_count, COALESCE(SUM(file_size_bytes), 0) as total_bytes
        FROM tenant_storage_usage
        WHERE organization_id = :org_id AND is_deleted = false
        GROUP BY file_type
        ORDER BY total_bytes DESC
    """), {"org_id": org_id}).fetchall()

    return {
        "quota_bytes": quota,
        "quota_gb": round(quota / (1024 ** 3), 2),
        "used_bytes": used,
        "used_gb": round(used / (1024 ** 3), 2),
        "remaining_bytes": max(quota - used, 0),
        "remaining_gb": round(max(quota - used, 0) / (1024 ** 3), 2),
        "usage_pct": round((used / quota) * 100, 1) if quota > 0 else 0,
        "breakdown": [
            {
                "file_type": r[0],
                "file_count": r[1],
                "total_bytes": int(r[2]),
                "total_gb": round(int(r[2]) / (1024 ** 3), 3),
            }
            for r in breakdown
        ],
    }
