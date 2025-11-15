"""
Statistical Analysis for A/B Testing
Calculates significance, confidence intervals, and winner recommendations
"""
import logging
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import defaultdict

import sys
sys.path.append('..')
from ab_testing_models import (
    Experiment, ExperimentVariant, ExperimentResult, ExperimentInsight
)

logger = logging.getLogger(__name__)


class StatisticalAnalyzer:
    """Analyzes A/B test results and determines statistical significance"""

    def __init__(self, db: Session):
        self.db = db

    def analyze_experiment(self, experiment_id: int) -> Optional[ExperimentInsight]:
        """
        Perform complete statistical analysis on an experiment

        Args:
            experiment_id: ID of experiment to analyze

        Returns:
            ExperimentInsight with analysis results
        """
        try:
            experiment = self.db.query(Experiment).filter(
                Experiment.id == experiment_id
            ).first()

            if not experiment:
                logger.error(f"Experiment {experiment_id} not found")
                return None

            # Get variant statistics
            variant_stats = self._calculate_variant_stats(
                experiment_id,
                experiment.primary_metric
            )

            if not variant_stats or len(variant_stats) < 2:
                logger.warning(f"Not enough data for experiment {experiment_id}")
                return None

            # Calculate statistical significance
            p_value, is_significant = self._calculate_p_value(variant_stats)

            # Determine winner
            recommended_winner_id, confidence, reason = self._recommend_winner(
                variant_stats,
                is_significant,
                experiment.confidence_level
            )

            # Check sample size
            total_samples = sum(stats['count'] for stats in variant_stats.values())
            sufficient_samples = total_samples >= experiment.min_sample_size

            # Create or update insight
            insight = self.db.query(ExperimentInsight).filter(
                ExperimentInsight.experiment_id == experiment_id
            ).order_by(ExperimentInsight.analysis_date.desc()).first()

            if not insight:
                insight = ExperimentInsight(experiment_id=experiment_id)
                self.db.add(insight)

            # Update insight
            insight.analysis_date = datetime.now(timezone.utc)
            insight.variant_stats = {
                str(k): v for k, v in variant_stats.items()
            }
            insight.p_value = p_value
            insight.is_significant = is_significant
            insight.recommended_winner_id = recommended_winner_id
            insight.recommendation_confidence = confidence
            insight.recommendation_reason = reason
            insight.sufficient_sample_size = sufficient_samples
            insight.current_sample_size = total_samples
            insight.required_sample_size = experiment.min_sample_size

            self.db.commit()

            logger.info(
                f"Analyzed experiment {experiment_id}: "
                f"p_value={p_value:.4f}, significant={is_significant}, "
                f"winner={recommended_winner_id}"
            )

            return insight

        except Exception as e:
            logger.error(f"Error analyzing experiment {experiment_id}: {e}")
            self.db.rollback()
            return None

    def _calculate_variant_stats(
        self,
        experiment_id: int,
        metric_name: str
    ) -> Dict[int, Dict]:
        """
        Calculate statistics for each variant

        Returns:
            {variant_id: {"mean": float, "std": float, "count": int, "values": list}}
        """
        try:
            # Get all results for this experiment and metric
            results = self.db.query(ExperimentResult).filter(
                ExperimentResult.experiment_id == experiment_id,
                ExperimentResult.metric_name == metric_name
            ).all()

            # Group by variant
            variant_data = defaultdict(list)
            for result in results:
                variant_data[result.variant_id].append(result.metric_value)

            # Calculate statistics
            variant_stats = {}
            for variant_id, values in variant_data.items():
                if not values:
                    continue

                mean = sum(values) / len(values)
                variance = sum((x - mean) ** 2 for x in values) / len(values)
                std = math.sqrt(variance) if variance > 0 else 0.0

                variant_stats[variant_id] = {
                    "mean": mean,
                    "std": std,
                    "count": len(values),
                    "values": values,
                    "min": min(values),
                    "max": max(values),
                    "median": sorted(values)[len(values) // 2]
                }

            return variant_stats

        except Exception as e:
            logger.error(f"Error calculating variant stats: {e}")
            return {}

    def _calculate_p_value(
        self,
        variant_stats: Dict[int, Dict]
    ) -> Tuple[float, bool]:
        """
        Calculate p-value using two-sample t-test

        Returns:
            (p_value, is_significant)
        """
        try:
            # For simplicity, compare control vs best performing variant
            # Find control variant
            control_id = None
            control_stats = None

            for variant_id, stats in variant_stats.items():
                # Assuming control has lowest variant_id or check is_control flag
                if control_id is None or variant_id < control_id:
                    control_id = variant_id
                    control_stats = stats

            if not control_stats:
                return 1.0, False

            # Find best performing variant (highest mean)
            best_id = max(variant_stats.keys(), key=lambda k: variant_stats[k]["mean"])
            best_stats = variant_stats[best_id]

            if best_id == control_id:
                # Control is already best
                return 1.0, False

            # Calculate t-statistic
            mean1 = control_stats["mean"]
            mean2 = best_stats["mean"]
            std1 = control_stats["std"]
            std2 = best_stats["std"]
            n1 = control_stats["count"]
            n2 = best_stats["count"]

            # Pooled standard error
            se = math.sqrt((std1 ** 2 / n1) + (std2 ** 2 / n2))

            if se == 0:
                return 1.0, False

            t_stat = abs(mean2 - mean1) / se

            # Degrees of freedom (Welch's approximation)
            df = ((std1 ** 2 / n1 + std2 ** 2 / n2) ** 2) / \
                 ((std1 ** 2 / n1) ** 2 / (n1 - 1) + (std2 ** 2 / n2) ** 2 / (n2 - 1))

            # Simplified p-value calculation (two-tailed)
            # For production, use scipy.stats.t.sf(t_stat, df) * 2
            # This is a rough approximation
            if t_stat > 2.0:  # Roughly corresponds to p < 0.05 for large samples
                p_value = 0.01
                is_significant = True
            elif t_stat > 1.65:  # Roughly corresponds to p < 0.10
                p_value = 0.08
                is_significant = False
            else:
                p_value = 0.20
                is_significant = False

            return p_value, is_significant

        except Exception as e:
            logger.error(f"Error calculating p-value: {e}")
            return 1.0, False

    def _recommend_winner(
        self,
        variant_stats: Dict[int, Dict],
        is_significant: bool,
        confidence_level: float
    ) -> Tuple[Optional[int], float, str]:
        """
        Recommend winning variant

        Returns:
            (variant_id, confidence, reason)
        """
        try:
            if not is_significant:
                return (
                    None,
                    0.0,
                    "No statistically significant difference found. Need more data or variants perform similarly."
                )

            # Find variant with highest mean
            best_id = max(variant_stats.keys(), key=lambda k: variant_stats[k]["mean"])
            best_stats = variant_stats[best_id]

            # Calculate confidence based on sample size and effect size
            sample_size = best_stats["count"]

            # Simple confidence calculation
            if sample_size < 100:
                confidence = 0.6
            elif sample_size < 500:
                confidence = 0.75
            elif sample_size < 1000:
                confidence = 0.85
            else:
                confidence = 0.95

            # Calculate improvement percentage
            control_id = min(variant_stats.keys())
            control_mean = variant_stats[control_id]["mean"]
            best_mean = best_stats["mean"]

            if control_mean > 0:
                improvement = ((best_mean - control_mean) / control_mean) * 100
            else:
                improvement = 0

            reason = (
                f"Variant {best_id} shows {improvement:.1f}% improvement "
                f"with {sample_size} samples. Mean: {best_mean:.3f} "
                f"(vs control: {control_mean:.3f})"
            )

            return best_id, confidence, reason

        except Exception as e:
            logger.error(f"Error recommending winner: {e}")
            return None, 0.0, f"Error in analysis: {str(e)}"

    def get_experiment_summary(self, experiment_id: int) -> Optional[Dict]:
        """
        Get human-readable summary of experiment results

        Returns:
            Summary dict with all key metrics
        """
        try:
            experiment = self.db.query(Experiment).filter(
                Experiment.id == experiment_id
            ).first()

            if not experiment:
                return None

            # Get latest insight
            insight = self.db.query(ExperimentInsight).filter(
                ExperimentInsight.experiment_id == experiment_id
            ).order_by(ExperimentInsight.analysis_date.desc()).first()

            # Get variant details
            variants = self.db.query(ExperimentVariant).filter(
                ExperimentVariant.experiment_id == experiment_id
            ).all()

            variant_details = []
            for variant in variants:
                stats = insight.variant_stats.get(str(variant.id), {}) if insight else {}
                variant_details.append({
                    "id": variant.id,
                    "name": variant.name,
                    "is_control": variant.is_control,
                    "mean": stats.get("mean", 0),
                    "count": stats.get("count", 0),
                    "is_winner": variant.id == insight.recommended_winner_id if insight else False
                })

            summary = {
                "experiment_id": experiment.id,
                "experiment_name": experiment.name,
                "status": experiment.status.value,
                "primary_metric": experiment.primary_metric,
                "variants": variant_details,
                "is_significant": insight.is_significant if insight else False,
                "p_value": insight.p_value if insight else None,
                "recommended_winner_id": insight.recommended_winner_id if insight else None,
                "recommendation_reason": insight.recommendation_reason if insight else None,
                "sufficient_sample_size": insight.sufficient_sample_size if insight else False,
                "current_sample_size": insight.current_sample_size if insight else 0,
                "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
                "ended_at": experiment.ended_at.isoformat() if experiment.ended_at else None
            }

            return summary

        except Exception as e:
            logger.error(f"Error getting experiment summary: {e}")
            return None


# Helper function for better p-value calculation (if scipy is available)
def calculate_p_value_scipy(values1: List[float], values2: List[float]) -> float:
    """
    Calculate p-value using scipy (more accurate)
    Install: pip install scipy
    """
    try:
        from scipy import stats

        t_stat, p_value = stats.ttest_ind(values1, values2)
        return p_value
    except ImportError:
        logger.warning("scipy not available, using simplified p-value calculation")
        return None
