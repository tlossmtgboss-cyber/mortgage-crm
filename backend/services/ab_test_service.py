"""A/B testing service for AI call scripts — experiment management, assignment, and statistical analysis."""
import logging
import random
import math
from datetime import datetime
from typing import Optional, Dict, List

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ABTestService:
    """Manages A/B experiments for AI call scripts and engagement content."""

    def create_experiment(
        self,
        db: Session,
        name: str,
        experiment_type: str,
        primary_metric: str,
        variants: List[Dict],
        description: str = "",
        min_sample_size: int = 100,
        confidence_level: float = 0.95,
        user_id: Optional[str] = None,
    ) -> Dict:
        """Create a new A/B experiment with variants."""
        try:
            result = db.execute(text("""
                INSERT INTO ab_experiments (name, description, experiment_type, status,
                    primary_metric, min_sample_size, confidence_level, created_by_user_id)
                VALUES (:name, :desc, :type, 'draft', :metric, :min_sample, :confidence, :user_id)
                RETURNING id
            """), {
                "name": name, "desc": description, "type": experiment_type,
                "metric": primary_metric, "min_sample": min_sample_size,
                "confidence": confidence_level, "user_id": user_id,
            })
            experiment_id = result.fetchone()[0]

            # Create variants
            for v in variants:
                db.execute(text("""
                    INSERT INTO ab_variants (experiment_id, name, description, is_control,
                        traffic_allocation, config)
                    VALUES (:exp_id, :name, :desc, :is_control, :traffic, :config::json)
                """), {
                    "exp_id": experiment_id,
                    "name": v["name"],
                    "desc": v.get("description", ""),
                    "is_control": v.get("is_control", False),
                    "traffic": v.get("traffic_allocation", 50.0),
                    "config": str(v.get("config", {})).replace("'", '"'),
                })

            db.commit()
            return {"status": "created", "experiment_id": experiment_id, "variants": len(variants)}
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to create experiment: {e}")
            return {"status": "error", "detail": str(e)}

    def start_experiment(self, db: Session, experiment_id: int) -> Dict:
        """Start an experiment (move from draft to running)."""
        db.execute(text("""
            UPDATE ab_experiments SET status = 'running', started_at = CURRENT_TIMESTAMP
            WHERE id = :id AND status = 'draft'
        """), {"id": experiment_id})
        db.commit()
        return {"status": "started", "experiment_id": experiment_id}

    def assign_variant(self, db: Session, experiment_id: int, user_id: Optional[str] = None,
                       session_id: Optional[str] = None) -> Dict:
        """Assign a user/session to a variant based on traffic allocation."""
        # Check for existing assignment
        existing = db.execute(text("""
            SELECT v.id as variant_id, v.name, v.config
            FROM ab_assignments a
            JOIN ab_variants v ON v.id = a.variant_id
            WHERE a.experiment_id = :exp_id
                AND (a.user_id = :user_id OR a.session_id = :session_id)
            LIMIT 1
        """), {"exp_id": experiment_id, "user_id": user_id, "session_id": session_id}).mappings().first()

        if existing:
            return {"variant_id": existing["variant_id"], "variant_name": existing["name"],
                    "config": existing["config"], "assignment": "existing"}

        # Get variants with traffic allocation
        variants = db.execute(text("""
            SELECT id, name, traffic_allocation, config
            FROM ab_variants WHERE experiment_id = :exp_id
            ORDER BY id
        """), {"exp_id": experiment_id}).mappings().all()

        if not variants:
            return {"error": "No variants found"}

        # Weighted random assignment
        total_weight = sum(float(v["traffic_allocation"]) for v in variants)
        roll = random.uniform(0, total_weight)
        cumulative = 0
        selected = variants[0]
        for v in variants:
            cumulative += float(v["traffic_allocation"])
            if roll <= cumulative:
                selected = v
                break

        # Record assignment
        db.execute(text("""
            INSERT INTO ab_assignments (experiment_id, variant_id, user_id, session_id, assignment_method)
            VALUES (:exp_id, :var_id, :user_id, :session_id, 'weighted_random')
        """), {"exp_id": experiment_id, "var_id": selected["id"],
               "user_id": user_id, "session_id": session_id})
        db.commit()

        return {"variant_id": selected["id"], "variant_name": selected["name"],
                "config": selected["config"], "assignment": "new"}

    def record_result(self, db: Session, experiment_id: int, variant_id: int,
                      metric_name: str, metric_value: float) -> Dict:
        """Record a result metric for a variant."""
        db.execute(text("""
            INSERT INTO ab_results (experiment_id, variant_id, metric_name, metric_value)
            VALUES (:exp_id, :var_id, :metric, :value)
        """), {"exp_id": experiment_id, "var_id": variant_id,
               "metric": metric_name, "value": metric_value})
        db.commit()
        return {"status": "recorded"}

    def get_results(self, db: Session, experiment_id: int) -> Dict:
        """Get experiment results with statistical analysis."""
        # Get experiment info
        exp = db.execute(text("""
            SELECT id, name, status, primary_metric, min_sample_size, confidence_level,
                   started_at, ended_at
            FROM ab_experiments WHERE id = :id
        """), {"id": experiment_id}).mappings().first()

        if not exp:
            return {"error": "Experiment not found"}

        # Get per-variant stats
        variants = db.execute(text("""
            SELECT
                v.id, v.name, v.is_control, v.traffic_allocation,
                COUNT(DISTINCT a.id) as assignments,
                AVG(r.metric_value) as avg_metric,
                STDDEV(r.metric_value) as stddev_metric,
                COUNT(r.id) as result_count
            FROM ab_variants v
            LEFT JOIN ab_assignments a ON a.variant_id = v.id
            LEFT JOIN ab_results r ON r.variant_id = v.id AND r.metric_name = :metric
            WHERE v.experiment_id = :exp_id
            GROUP BY v.id, v.name, v.is_control, v.traffic_allocation
            ORDER BY v.id
        """), {"exp_id": experiment_id, "metric": exp["primary_metric"]}).mappings().all()

        # Statistical significance (two-sample z-test between control and each variant)
        control = next((v for v in variants if v["is_control"]), variants[0] if variants else None)
        analysis = []

        for v in variants:
            entry = {
                "variant_id": v["id"],
                "variant_name": v["name"],
                "is_control": v["is_control"],
                "assignments": v["assignments"] or 0,
                "avg_metric": round(float(v["avg_metric"] or 0), 4),
                "stddev": round(float(v["stddev_metric"] or 0), 4),
                "sample_size": v["result_count"] or 0,
            }

            if control and not v["is_control"] and control["result_count"] and v["result_count"]:
                entry["lift"] = self._calculate_lift(
                    float(control["avg_metric"] or 0), float(v["avg_metric"] or 0))
                entry["is_significant"] = self._is_significant(
                    float(control["avg_metric"] or 0), float(control["stddev_metric"] or 1),
                    int(control["result_count"]),
                    float(v["avg_metric"] or 0), float(v["stddev_metric"] or 1),
                    int(v["result_count"]),
                    float(exp["confidence_level"]),
                )

            analysis.append(entry)

        sufficient_data = all(v["sample_size"] >= int(exp["min_sample_size"]) for v in analysis)

        return {
            "experiment_id": experiment_id,
            "name": exp["name"],
            "status": exp["status"],
            "primary_metric": exp["primary_metric"],
            "sufficient_data": sufficient_data,
            "variants": analysis,
        }

    def _calculate_lift(self, control_mean: float, variant_mean: float) -> float:
        if control_mean == 0:
            return 0
        return round(((variant_mean - control_mean) / control_mean) * 100, 2)

    def _is_significant(self, mean_a: float, std_a: float, n_a: int,
                        mean_b: float, std_b: float, n_b: int,
                        confidence: float) -> bool:
        """Two-sample z-test for significance."""
        if n_a < 2 or n_b < 2:
            return False
        se = math.sqrt((std_a ** 2 / n_a) + (std_b ** 2 / n_b))
        if se == 0:
            return False
        z = abs(mean_b - mean_a) / se
        # z critical values: 90%=1.645, 95%=1.96, 99%=2.576
        z_crit = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}.get(confidence, 1.96)
        return z > z_crit


_service = None


def get_ab_test_service() -> ABTestService:
    global _service
    if _service is None:
        _service = ABTestService()
    return _service
