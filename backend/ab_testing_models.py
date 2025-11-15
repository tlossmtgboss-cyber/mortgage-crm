"""
A/B Testing Database Models
Supports experimentation for AI prompts, models, agent configurations, and features
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
from main import Base


class ExperimentStatus(enum.Enum):
    """Status of an A/B test experiment"""
    DRAFT = "draft"  # Being configured
    RUNNING = "running"  # Currently collecting data
    PAUSED = "paused"  # Temporarily stopped
    COMPLETED = "completed"  # Finished, winner declared
    ARCHIVED = "archived"  # Old experiment, kept for reference


class ExperimentType(enum.Enum):
    """Type of experiment being run"""
    PROMPT = "prompt"  # Testing different AI prompts
    MODEL = "model"  # Testing different LLM models (Claude vs GPT-4)
    AGENT_CONFIG = "agent_config"  # Testing agent parameters
    FEATURE = "feature"  # Testing new features
    UI = "ui"  # Testing UI changes
    WORKFLOW = "workflow"  # Testing different workflows


class Experiment(Base):
    """
    A/B test experiment definition
    Example: Testing "Prompt V2" vs "Prompt V1" for lead qualification
    """
    __tablename__ = "ab_experiments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)  # "Lead Qualification Prompt Test"
    description = Column(Text)  # Detailed explanation
    experiment_type = Column(SQLEnum(ExperimentType), nullable=False)
    status = Column(SQLEnum(ExperimentStatus), default=ExperimentStatus.DRAFT, nullable=False)

    # Targeting
    target_percentage = Column(Float, default=100.0)  # % of traffic to include (100 = everyone)
    target_user_segment = Column(String(100))  # "all", "loan_officers", "admins", etc.

    # Metrics to track
    primary_metric = Column(String(100), nullable=False)  # "resolution_rate", "satisfaction", etc.
    secondary_metrics = Column(JSON)  # ["response_time", "escalation_rate"]

    # Statistical settings
    min_sample_size = Column(Integer, default=100)  # Minimum samples before declaring winner
    confidence_level = Column(Float, default=0.95)  # 95% confidence

    # Winner selection
    winning_variant_id = Column(Integer, ForeignKey("ab_variants.id"), nullable=True)
    winner_declared_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    created_by_user_id = Column(Integer, ForeignKey("users.id"))

    # Metadata
    metadata = Column(JSON)  # Additional configuration

    # Relationships
    variants = relationship("ExperimentVariant", back_populates="experiment", foreign_keys="ExperimentVariant.experiment_id")
    assignments = relationship("ExperimentAssignment", back_populates="experiment")
    results = relationship("ExperimentResult", back_populates="experiment")
    winner = relationship("ExperimentVariant", foreign_keys=[winning_variant_id])


class ExperimentVariant(Base):
    """
    A variant in an A/B test
    Example: Variant A = "Current prompt", Variant B = "New prompt with examples"
    """
    __tablename__ = "ab_variants"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("ab_experiments.id"), nullable=False)
    name = Column(String(100), nullable=False)  # "Control", "Treatment A", "Treatment B"
    description = Column(Text)

    # Variant configuration
    is_control = Column(Boolean, default=False)  # True for baseline variant
    traffic_allocation = Column(Float, default=50.0)  # % of experiment traffic (must sum to 100)

    # Configuration (depends on experiment type)
    config = Column(JSON, nullable=False)
    # Examples:
    # For PROMPT: {"system_prompt": "...", "few_shot_examples": [...]}
    # For MODEL: {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"}
    # For AGENT_CONFIG: {"confidence_threshold": 0.85, "max_retries": 3}

    # Metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    experiment = relationship("Experiment", back_populates="variants", foreign_keys=[experiment_id])
    assignments = relationship("ExperimentAssignment", back_populates="variant")
    results = relationship("ExperimentResult", back_populates="variant")


class ExperimentAssignment(Base):
    """
    Tracks which variant each user/session is assigned to
    Ensures consistent experience (same user always sees same variant)
    """
    __tablename__ = "ab_assignments"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("ab_experiments.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("ab_variants.id"), nullable=False)

    # Assignment target (at least one must be set)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # For logged-in users
    session_id = Column(String(255), index=True)  # For anonymous sessions

    # Assignment details
    assigned_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    assignment_method = Column(String(50), default="random")  # "random", "deterministic", "manual"

    # Relationships
    experiment = relationship("Experiment", back_populates="assignments")
    variant = relationship("ExperimentVariant", back_populates="assignments")


class ExperimentResult(Base):
    """
    Individual result/outcome for an experiment
    One row per user interaction being measured
    """
    __tablename__ = "ab_results"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("ab_experiments.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("ab_variants.id"), nullable=False, index=True)

    # Who/what generated this result
    user_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String(255))

    # Metrics (store all metrics, query by metric_name)
    metric_name = Column(String(100), nullable=False, index=True)  # "resolution_rate", "satisfaction", etc.
    metric_value = Column(Float, nullable=False)  # The measured value

    # Context
    context = Column(JSON)  # Additional data (lead_id, loan_id, interaction details)

    # Timestamp
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    experiment = relationship("Experiment", back_populates="results")
    variant = relationship("ExperimentVariant", back_populates="results")


class ExperimentInsight(Base):
    """
    Aggregated insights and statistical analysis for experiments
    Updated periodically as data comes in
    """
    __tablename__ = "ab_insights"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("ab_experiments.id"), nullable=False, index=True)

    # Statistical analysis (updated daily or on-demand)
    analysis_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Variant performance comparison
    variant_stats = Column(JSON)  # {"variant_id": {"mean": 0.85, "std": 0.1, "count": 1000}}

    # Statistical significance
    p_value = Column(Float)  # Lower = more significant (< 0.05 = significant)
    is_significant = Column(Boolean, default=False)  # True if p < confidence threshold
    confidence_interval = Column(JSON)  # {"lower": 0.80, "upper": 0.90}

    # Winner recommendation
    recommended_winner_id = Column(Integer, ForeignKey("ab_variants.id"))
    recommendation_confidence = Column(Float)  # 0-1, how confident the recommendation is
    recommendation_reason = Column(Text)  # Human-readable explanation

    # Sample size check
    sufficient_sample_size = Column(Boolean, default=False)
    current_sample_size = Column(Integer)
    required_sample_size = Column(Integer)

    # Metadata
    analysis_metadata = Column(JSON)  # Additional statistical details


# Add to main.py's create_all() after import
