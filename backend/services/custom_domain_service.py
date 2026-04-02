"""
Custom Domain Service

Provides cached domain lookups for CORS middleware.
Caches allowed domains in memory with periodic refresh.
"""

import logging
import threading
import time
from typing import Set, Optional
from datetime import datetime, timezone

from sqlalchemy import text
from database import SessionLocal
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class CustomDomainService:
    """
    Service for managing custom domain lookups with caching.

    Features:
    - In-memory cache of allowed domains
    - Automatic refresh every 60 seconds
    - Thread-safe operations
    - Fallback to static list if DB unavailable
    """

    # Static domains that are always allowed
    STATIC_DOMAINS = {
        "http://localhost:3000",
        "http://localhost:3001",
        "https://perenniaai.com",
        "https://www.perenniaai.com",
        "https://app.perenniaai.com",
        "https://app.perenniaai.com",
    }

    def __init__(self, refresh_interval: int = 60):
        self._cache: Set[str] = set()
        self._cache_lock = threading.Lock()
        self._last_refresh: Optional[datetime] = None
        self._refresh_interval = refresh_interval
        self._initialized = False

        # Initial load
        self._refresh_cache()

    def _refresh_cache(self) -> None:
        """Refresh the domain cache from database."""
        try:
            db = SessionLocal()
            try:
                result = db.execute(text("""
                    SELECT domain FROM custom_domains
                    WHERE is_active = true
                """))
                domains = {f"https://{row[0]}" for row in result.fetchall()}

                with self._cache_lock:
                    self._cache = domains
                    self._last_refresh = datetime.now(timezone.utc)
                    self._initialized = True

                logger.info(f"Refreshed custom domains cache: {len(domains)} domains")
            finally:
                db.close()

        except SQLAlchemyError as e:
            logger.warning(f"Failed to refresh custom domains cache: {e}")
            # Keep using existing cache if refresh fails
            if not self._initialized:
                self._cache = set()
                self._initialized = True

    def _maybe_refresh(self) -> None:
        """Refresh cache if interval has passed."""
        if self._last_refresh is None:
            self._refresh_cache()
            return

        elapsed = (datetime.now(timezone.utc) - self._last_refresh).total_seconds()
        if elapsed > self._refresh_interval:
            # Refresh in background to not block requests
            thread = threading.Thread(target=self._refresh_cache)
            thread.daemon = True
            thread.start()

    def is_allowed_origin(self, origin: str) -> bool:
        """
        Check if an origin is allowed.

        Args:
            origin: The origin to check (e.g., "https://www.timloss.com")

        Returns:
            True if origin is allowed
        """
        if not origin:
            return False

        # Always allow static domains
        if origin in self.STATIC_DOMAINS:
            return True

        # Allow perenniaai.com and subdomains
        if origin.endswith("perenniaai.com"):
            return True

        # Check dynamic cache
        self._maybe_refresh()

        with self._cache_lock:
            return origin in self._cache

    def get_all_allowed_origins(self) -> Set[str]:
        """Get all allowed origins (static + dynamic)."""
        self._maybe_refresh()

        with self._cache_lock:
            return self.STATIC_DOMAINS | self._cache

    def add_domain(self, domain: str, user_id: Optional[int] = None,
                   organization_id: Optional[int] = None) -> bool:
        """
        Add a new custom domain.

        Args:
            domain: Domain to add (without https://)
            user_id: Optional user who owns this domain
            organization_id: Optional organization that owns this domain

        Returns:
            True if added successfully
        """
        try:
            db = SessionLocal()
            try:
                # Check if already exists
                existing = db.execute(text(
                    "SELECT id FROM custom_domains WHERE domain = :domain"
                ), {"domain": domain}).fetchone()

                if existing:
                    logger.info(f"Domain {domain} already exists")
                    return False

                # Insert new domain
                db.execute(text("""
                    INSERT INTO custom_domains (domain, user_id, organization_id, is_active, is_verified)
                    VALUES (:domain, :user_id, :org_id, true, true)
                """), {
                    "domain": domain,
                    "user_id": user_id,
                    "org_id": organization_id
                })
                db.commit()

                # Refresh cache immediately
                self._refresh_cache()

                logger.info(f"Added custom domain: {domain}")
                return True

            finally:
                db.close()

        except SQLAlchemyError as e:
            logger.error(f"Failed to add domain {domain}: {e}")
            return False

    def remove_domain(self, domain: str) -> bool:
        """Remove a custom domain."""
        try:
            db = SessionLocal()
            try:
                db.execute(text(
                    "UPDATE custom_domains SET is_active = false WHERE domain = :domain"
                ), {"domain": domain})
                db.commit()

                # Refresh cache immediately
                self._refresh_cache()

                logger.info(f"Removed custom domain: {domain}")
                return True

            finally:
                db.close()

        except SQLAlchemyError as e:
            logger.error(f"Failed to remove domain {domain}: {e}")
            return False

    def list_domains(self) -> list:
        """List all custom domains with their status."""
        try:
            db = SessionLocal()
            try:
                result = db.execute(text("""
                    SELECT id, domain, is_verified, is_active, ssl_status,
                           created_at, organization_id, user_id,
                           verification_token, verified_at
                    FROM custom_domains
                    ORDER BY created_at DESC
                """))

                domains = []
                for row in result.fetchall():
                    domains.append({
                        "id": row[0],
                        "domain": row[1],
                        "is_verified": row[2],
                        "is_active": row[3],
                        "ssl_status": row[4],
                        "created_at": row[5].isoformat() if row[5] else None,
                        "organization_id": row[6],
                        "user_id": row[7],
                        "verification_token": row[8],
                        "verified_at": row[9].isoformat() if row[9] else None
                    })

                return domains

            finally:
                db.close()

        except SQLAlchemyError as e:
            logger.error(f"Failed to list domains: {e}")
            return []


# Singleton instance
_domain_service: Optional[CustomDomainService] = None


def get_domain_service() -> CustomDomainService:
    """Get the singleton domain service instance."""
    global _domain_service
    if _domain_service is None:
        _domain_service = CustomDomainService()
    return _domain_service
