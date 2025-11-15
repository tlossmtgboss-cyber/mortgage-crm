"""
Experiment Service
Handles A/B test variant assignment and experiment management
"""
import hashlib
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

import sys
sys.path.append('..')
from ab_testing_models import (
    Experiment, ExperimentVariant, ExperimentAssignment, ExperimentResult,
    ExperimentStatus, ExperimentType
)

logger = logging.getLogger(__name__)


class ExperimentService:
    """Service for managing A/B testing experiments"""

    def __init__(self, db: Session):
        self.db = db

    def get_variant_for_user(
        self,
        experiment_name: str,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the assigned variant for a user/session
        Returns variant configuration or None if not in experiment

        Args:
            experiment_name: Name of the experiment
            user_id: User ID (for logged-in users)
            session_id: Session ID (for anonymous users)
            context: Additional context for targeting

        Returns:
            Variant config dict or None
        """
        try:
            # Get experiment
            experiment = self.db.query(Experiment).filter(
                Experiment.name == experiment_name,
                Experiment.status == ExperimentStatus.RUNNING
            ).first()

            if not experiment:
                logger.debug(f"Experiment '{experiment_name}' not found or not running")
                return None

            # Check if user/session should be included
            if not self._should_include(experiment, user_id, context):
                return None

            # Check for existing assignment
            existing_assignment = self._get_existing_assignment(
                experiment.id, user_id, session_id
            )

            if existing_assignment:
                variant = self.db.query(ExperimentVariant).filter(
                    ExperimentVariant.id == existing_assignment.variant_id
                ).first()
                return self._format_variant_response(variant, experiment)

            # Assign new variant
            variant = self._assign_variant(experiment, user_id, session_id)
            return self._format_variant_response(variant, experiment)

        except Exception as e:
            logger.error(f"Error getting variant for experiment '{experiment_name}': {e}")
            return None

    def record_result(
        self,
        experiment_name: str,
        metric_name: str,
        metric_value: float,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> bool:
        """
        Record an experiment result/outcome

        Args:
            experiment_name: Name of the experiment
            metric_name: Name of the metric being recorded
            metric_value: Value of the metric
            user_id: User ID
            session_id: Session ID
            context: Additional context

        Returns:
            True if recorded successfully
        """
        try:
            # Get experiment
            experiment = self.db.query(Experiment).filter(
                Experiment.name == experiment_name,
                Experiment.status == ExperimentStatus.RUNNING
            ).first()

            if not experiment:
                logger.warning(f"Cannot record result - experiment '{experiment_name}' not found")
                return False

            # Get user's variant assignment
            assignment = self._get_existing_assignment(
                experiment.id, user_id, session_id
            )

            if not assignment:
                logger.warning(f"Cannot record result - no assignment found for experiment '{experiment_name}'")
                return False

            # Create result record
            result = ExperimentResult(
                experiment_id=experiment.id,
                variant_id=assignment.variant_id,
                user_id=user_id,
                session_id=session_id,
                metric_name=metric_name,
                metric_value=metric_value,
                context=context or {}
            )

            self.db.add(result)
            self.db.commit()

            logger.info(
                f"Recorded result for experiment '{experiment_name}': "
                f"{metric_name}={metric_value} (variant_id={assignment.variant_id})"
            )
            return True

        except Exception as e:
            logger.error(f"Error recording result for experiment '{experiment_name}': {e}")
            self.db.rollback()
            return False

    def create_experiment(
        self,
        name: str,
        description: str,
        experiment_type: ExperimentType,
        primary_metric: str,
        variants: List[Dict[str, Any]],
        secondary_metrics: Optional[List[str]] = None,
        target_percentage: float = 100.0,
        min_sample_size: int = 100,
        confidence_level: float = 0.95
    ) -> Optional[Experiment]:
        """
        Create a new A/B test experiment

        Args:
            name: Experiment name
            description: Description
            experiment_type: Type of experiment
            primary_metric: Primary metric to optimize
            variants: List of variant configs [{"name": "Control", "is_control": True, "config": {...}}, ...]
            secondary_metrics: Additional metrics to track
            target_percentage: % of users to include
            min_sample_size: Minimum samples before declaring winner
            confidence_level: Statistical confidence (0.95 = 95%)

        Returns:
            Created experiment or None
        """
        try:
            # Validate traffic allocation sums to 100
            total_allocation = sum(v.get("traffic_allocation", 50.0) for v in variants)
            if abs(total_allocation - 100.0) > 0.01:
                logger.error(f"Traffic allocation must sum to 100%, got {total_allocation}")
                return None

            # Create experiment
            experiment = Experiment(
                name=name,
                description=description,
                experiment_type=experiment_type,
                status=ExperimentStatus.DRAFT,
                primary_metric=primary_metric,
                secondary_metrics=secondary_metrics or [],
                target_percentage=target_percentage,
                min_sample_size=min_sample_size,
                confidence_level=confidence_level
            )

            self.db.add(experiment)
            self.db.flush()  # Get experiment.id

            # Create variants
            for variant_data in variants:
                variant = ExperimentVariant(
                    experiment_id=experiment.id,
                    name=variant_data["name"],
                    description=variant_data.get("description", ""),
                    is_control=variant_data.get("is_control", False),
                    traffic_allocation=variant_data.get("traffic_allocation", 50.0),
                    config=variant_data["config"]
                )
                self.db.add(variant)

            self.db.commit()
            logger.info(f"Created experiment '{name}' with {len(variants)} variants")
            return experiment

        except Exception as e:
            logger.error(f"Error creating experiment: {e}")
            self.db.rollback()
            return None

    def start_experiment(self, experiment_id: int) -> bool:
        """Start an experiment"""
        try:
            experiment = self.db.query(Experiment).filter(
                Experiment.id == experiment_id
            ).first()

            if not experiment:
                logger.error(f"Experiment {experiment_id} not found")
                return False

            if experiment.status != ExperimentStatus.DRAFT:
                logger.error(f"Cannot start experiment - status is {experiment.status}")
                return False

            experiment.status = ExperimentStatus.RUNNING
            experiment.started_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(f"Started experiment '{experiment.name}'")
            return True

        except Exception as e:
            logger.error(f"Error starting experiment: {e}")
            self.db.rollback()
            return False

    def stop_experiment(self, experiment_id: int, declare_winner: bool = False) -> bool:
        """Stop an experiment and optionally declare a winner"""
        try:
            experiment = self.db.query(Experiment).filter(
                Experiment.id == experiment_id
            ).first()

            if not experiment:
                return False

            experiment.status = ExperimentStatus.COMPLETED
            experiment.ended_at = datetime.now(timezone.utc)

            if declare_winner:
                # Get latest insight to find recommended winner
                from .statistical_analysis import StatisticalAnalyzer
                analyzer = StatisticalAnalyzer(self.db)
                insight = analyzer.analyze_experiment(experiment_id)

                if insight and insight.recommended_winner_id:
                    experiment.winning_variant_id = insight.recommended_winner_id
                    experiment.winner_declared_at = datetime.now(timezone.utc)

            self.db.commit()
            logger.info(f"Stopped experiment '{experiment.name}'")
            return True

        except Exception as e:
            logger.error(f"Error stopping experiment: {e}")
            self.db.rollback()
            return False

    # Private helper methods

    def _should_include(
        self,
        experiment: Experiment,
        user_id: Optional[int],
        context: Optional[Dict]
    ) -> bool:
        """Determine if user should be included in experiment"""
        # Random sampling based on target_percentage
        if experiment.target_percentage < 100.0:
            # Use deterministic hash to ensure consistency
            hash_input = f"{experiment.id}:{user_id or context.get('session_id', '')}"
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
            if (hash_value % 100) >= experiment.target_percentage:
                return False

        # TODO: Add user segment filtering if needed
        # if experiment.target_user_segment and context:
        #     Check if user matches segment

        return True

    def _get_existing_assignment(
        self,
        experiment_id: int,
        user_id: Optional[int],
        session_id: Optional[str]
    ) -> Optional[ExperimentAssignment]:
        """Get existing variant assignment for user/session"""
        query = self.db.query(ExperimentAssignment).filter(
            ExperimentAssignment.experiment_id == experiment_id
        )

        if user_id:
            query = query.filter(ExperimentAssignment.user_id == user_id)
        elif session_id:
            query = query.filter(ExperimentAssignment.session_id == session_id)
        else:
            return None

        return query.first()

    def _assign_variant(
        self,
        experiment: Experiment,
        user_id: Optional[int],
        session_id: Optional[str]
    ) -> ExperimentVariant:
        """Assign a variant to a user/session"""
        # Get all variants with their traffic allocations
        variants = self.db.query(ExperimentVariant).filter(
            ExperimentVariant.experiment_id == experiment.id
        ).all()

        # Deterministic assignment based on hash
        hash_input = f"{experiment.id}:{user_id or session_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        random_value = (hash_value % 100000) / 1000.0  # 0-100

        # Select variant based on traffic allocation
        cumulative = 0.0
        selected_variant = variants[0]  # Fallback

        for variant in variants:
            cumulative += variant.traffic_allocation
            if random_value <= cumulative:
                selected_variant = variant
                break

        # Create assignment record
        assignment = ExperimentAssignment(
            experiment_id=experiment.id,
            variant_id=selected_variant.id,
            user_id=user_id,
            session_id=session_id,
            assignment_method="deterministic"
        )

        self.db.add(assignment)
        self.db.commit()

        logger.info(
            f"Assigned variant '{selected_variant.name}' to user_id={user_id}, "
            f"session_id={session_id} for experiment '{experiment.name}'"
        )

        return selected_variant

    def _format_variant_response(
        self,
        variant: ExperimentVariant,
        experiment: Experiment
    ) -> Dict[str, Any]:
        """Format variant data for return"""
        return {
            "variant_id": variant.id,
            "variant_name": variant.name,
            "is_control": variant.is_control,
            "config": variant.config,
            "experiment_id": experiment.id,
            "experiment_name": experiment.name,
            "experiment_type": experiment.experiment_type.value
        }
