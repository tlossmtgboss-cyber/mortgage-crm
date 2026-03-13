"""
AI Benchmarking Models

Models for tracking AI classification accuracy benchmarks:
- AIBenchmarkDataset: Named collection of labeled samples for benchmarking
- AIBenchmarkSample: Individual labeled sample with ground-truth doc type

These models support the continuous evaluation framework that measures
classifier accuracy over time by comparing AI predictions against
human-verified document types.

Usage:
    from database.models.ai_benchmark import AIBenchmarkDataset, AIBenchmarkSample

    # Create a benchmark dataset
    dataset = AIBenchmarkDataset(
        organization_id=org_id,
        name="Q1 2026 Benchmark",
    )
    db.add(dataset)

    # Add labeled samples
    sample = AIBenchmarkSample(
        dataset_id=dataset.id,
        organization_id=org_id,
        document_hash="abc123...",
        actual_doc_type="W2",
        actual_category="income",
        source="human_correction",
    )
    db.add(sample)
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
)

from db import Base


# =============================================================================
# AI BENCHMARK DATASET
# =============================================================================

class AIBenchmarkDataset(Base):
    """Named collection of labeled samples used for benchmarking AI classifiers.

    Each organization can have multiple datasets (e.g., per-quarter, per-loan-type).
    The ``last_benchmark_accuracy`` and ``last_benchmark_date`` are updated each
    time a benchmark run completes against this dataset.
    """
    __tablename__ = "ai_benchmark_datasets"
    __table_args__ = (
        Index("ix_ai_bench_ds_org_id", "organization_id"),
        Index("ix_ai_bench_ds_name", "name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, comment="FK to organizations.id")

    name = Column(String(255), nullable=False, comment="Human-readable dataset name")
    description = Column(String(1000), nullable=True, comment="Optional description")

    sample_count = Column(Integer, nullable=False, default=0, comment="Cached count of samples")
    last_benchmark_accuracy = Column(Float, nullable=True, comment="Accuracy from last benchmark run (0-100)")
    last_benchmark_date = Column(DateTime, nullable=True, comment="When last benchmark was run")

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime, nullable=True,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# =============================================================================
# AI BENCHMARK SAMPLE
# =============================================================================

class AIBenchmarkSample(Base):
    """Individual labeled sample in a benchmark dataset.

    Each sample represents a document whose type has been verified by a human.
    The ``document_hash`` links to a specific document version (SHA-256 of content)
    so the same file can be re-classified by different classifier versions.

    Sources:
    - ``human_correction``: Auto-collected from AIDocumentClassification corrections
    - ``manual_label``: Manually added by an admin
    - ``verified``: Confirmed-correct AI prediction
    """
    __tablename__ = "ai_benchmark_samples"
    __table_args__ = (
        Index("ix_ai_bench_sample_ds_id", "dataset_id"),
        Index("ix_ai_bench_sample_org_id", "organization_id"),
        Index("ix_ai_bench_sample_doc_hash", "document_hash"),
        Index("ix_ai_bench_sample_doc_type", "actual_doc_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, nullable=False, comment="FK to ai_benchmark_datasets.id")
    organization_id = Column(Integer, nullable=False, comment="FK to organizations.id")

    document_hash = Column(String(64), nullable=False, comment="SHA-256 hash of document content")
    actual_doc_type = Column(String(50), nullable=False, comment="Ground-truth document type")
    actual_category = Column(String(50), nullable=True, comment="Document category (income, assets, etc.)")

    source = Column(
        String(20), nullable=False, default="human_correction",
        comment="How sample was created: human_correction, manual_label, verified",
    )
    metadata_ = Column("metadata", JSON, nullable=True, comment="Additional context (filename, classification_id, etc.)")

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "AIBenchmarkDataset",
    "AIBenchmarkSample",
]
