"""
Model Versioning for Call Intelligence

Tracks model versions for reproducibility and enables A/B testing
of different extraction configurations.

Features:
- Track which model/prompt version produced each extraction
- Compare extraction quality between versions
- Manage active/inactive versions
- Support for A/B testing
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from .llm_client import BaseLLMClient, LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ModelVersion:
    """Represents a specific model/prompt configuration."""
    version_id: str
    llm_provider: str  # "anthropic" or "openai"
    model_name: str    # e.g., "claude-3-sonnet-20240229"
    schema_version: str
    prompt_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "llm_provider": self.llm_provider,
            "model_name": self.model_name,
            "schema_version": self.schema_version,
            "prompt_hash": self.prompt_hash,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


@dataclass
class VersionComparisonReport:
    """Report comparing extraction quality between versions."""
    version_a: str
    version_b: str
    sample_size: int
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Metrics
    avg_extractions_a: float = 0.0
    avg_extractions_b: float = 0.0
    avg_confidence_a: float = 0.0
    avg_confidence_b: float = 0.0
    high_confidence_rate_a: float = 0.0
    high_confidence_rate_b: float = 0.0

    # Field-level comparison
    field_differences: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Recommendation
    recommended_version: Optional[str] = None
    recommendation_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_a": self.version_a,
            "version_b": self.version_b,
            "sample_size": self.sample_size,
            "generated_at": self.generated_at.isoformat(),
            "metrics": {
                "version_a": {
                    "avg_extractions": self.avg_extractions_a,
                    "avg_confidence": self.avg_confidence_a,
                    "high_confidence_rate": self.high_confidence_rate_a,
                },
                "version_b": {
                    "avg_extractions": self.avg_extractions_b,
                    "avg_confidence": self.avg_confidence_b,
                    "high_confidence_rate": self.high_confidence_rate_b,
                },
            },
            "field_differences": self.field_differences,
            "recommendation": {
                "version": self.recommended_version,
                "reason": self.recommendation_reason,
            },
        }


# =============================================================================
# Model Version Tracker
# =============================================================================

class ModelVersionTracker:
    """
    Track model versions for reproducibility and A/B testing.

    Usage:
        tracker = ModelVersionTracker(db_session)

        # Get active version
        version = tracker.get_active_version()

        # Record extraction with version
        tracker.record_extraction(call_id, version, result)

        # Compare versions
        report = tracker.compare_versions("v1.0", "v1.1", sample_size=100)
    """

    # Schema version - increment when extraction schema changes
    SCHEMA_VERSION = "1.0"

    def __init__(self, db_session: Optional["Session"] = None):
        """
        Initialize version tracker.

        Args:
            db_session: SQLAlchemy session (optional, for persistence)
        """
        self.db = db_session
        self._active_version: Optional[ModelVersion] = None
        self._version_cache: Dict[str, ModelVersion] = {}

    def create_version(
        self,
        llm_provider: str,
        model_name: str,
        prompt_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        set_active: bool = False,
    ) -> ModelVersion:
        """
        Create a new model version.

        Args:
            llm_provider: Provider name (anthropic, openai)
            model_name: Model identifier
            prompt_content: Full prompt text for hashing
            metadata: Additional metadata
            set_active: Whether to set as active version

        Returns:
            Created ModelVersion
        """
        prompt_hash = self._compute_hash(prompt_content)

        # Generate version ID
        version_id = f"v{self.SCHEMA_VERSION}-{prompt_hash[:8]}"

        version = ModelVersion(
            version_id=version_id,
            llm_provider=llm_provider,
            model_name=model_name,
            schema_version=self.SCHEMA_VERSION,
            prompt_hash=prompt_hash,
            is_active=set_active,
            metadata=metadata or {},
        )

        # Cache version
        self._version_cache[version_id] = version

        # Persist if DB available
        if self.db:
            self._save_version(version)

        if set_active:
            self._active_version = version

        logger.info(f"Created model version: {version_id}")

        return version

    def get_active_version(self) -> Optional[ModelVersion]:
        """
        Get currently active model version.

        Returns:
            Active ModelVersion or None
        """
        if self._active_version:
            return self._active_version

        # Try to load from database
        if self.db:
            version = self._load_active_version()
            if version:
                self._active_version = version
                return version

        return None

    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        """
        Get a specific version by ID.

        Args:
            version_id: Version identifier

        Returns:
            ModelVersion or None
        """
        # Check cache
        if version_id in self._version_cache:
            return self._version_cache[version_id]

        # Try database
        if self.db:
            version = self._load_version(version_id)
            if version:
                self._version_cache[version_id] = version
                return version

        return None

    def set_active_version(self, version_id: str) -> bool:
        """
        Set a version as active.

        Args:
            version_id: Version to activate

        Returns:
            True if successful
        """
        version = self.get_version(version_id)
        if not version:
            logger.warning(f"Version {version_id} not found")
            return False

        # Deactivate current
        if self._active_version:
            self._active_version.is_active = False
            if self.db:
                self._update_version_status(self._active_version.version_id, False)

        # Activate new
        version.is_active = True
        self._active_version = version

        if self.db:
            self._update_version_status(version_id, True)

        logger.info(f"Set active version: {version_id}")

        return True

    def record_extraction(
        self,
        call_id: str,
        version: ModelVersion,
        total_extractions: int,
        high_confidence_count: int,
        processing_time_ms: int,
        extraction_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record which version produced an extraction.

        Args:
            call_id: Call identifier
            version: Model version used
            total_extractions: Number of extractions
            high_confidence_count: High confidence extractions
            processing_time_ms: Processing time
            extraction_details: Optional detailed extraction info
        """
        if not self.db:
            return

        from sqlalchemy import text

        try:
            self.db.execute(
                text("""
                    INSERT INTO model_version_extractions
                    (call_id, version_id, total_extractions, high_confidence_count,
                     processing_time_ms, extraction_details, created_at)
                    VALUES
                    (:call_id, :version_id, :total, :high_conf, :time_ms, :details, :created_at)
                    ON CONFLICT (call_id) DO UPDATE SET
                        version_id = :version_id,
                        total_extractions = :total,
                        high_confidence_count = :high_conf,
                        processing_time_ms = :time_ms
                """),
                {
                    "call_id": call_id,
                    "version_id": version.version_id,
                    "total": total_extractions,
                    "high_conf": high_confidence_count,
                    "time_ms": processing_time_ms,
                    "details": json.dumps(extraction_details) if extraction_details else None,
                    "created_at": datetime.now(timezone.utc),
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to record extraction version: {e}")
            try:
                self.db.rollback()
            except Exception as e:
                logger.error(f"Error during rollback in record_extraction: {e}")

    def compare_versions(
        self,
        version_a: str,
        version_b: str,
        sample_size: int = 100,
    ) -> VersionComparisonReport:
        """
        Compare extraction quality between two versions.

        Args:
            version_a: First version ID
            version_b: Second version ID
            sample_size: Number of extractions to compare

        Returns:
            VersionComparisonReport with comparison metrics
        """
        report = VersionComparisonReport(
            version_a=version_a,
            version_b=version_b,
            sample_size=sample_size,
        )

        if not self.db:
            report.recommendation_reason = "No database connection for comparison"
            return report

        from sqlalchemy import text

        try:
            # Get metrics for version A
            result_a = self.db.execute(
                text("""
                    SELECT
                        AVG(total_extractions) as avg_extractions,
                        AVG(CASE WHEN total_extractions > 0
                            THEN high_confidence_count::float / total_extractions
                            ELSE 0 END) as high_conf_rate,
                        COUNT(*) as count
                    FROM model_version_extractions
                    WHERE version_id = :version_id
                    LIMIT :limit
                """),
                {"version_id": version_a, "limit": sample_size}
            ).fetchone()

            # Get metrics for version B
            result_b = self.db.execute(
                text("""
                    SELECT
                        AVG(total_extractions) as avg_extractions,
                        AVG(CASE WHEN total_extractions > 0
                            THEN high_confidence_count::float / total_extractions
                            ELSE 0 END) as high_conf_rate,
                        COUNT(*) as count
                    FROM model_version_extractions
                    WHERE version_id = :version_id
                    LIMIT :limit
                """),
                {"version_id": version_b, "limit": sample_size}
            ).fetchone()

            if result_a:
                report.avg_extractions_a = float(result_a[0] or 0)
                report.high_confidence_rate_a = float(result_a[1] or 0) * 100

            if result_b:
                report.avg_extractions_b = float(result_b[0] or 0)
                report.high_confidence_rate_b = float(result_b[1] or 0) * 100

            # Determine recommendation
            score_a = report.avg_extractions_a * report.high_confidence_rate_a
            score_b = report.avg_extractions_b * report.high_confidence_rate_b

            if score_a > score_b * 1.05:  # 5% improvement threshold
                report.recommended_version = version_a
                report.recommendation_reason = (
                    f"Version A has better combined score "
                    f"({score_a:.1f} vs {score_b:.1f})"
                )
            elif score_b > score_a * 1.05:
                report.recommended_version = version_b
                report.recommendation_reason = (
                    f"Version B has better combined score "
                    f"({score_b:.1f} vs {score_a:.1f})"
                )
            else:
                report.recommendation_reason = (
                    "Versions perform similarly, no clear winner"
                )

        except Exception as e:
            logger.warning(f"Version comparison failed: {e}")
            report.recommendation_reason = f"Comparison failed: {e}"

        return report

    def get_version_stats(
        self,
        version_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get performance statistics for a version.

        Args:
            version_id: Version to analyze
            days: Look back period

        Returns:
            Dict with version statistics
        """
        if not self.db:
            return {}

        from sqlalchemy import text
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            result = self.db.execute(
                text("""
                    SELECT
                        COUNT(*) as total_calls,
                        AVG(total_extractions) as avg_extractions,
                        AVG(high_confidence_count) as avg_high_conf,
                        AVG(processing_time_ms) as avg_time_ms,
                        MIN(created_at) as first_use,
                        MAX(created_at) as last_use
                    FROM model_version_extractions
                    WHERE version_id = :version_id
                    AND created_at >= :cutoff
                """),
                {"version_id": version_id, "cutoff": cutoff}
            ).fetchone()

            if result:
                return {
                    "version_id": version_id,
                    "period_days": days,
                    "total_calls": result[0] or 0,
                    "avg_extractions": round(float(result[1] or 0), 1),
                    "avg_high_confidence": round(float(result[2] or 0), 1),
                    "avg_processing_time_ms": round(float(result[3] or 0), 0),
                    "first_use": result[4].isoformat() if result[4] else None,
                    "last_use": result[5].isoformat() if result[5] else None,
                }

        except Exception as e:
            logger.warning(f"Failed to get version stats: {e}")

        return {}

    def list_versions(
        self,
        include_inactive: bool = False,
        limit: int = 20,
    ) -> List[ModelVersion]:
        """
        List available model versions.

        Args:
            include_inactive: Include inactive versions
            limit: Max versions to return

        Returns:
            List of ModelVersion objects
        """
        if not self.db:
            return list(self._version_cache.values())[:limit]

        from sqlalchemy import text

        try:
            query = """
                SELECT
                    version_id, llm_provider, model_name, schema_version,
                    prompt_hash, created_at, is_active, metadata
                FROM model_versions
            """
            if not include_inactive:
                query += " WHERE is_active = true"
            query += " ORDER BY created_at DESC LIMIT :limit"

            result = self.db.execute(text(query), {"limit": limit}).fetchall()

            versions = []
            for row in result:
                version = ModelVersion(
                    version_id=row[0],
                    llm_provider=row[1],
                    model_name=row[2],
                    schema_version=row[3],
                    prompt_hash=row[4],
                    created_at=row[5],
                    is_active=row[6],
                    metadata=json.loads(row[7]) if row[7] else {},
                )
                versions.append(version)
                self._version_cache[version.version_id] = version

            return versions

        except Exception as e:
            logger.warning(f"Failed to list versions: {e}")
            return list(self._version_cache.values())[:limit]

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()

    def _save_version(self, version: ModelVersion) -> None:
        """Save version to database."""
        from sqlalchemy import text

        try:
            self.db.execute(
                text("""
                    INSERT INTO model_versions
                    (version_id, llm_provider, model_name, schema_version,
                     prompt_hash, created_at, is_active, metadata)
                    VALUES
                    (:version_id, :provider, :model, :schema_version,
                     :prompt_hash, :created_at, :is_active, :metadata)
                    ON CONFLICT (version_id) DO NOTHING
                """),
                {
                    "version_id": version.version_id,
                    "provider": version.llm_provider,
                    "model": version.model_name,
                    "schema_version": version.schema_version,
                    "prompt_hash": version.prompt_hash,
                    "created_at": version.created_at,
                    "is_active": version.is_active,
                    "metadata": json.dumps(version.metadata),
                }
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.warning(f"Failed to save version: {e}")

    def _load_version(self, version_id: str) -> Optional[ModelVersion]:
        """Load version from database."""
        from sqlalchemy import text

        try:
            result = self.db.execute(
                text("""
                    SELECT
                        version_id, llm_provider, model_name, schema_version,
                        prompt_hash, created_at, is_active, metadata
                    FROM model_versions
                    WHERE version_id = :version_id
                """),
                {"version_id": version_id}
            ).fetchone()

            if result:
                return ModelVersion(
                    version_id=result[0],
                    llm_provider=result[1],
                    model_name=result[2],
                    schema_version=result[3],
                    prompt_hash=result[4],
                    created_at=result[5],
                    is_active=result[6],
                    metadata=json.loads(result[7]) if result[7] else {},
                )

        except Exception as e:
            logger.warning(f"Failed to load version: {e}")

        return None

    def _load_active_version(self) -> Optional[ModelVersion]:
        """Load active version from database."""
        from sqlalchemy import text

        try:
            result = self.db.execute(
                text("""
                    SELECT
                        version_id, llm_provider, model_name, schema_version,
                        prompt_hash, created_at, is_active, metadata
                    FROM model_versions
                    WHERE is_active = true
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
            ).fetchone()

            if result:
                return ModelVersion(
                    version_id=result[0],
                    llm_provider=result[1],
                    model_name=result[2],
                    schema_version=result[3],
                    prompt_hash=result[4],
                    created_at=result[5],
                    is_active=result[6],
                    metadata=json.loads(result[7]) if result[7] else {},
                )

        except Exception as e:
            logger.warning(f"Failed to load active version: {e}")

        return None

    def _update_version_status(self, version_id: str, is_active: bool) -> None:
        """Update version active status."""
        from sqlalchemy import text

        try:
            self.db.execute(
                text("""
                    UPDATE model_versions
                    SET is_active = :is_active
                    WHERE version_id = :version_id
                """),
                {"version_id": version_id, "is_active": is_active}
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.warning(f"Failed to update version status: {e}")


# =============================================================================
# Factory
# =============================================================================

def create_version_tracker(db_session: Optional["Session"] = None) -> ModelVersionTracker:
    """
    Create version tracker instance.

    Args:
        db_session: Optional SQLAlchemy session

    Returns:
        Configured ModelVersionTracker
    """
    return ModelVersionTracker(db_session)
