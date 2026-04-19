"""Sliding-window rate limit for upload endpoints."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import text

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

UPLOADS_PER_HOUR_PER_USER = 100
BYTES_PER_HOUR_PER_USER = 5 * 1024 * 1024 * 1024  # 5 GB
UPLOADS_PER_HOUR_PER_ORG = 2_000


class UploadRateLimiter:
    def __init__(self, db, user):
        self.db = db
        self.user = user

    def check(self, incoming_bytes: int = 0) -> None:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=1)
        user_id = getattr(self.user, 'id', None)
        org_id = getattr(self.user, 'organization_id', None)

        if not user_id:
            return

        row = self.db.execute(
            text(
                "SELECT COUNT(*) AS cnt, COALESCE(SUM(bytes_uploaded), 0) AS total_bytes "
                "FROM upload_rate_events "
                "WHERE user_id = :uid AND occurred_at >= :since"
            ),
            {"uid": user_id, "since": window_start},
        ).mappings().one()

        if row["cnt"] >= UPLOADS_PER_HOUR_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Upload rate limit exceeded (per-user hourly count)",
                headers={"Retry-After": "3600"},
            )
        if row["total_bytes"] + incoming_bytes > BYTES_PER_HOUR_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Upload rate limit exceeded (per-user hourly bytes)",
                headers={"Retry-After": "3600"},
            )

        if org_id:
            org_cnt = self.db.execute(
                text(
                    "SELECT COUNT(*) FROM upload_rate_events "
                    "WHERE organization_id = :oid AND occurred_at >= :since"
                ),
                {"oid": org_id, "since": window_start},
            ).scalar()
            if org_cnt >= UPLOADS_PER_HOUR_PER_ORG:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Upload rate limit exceeded (per-org hourly count)",
                    headers={"Retry-After": "3600"},
                )

    def record(self, bytes_uploaded: int) -> None:
        user_id = getattr(self.user, 'id', None)
        org_id = getattr(self.user, 'organization_id', None)
        if not user_id:
            return
        try:
            self.db.execute(
                text(
                    "INSERT INTO upload_rate_events "
                    "(user_id, organization_id, bytes_uploaded) "
                    "VALUES (:uid, :oid, :b)"
                ),
                {"uid": user_id, "oid": org_id or 0, "b": bytes_uploaded},
            )
        except Exception as e:
            logger.warning("Failed to record upload rate event: %s", e)


def get_upload_rate_limiter(
    db=Depends(get_db),
    user=Depends(get_current_user),
) -> UploadRateLimiter:
    return UploadRateLimiter(db, user)
