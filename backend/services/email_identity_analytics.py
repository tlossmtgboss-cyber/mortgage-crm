"""Email Identity Resolution Analytics & Monitoring.

This module provides analytics, health checks, and monitoring capabilities
for the Email Identity Resolution system. Use it to:

- Track match rates and effectiveness
- Monitor system health
- Generate reports
- Set up alerts for degraded performance
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# ============================================================
# Data Classes for Type Safety
# ============================================================

@dataclass
class MatchStatistics:
    """Statistics about email matching performance."""
    total_emails: int = 0
    matched: int = 0
    unmatched: int = 0
    match_rate: float = 0.0
    by_method: Dict[str, int] = field(default_factory=dict)
    by_confidence: Dict[str, int] = field(default_factory=dict)
    priority_count: int = 0
    avg_confidence: float = 0.0
    avg_resolution_time_ms: Optional[float] = None


@dataclass
class MethodEffectiveness:
    """Effectiveness metrics for a single matching method."""
    method: str
    total_matches: int = 0
    avg_confidence: float = 0.0
    priority_rate: float = 0.0
    unique_clients: int = 0
    last_match_at: Optional[datetime] = None


@dataclass
class TrendingClient:
    """Client with recent email activity."""
    client_name: str
    email_count: int
    entity_type: str
    entity_id: Optional[int]
    last_email_at: datetime
    is_priority: bool


@dataclass
class HealthCheckResult:
    """Result of a system health check."""
    status: str  # 'healthy', 'warning', 'critical'
    checks: Dict[str, bool] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PerformanceMetrics:
    """Performance metrics for the resolution system."""
    avg_resolution_time_ms: float = 0.0
    p95_resolution_time_ms: float = 0.0
    p99_resolution_time_ms: float = 0.0
    total_resolutions: int = 0
    failed_resolutions: int = 0
    cache_hit_rate: float = 0.0


# ============================================================
# Analytics Engine
# ============================================================

class EmailIdentityAnalytics:
    """Analytics engine for email identity resolution.

    Provides comprehensive analytics including:
    - Match statistics over time periods
    - Method effectiveness comparison
    - Trending clients (high email volume)
    - Unresolved email patterns
    - Performance metrics
    """

    def __init__(self, db: Session):
        self.db = db

    def get_match_statistics(
        self,
        user_id: int,
        days: int = 7,
        include_performance: bool = False
    ) -> MatchStatistics:
        """Get comprehensive match statistics for a user.

        Args:
            user_id: User ID to get stats for
            days: Number of days to look back
            include_performance: Include resolution time metrics

        Returns:
            MatchStatistics with all metrics
        """
        since = datetime.utcnow() - timedelta(days=days)

        try:
            # Total emails
            total = self.db.execute(text("""
                SELECT COUNT(*) FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
            """), {"user_id": user_id, "since": since}).scalar() or 0

            # Matched emails
            matched = self.db.execute(text("""
                SELECT COUNT(*) FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                AND (matched_contact_id IS NOT NULL
                     OR matched_loan_id IS NOT NULL
                     OR matched_lead_id IS NOT NULL)
            """), {"user_id": user_id, "since": since}).scalar() or 0

            # By method
            method_rows = self.db.execute(text("""
                SELECT match_method, COUNT(*) as cnt
                FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                AND match_method IS NOT NULL
                GROUP BY match_method
                ORDER BY cnt DESC
            """), {"user_id": user_id, "since": since}).fetchall()

            # By confidence bucket
            confidence_rows = self.db.execute(text("""
                SELECT
                    CASE
                        WHEN match_confidence >= 0.9 THEN 'high (>=0.9)'
                        WHEN match_confidence >= 0.8 THEN 'medium (0.8-0.9)'
                        WHEN match_confidence >= 0.7 THEN 'low (0.7-0.8)'
                        ELSE 'very_low (<0.7)'
                    END as bucket,
                    COUNT(*) as cnt
                FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                AND match_confidence IS NOT NULL
                GROUP BY bucket
                ORDER BY bucket
            """), {"user_id": user_id, "since": since}).fetchall()

            # Priority count
            priority_count = self.db.execute(text("""
                SELECT COUNT(*) FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                AND is_priority = TRUE
            """), {"user_id": user_id, "since": since}).scalar() or 0

            # Average confidence
            avg_conf = self.db.execute(text("""
                SELECT AVG(match_confidence) FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                AND match_confidence IS NOT NULL
            """), {"user_id": user_id, "since": since}).scalar() or 0.0

            # Performance metrics (if requested)
            avg_time = None
            if include_performance:
                avg_time = self.db.execute(text("""
                    SELECT AVG(resolution_time_ms)
                    FROM email_identity_resolution_log
                    WHERE user_id = :user_id AND created_at >= :since
                """), {"user_id": user_id, "since": since}).scalar()

            return MatchStatistics(
                total_emails=total,
                matched=matched,
                unmatched=total - matched,
                match_rate=round(matched / total * 100, 1) if total > 0 else 0.0,
                by_method={row[0]: row[1] for row in method_rows},
                by_confidence={row[0]: row[1] for row in confidence_rows},
                priority_count=priority_count,
                avg_confidence=round(avg_conf, 3) if avg_conf else 0.0,
                avg_resolution_time_ms=avg_time
            )

        except Exception as e:
            logger.error(f"Error getting match statistics: {e}")
            return MatchStatistics()

    def get_method_effectiveness(
        self,
        user_id: int,
        days: int = 30
    ) -> List[MethodEffectiveness]:
        """Get effectiveness metrics for each matching method.

        Args:
            user_id: User ID to analyze
            days: Number of days to look back

        Returns:
            List of MethodEffectiveness for each method used
        """
        since = datetime.utcnow() - timedelta(days=days)

        try:
            rows = self.db.execute(text("""
                SELECT
                    match_method,
                    COUNT(*) as total_matches,
                    AVG(match_confidence) as avg_confidence,
                    COUNT(*) FILTER (WHERE is_priority = TRUE) * 100.0 / COUNT(*) as priority_rate,
                    COUNT(DISTINCT COALESCE(matched_contact_id::text, matched_loan_id::text, matched_lead_id::text)) as unique_clients,
                    MAX(imported_at) as last_match_at
                FROM email_reconciliation_queue
                WHERE user_id = :user_id
                AND imported_at >= :since
                AND match_method IS NOT NULL
                GROUP BY match_method
                ORDER BY total_matches DESC
            """), {"user_id": user_id, "since": since}).fetchall()

            results = []
            for row in rows:
                results.append(MethodEffectiveness(
                    method=row[0],
                    total_matches=row[1],
                    avg_confidence=round(row[2], 3) if row[2] else 0.0,
                    priority_rate=round(row[3], 1) if row[3] else 0.0,
                    unique_clients=row[4],
                    last_match_at=row[5]
                ))

            return results

        except Exception as e:
            logger.error(f"Error getting method effectiveness: {e}")
            return []

    def get_trending_clients(
        self,
        user_id: int,
        days: int = 7,
        limit: int = 10
    ) -> List[TrendingClient]:
        """Get clients with the most email activity recently.

        Args:
            user_id: User ID to analyze
            days: Number of days to look back
            limit: Maximum clients to return

        Returns:
            List of TrendingClient objects sorted by email count
        """
        since = datetime.utcnow() - timedelta(days=days)

        try:
            rows = self.db.execute(text("""
                SELECT
                    COALESCE(match_client_name, from_email) as client_name,
                    COUNT(*) as email_count,
                    CASE
                        WHEN matched_loan_id IS NOT NULL THEN 'loan'
                        WHEN matched_lead_id IS NOT NULL THEN 'lead'
                        WHEN matched_contact_id IS NOT NULL THEN 'contact'
                        ELSE 'unknown'
                    END as entity_type,
                    COALESCE(matched_loan_id, matched_lead_id, matched_contact_id) as entity_id,
                    MAX(received_date) as last_email_at,
                    BOOL_OR(is_priority) as is_priority
                FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                GROUP BY client_name, entity_type, entity_id
                ORDER BY email_count DESC
                LIMIT :limit
            """), {"user_id": user_id, "since": since, "limit": limit}).fetchall()

            results = []
            for row in rows:
                results.append(TrendingClient(
                    client_name=row[0] or "Unknown",
                    email_count=row[1],
                    entity_type=row[2],
                    entity_id=row[3],
                    last_email_at=row[4],
                    is_priority=row[5] or False
                ))

            return results

        except Exception as e:
            logger.error(f"Error getting trending clients: {e}")
            return []

    def get_unresolved_patterns(
        self,
        user_id: int,
        days: int = 7,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Analyze patterns in unresolved emails.

        Helps identify opportunities to improve match rate by
        showing common senders, domains, and subjects that don't match.

        Args:
            user_id: User ID to analyze
            days: Number of days to look back
            limit: Maximum items per category

        Returns:
            Dictionary with pattern analysis
        """
        since = datetime.utcnow() - timedelta(days=days)

        try:
            # Top unmatched senders
            senders = self.db.execute(text("""
                SELECT from_email, COUNT(*) as cnt
                FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                AND match_method IS NULL
                AND from_email IS NOT NULL
                GROUP BY from_email
                ORDER BY cnt DESC
                LIMIT :limit
            """), {"user_id": user_id, "since": since, "limit": limit}).fetchall()

            # Top unmatched domains
            domains = self.db.execute(text("""
                SELECT
                    SPLIT_PART(from_email, '@', 2) as domain,
                    COUNT(*) as cnt
                FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                AND match_method IS NULL
                AND from_email LIKE '%@%'
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT :limit
            """), {"user_id": user_id, "since": since, "limit": limit}).fetchall()

            # Subject patterns (first word)
            subjects = self.db.execute(text("""
                SELECT
                    SPLIT_PART(UPPER(subject), ' ', 1) as first_word,
                    COUNT(*) as cnt
                FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                AND match_method IS NULL
                AND subject IS NOT NULL AND subject != ''
                GROUP BY first_word
                ORDER BY cnt DESC
                LIMIT :limit
            """), {"user_id": user_id, "since": since, "limit": limit}).fetchall()

            return {
                "top_unmatched_senders": [{"email": r[0], "count": r[1]} for r in senders],
                "top_unmatched_domains": [{"domain": r[0], "count": r[1]} for r in domains],
                "subject_patterns": [{"pattern": r[0], "count": r[1]} for r in subjects],
                "recommendations": self._generate_recommendations(senders, domains)
            }

        except Exception as e:
            logger.error(f"Error analyzing unresolved patterns: {e}")
            return {}

    def _generate_recommendations(
        self,
        senders: List[Tuple],
        domains: List[Tuple]
    ) -> List[str]:
        """Generate recommendations based on unresolved patterns."""
        recommendations = []

        # Check for high-volume unmatched senders
        for email, count in senders[:3]:
            if count >= 5:
                recommendations.append(
                    f"Consider adding '{email}' to known_client_emails ({count} unmatched emails)"
                )

        # Check for unmatched vendor domains
        common_vendor_domains = {'title', 'appraisal', 'bank', 'mortgage', 'escrow'}
        for domain, count in domains[:5]:
            if count >= 3 and any(v in domain.lower() for v in common_vendor_domains):
                recommendations.append(
                    f"Consider adding domain '{domain}' to vendor mappings ({count} emails)"
                )

        return recommendations

    def get_daily_trend(
        self,
        user_id: int,
        days: int = 14
    ) -> List[Dict[str, Any]]:
        """Get daily match rate trend.

        Args:
            user_id: User ID to analyze
            days: Number of days to look back

        Returns:
            List of daily statistics
        """
        since = datetime.utcnow() - timedelta(days=days)

        try:
            rows = self.db.execute(text("""
                SELECT
                    DATE(imported_at) as date,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE match_method IS NOT NULL) as matched,
                    AVG(match_confidence) FILTER (WHERE match_confidence IS NOT NULL) as avg_confidence
                FROM email_reconciliation_queue
                WHERE user_id = :user_id AND imported_at >= :since
                GROUP BY DATE(imported_at)
                ORDER BY date
            """), {"user_id": user_id, "since": since}).fetchall()

            return [
                {
                    "date": row[0].isoformat() if row[0] else None,
                    "total": row[1],
                    "matched": row[2],
                    "match_rate": round(row[2] / row[1] * 100, 1) if row[1] > 0 else 0,
                    "avg_confidence": round(row[3], 3) if row[3] else None
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error getting daily trend: {e}")
            return []


# ============================================================
# Monitoring & Alerts
# ============================================================

class MonitoringAlerts:
    """Health checks and alerting for the identity resolution system.

    Use this class to:
    - Run health checks
    - Detect degraded performance
    - Generate alerts
    """

    def __init__(self, db: Session):
        self.db = db

    def run_health_check(
        self,
        user_id: int,
        thresholds: Optional[Dict[str, Any]] = None
    ) -> HealthCheckResult:
        """Run comprehensive health check on the system.

        Args:
            user_id: User ID to check
            thresholds: Custom thresholds (optional)

        Returns:
            HealthCheckResult with status and recommendations
        """
        thresholds = thresholds or {
            "min_match_rate": 50.0,
            "min_known_clients": 10,
            "max_queue_age_hours": 24,
            "max_unresolved_pct": 50.0
        }

        checks = {}
        metrics = {}
        recommendations = []

        try:
            # Check 1: Known clients populated
            known_count = self.db.execute(text("""
                SELECT COUNT(*) FROM known_client_emails WHERE user_id = :user_id
            """), {"user_id": user_id}).scalar() or 0

            checks["known_clients_populated"] = known_count >= thresholds["min_known_clients"]
            metrics["known_clients_count"] = known_count

            if not checks["known_clients_populated"]:
                recommendations.append(
                    f"Run sync-known-clients to populate lookup table (currently {known_count} records)"
                )

            # Check 2: Recent matches working
            recent_matched = self.db.execute(text("""
                SELECT COUNT(*) FROM email_reconciliation_queue
                WHERE user_id = :user_id
                AND imported_at >= NOW() - INTERVAL '24 hours'
                AND match_method IS NOT NULL
            """), {"user_id": user_id}).scalar() or 0

            recent_total = self.db.execute(text("""
                SELECT COUNT(*) FROM email_reconciliation_queue
                WHERE user_id = :user_id
                AND imported_at >= NOW() - INTERVAL '24 hours'
            """), {"user_id": user_id}).scalar() or 0

            match_rate = (recent_matched / recent_total * 100) if recent_total > 0 else 100
            checks["recent_matches_working"] = match_rate >= thresholds["min_match_rate"]
            metrics["recent_match_rate"] = round(match_rate, 1)
            metrics["recent_total"] = recent_total
            metrics["recent_matched"] = recent_matched

            if not checks["recent_matches_working"]:
                recommendations.append(
                    f"Match rate ({match_rate:.1f}%) below threshold ({thresholds['min_match_rate']}%)"
                )

            # Check 3: Queue not backed up
            oldest_pending = self.db.execute(text("""
                SELECT MIN(imported_at) FROM email_reconciliation_queue
                WHERE user_id = :user_id AND status = 'pending'
            """), {"user_id": user_id}).scalar()

            if oldest_pending:
                age_hours = (datetime.utcnow() - oldest_pending).total_seconds() / 3600
                checks["queue_not_backed_up"] = age_hours < thresholds["max_queue_age_hours"]
                metrics["oldest_pending_hours"] = round(age_hours, 1)

                if not checks["queue_not_backed_up"]:
                    recommendations.append(
                        f"Oldest pending email is {age_hours:.1f} hours old"
                    )
            else:
                checks["queue_not_backed_up"] = True
                metrics["oldest_pending_hours"] = 0

            # Check 4: Resolution time OK (if log table exists)
            try:
                avg_time = self.db.execute(text("""
                    SELECT AVG(resolution_time_ms)
                    FROM email_identity_resolution_log
                    WHERE user_id = :user_id
                    AND created_at >= NOW() - INTERVAL '1 hour'
                """), {"user_id": user_id}).scalar()

                if avg_time is not None:
                    checks["avg_resolution_time_ok"] = avg_time < 100
                    metrics["avg_resolution_time_ms"] = round(avg_time, 2)
                else:
                    checks["avg_resolution_time_ok"] = True
                    metrics["avg_resolution_time_ms"] = None
            except Exception as e:
                logger.exception(f"Failed to query average resolution time: {e}")
                checks["avg_resolution_time_ok"] = True
                metrics["avg_resolution_time_ms"] = None

            # Determine overall status
            failed_checks = [k for k, v in checks.items() if not v]
            if len(failed_checks) == 0:
                status = "healthy"
            elif len(failed_checks) == 1:
                status = "warning"
            else:
                status = "critical"

            return HealthCheckResult(
                status=status,
                checks=checks,
                metrics=metrics,
                recommendations=recommendations
            )

        except Exception as e:
            logger.error(f"Error running health check: {e}")
            return HealthCheckResult(
                status="critical",
                checks={"error": False},
                metrics={"error": "Internal server error"},
                recommendations=["Health check failed - check database connection"]
            )

    def check_match_rate_alert(
        self,
        user_id: int,
        threshold: float = 50.0,
        hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """Check if match rate has dropped below threshold.

        Args:
            user_id: User ID to check
            threshold: Minimum acceptable match rate
            hours: Hours to look back

        Returns:
            Alert dict if threshold breached, None otherwise
        """
        try:
            result = self.db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE match_method IS NOT NULL) as matched
                FROM email_reconciliation_queue
                WHERE user_id = :user_id
                AND imported_at >= NOW() - INTERVAL ':hours hours'
            """.replace(":hours", str(hours))), {"user_id": user_id}).fetchone()

            if result and result[0] > 0:
                match_rate = result[1] / result[0] * 100
                if match_rate < threshold:
                    return {
                        "alert_type": "low_match_rate",
                        "current_rate": round(match_rate, 1),
                        "threshold": threshold,
                        "total_emails": result[0],
                        "matched_emails": result[1],
                        "period_hours": hours,
                        "severity": "warning" if match_rate > threshold / 2 else "critical"
                    }

            return None

        except Exception as e:
            logger.error(f"Error checking match rate alert: {e}")
            return None

    def check_sync_staleness(
        self,
        user_id: int,
        max_age_hours: int = 168  # 1 week
    ) -> Optional[Dict[str, Any]]:
        """Check if known_client_emails sync is stale.

        Args:
            user_id: User ID to check
            max_age_hours: Maximum acceptable age of sync

        Returns:
            Alert dict if sync is stale, None otherwise
        """
        try:
            last_sync = self.db.execute(text("""
                SELECT MAX(last_synced) FROM known_client_emails
                WHERE user_id = :user_id
            """), {"user_id": user_id}).scalar()

            if last_sync:
                age_hours = (datetime.utcnow() - last_sync).total_seconds() / 3600
                if age_hours > max_age_hours:
                    return {
                        "alert_type": "stale_sync",
                        "last_sync": last_sync.isoformat(),
                        "age_hours": round(age_hours, 1),
                        "max_age_hours": max_age_hours,
                        "severity": "warning"
                    }
            else:
                return {
                    "alert_type": "no_sync",
                    "last_sync": None,
                    "severity": "critical"
                }

            return None

        except Exception as e:
            logger.error(f"Error checking sync staleness: {e}")
            return None


# ============================================================
# Factory Functions
# ============================================================

def get_email_identity_analytics(db: Session) -> EmailIdentityAnalytics:
    """Get an EmailIdentityAnalytics instance."""
    return EmailIdentityAnalytics(db)


def get_monitoring_alerts(db: Session) -> MonitoringAlerts:
    """Get a MonitoringAlerts instance."""
    return MonitoringAlerts(db)
