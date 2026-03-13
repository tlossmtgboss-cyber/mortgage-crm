"""
AI Benchmarking Service

Provides accuracy benchmarking and continuous evaluation for the AI document
classifier. Collects labeled samples from human corrections, runs benchmark
evaluations, generates confusion matrices, tracks accuracy trends, and
evaluates confidence calibration.

Usage:
    from services.smart_docs.ai_benchmarking_service import AIBenchmarkingService

    service = AIBenchmarkingService(db_session)
    dataset_id = service.create_benchmark_dataset(org_id=1, name="Q1 2026")
    service.auto_collect_from_corrections(org_id=1)
    result = service.run_benchmark(dataset_id)
    print(result.accuracy, result.confusion_matrix)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, case, and_, text
from sqlalchemy.orm import Session

from database.models.ai_benchmark import AIBenchmarkDataset, AIBenchmarkSample
from database.models.document_intelligence import AIDocumentClassification

logger = logging.getLogger(__name__)


# =============================================================================
# BENCHMARK RESULT DATACLASS
# =============================================================================

@dataclass
class BenchmarkResult:
    """Comprehensive result from a benchmark run."""
    accuracy: float  # Overall accuracy percentage (0-100)
    precision_by_type: Dict[str, float]  # doc_type -> precision (0-100)
    recall_by_type: Dict[str, float]  # doc_type -> recall (0-100)
    f1_by_type: Dict[str, float]  # doc_type -> F1 score (0-100)
    confusion_matrix: Dict[str, Dict[str, int]]  # actual -> {predicted -> count}
    sample_count: int
    classifier_version: str
    run_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    per_type_accuracy: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict."""
        return {
            "accuracy": round(self.accuracy, 2),
            "sample_count": self.sample_count,
            "classifier_version": self.classifier_version,
            "run_date": self.run_date.isoformat(),
            "precision_by_type": {k: round(v, 2) for k, v in self.precision_by_type.items()},
            "recall_by_type": {k: round(v, 2) for k, v in self.recall_by_type.items()},
            "f1_by_type": {k: round(v, 2) for k, v in self.f1_by_type.items()},
            "per_type_accuracy": {k: round(v, 2) for k, v in self.per_type_accuracy.items()},
            "confusion_matrix": self.confusion_matrix,
        }


# =============================================================================
# AI BENCHMARKING SERVICE
# =============================================================================

class AIBenchmarkingService:
    """Service for managing AI classification benchmarks and continuous evaluation."""

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------------------
    # Dataset Management
    # -------------------------------------------------------------------------

    def create_benchmark_dataset(
        self,
        org_id: int,
        name: str,
        description: Optional[str] = None,
    ) -> int:
        """Create a new benchmark dataset.

        Args:
            org_id: Organization ID for tenant isolation.
            name: Human-readable dataset name.
            description: Optional description.

        Returns:
            The ID of the newly created dataset.
        """
        dataset = AIBenchmarkDataset(
            organization_id=org_id,
            name=name,
            description=description,
            sample_count=0,
        )
        self.db.add(dataset)
        self.db.flush()
        logger.info("Created benchmark dataset id=%s name=%s org=%s", dataset.id, name, org_id)
        return dataset.id

    # -------------------------------------------------------------------------
    # Sample Management
    # -------------------------------------------------------------------------

    def add_labeled_sample(
        self,
        dataset_id: int,
        document_hash: str,
        actual_doc_type: str,
        actual_category: str,
        metadata: Optional[dict] = None,
        source: str = "manual_label",
    ) -> int:
        """Add a labeled sample to a benchmark dataset.

        Args:
            dataset_id: Target dataset ID.
            document_hash: SHA-256 hash of the document content.
            actual_doc_type: Ground-truth document type.
            actual_category: Document category (income, assets, etc.).
            metadata: Optional extra context.
            source: How the sample was created.

        Returns:
            The ID of the new sample.
        """
        dataset = self.db.query(AIBenchmarkDataset).filter(
            AIBenchmarkDataset.id == dataset_id
        ).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        sample = AIBenchmarkSample(
            dataset_id=dataset_id,
            organization_id=dataset.organization_id,
            document_hash=document_hash,
            actual_doc_type=actual_doc_type,
            actual_category=actual_category or "",
            source=source,
            metadata_=metadata,
        )
        self.db.add(sample)

        # Update cached count
        dataset.sample_count = (dataset.sample_count or 0) + 1
        self.db.flush()

        logger.info(
            "Added benchmark sample id=%s dataset=%s type=%s",
            sample.id, dataset_id, actual_doc_type,
        )
        return sample.id

    # -------------------------------------------------------------------------
    # Auto-Collection from Corrections
    # -------------------------------------------------------------------------

    def auto_collect_from_corrections(
        self,
        org_id: int,
        days: int = 30,
        dataset_id: Optional[int] = None,
    ) -> int:
        """Auto-collect labeled samples from human corrections.

        Queries AIDocumentClassification records where is_correct=False and
        corrected_doc_type is set, then adds them as labeled samples.

        If no dataset_id is provided, uses or creates an auto-collection
        dataset named "Auto-Collected Corrections".

        Args:
            org_id: Organization ID for tenant scoping.
            days: Look back period in days.
            dataset_id: Target dataset (auto-created if None).

        Returns:
            Count of samples collected.
        """
        # Resolve or create the target dataset
        if dataset_id is None:
            dataset = self.db.query(AIBenchmarkDataset).filter(
                AIBenchmarkDataset.organization_id == org_id,
                AIBenchmarkDataset.name == "Auto-Collected Corrections",
            ).first()
            if not dataset:
                dataset_id = self.create_benchmark_dataset(
                    org_id=org_id,
                    name="Auto-Collected Corrections",
                    description="Automatically collected from human corrections to AI classifications",
                )
            else:
                dataset_id = dataset.id

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Find corrections not already in the dataset
        existing_hashes = set()
        existing = self.db.query(AIBenchmarkSample.document_hash).filter(
            AIBenchmarkSample.dataset_id == dataset_id,
        ).all()
        for row in existing:
            existing_hashes.add(row[0])

        # Query corrections
        corrections = self.db.query(AIDocumentClassification).filter(
            AIDocumentClassification.organization_id == org_id,
            AIDocumentClassification.is_correct == False,  # noqa: E712
            AIDocumentClassification.corrected_doc_type.isnot(None),
            AIDocumentClassification.created_at >= cutoff,
        ).all()

        collected = 0
        for correction in corrections:
            # Use document_id as a pseudo-hash if no real hash is available
            doc_hash = str(correction.document_id)
            if doc_hash in existing_hashes:
                continue

            # Determine category from the corrected doc type
            category = self._infer_category(correction.corrected_doc_type)

            self.add_labeled_sample(
                dataset_id=dataset_id,
                document_hash=doc_hash,
                actual_doc_type=correction.corrected_doc_type,
                actual_category=category,
                metadata={
                    "classification_id": correction.id,
                    "original_prediction": correction.predicted_doc_type,
                    "original_confidence": correction.prediction_confidence,
                    "corrected_by": correction.corrected_by,
                },
                source="human_correction",
            )
            existing_hashes.add(doc_hash)
            collected += 1

        logger.info(
            "Auto-collected %d samples from corrections for org=%s dataset=%s",
            collected, org_id, dataset_id,
        )
        return collected

    # -------------------------------------------------------------------------
    # Benchmark Execution
    # -------------------------------------------------------------------------

    def run_benchmark(
        self,
        dataset_id: int,
        classifier_version: str = "current",
    ) -> BenchmarkResult:
        """Run a benchmark evaluation against all samples in a dataset.

        Compares each sample's actual_doc_type against the AI prediction
        stored in AIDocumentClassification (matched by document_hash/document_id).

        Args:
            dataset_id: The dataset to benchmark against.
            classifier_version: Identifier for the classifier being evaluated.

        Returns:
            BenchmarkResult with accuracy, precision, recall, F1, confusion matrix.
        """
        dataset = self.db.query(AIBenchmarkDataset).filter(
            AIBenchmarkDataset.id == dataset_id,
        ).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        samples = self.db.query(AIBenchmarkSample).filter(
            AIBenchmarkSample.dataset_id == dataset_id,
        ).all()

        if not samples:
            raise ValueError(f"Dataset {dataset_id} has no samples")

        # Build predictions map: document_id (from hash) -> predicted_doc_type
        doc_ids = []
        for s in samples:
            try:
                doc_ids.append(int(s.document_hash))
            except (ValueError, TypeError):
                pass

        predictions_map: Dict[str, str] = {}
        if doc_ids:
            classifications = self.db.query(AIDocumentClassification).filter(
                AIDocumentClassification.document_id.in_(doc_ids),
                AIDocumentClassification.organization_id == dataset.organization_id,
            ).all()
            for c in classifications:
                predictions_map[str(c.document_id)] = c.predicted_doc_type

        # Calculate metrics
        correct = 0
        total = 0
        confusion: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # For precision/recall: track true positives, false positives, false negatives per type
        tp: Dict[str, int] = defaultdict(int)
        fp: Dict[str, int] = defaultdict(int)
        fn: Dict[str, int] = defaultdict(int)
        type_correct: Dict[str, int] = defaultdict(int)
        type_total: Dict[str, int] = defaultdict(int)

        for sample in samples:
            predicted = predictions_map.get(sample.document_hash)
            if predicted is None:
                # No prediction available, skip this sample
                continue

            actual = sample.actual_doc_type
            total += 1
            type_total[actual] += 1
            confusion[actual][predicted] += 1

            if predicted == actual:
                correct += 1
                tp[actual] += 1
                type_correct[actual] += 1
            else:
                fn[actual] += 1
                fp[predicted] += 1

        if total == 0:
            raise ValueError("No matched samples found for benchmark")

        accuracy = (correct / total) * 100.0

        # Calculate per-type metrics
        all_types = set(list(tp.keys()) + list(fp.keys()) + list(fn.keys()))
        precision_by_type: Dict[str, float] = {}
        recall_by_type: Dict[str, float] = {}
        f1_by_type: Dict[str, float] = {}
        per_type_accuracy: Dict[str, float] = {}

        for doc_type in sorted(all_types):
            tp_count = tp.get(doc_type, 0)
            fp_count = fp.get(doc_type, 0)
            fn_count = fn.get(doc_type, 0)

            precision = (tp_count / (tp_count + fp_count) * 100.0) if (tp_count + fp_count) > 0 else 0.0
            recall = (tp_count / (tp_count + fn_count) * 100.0) if (tp_count + fn_count) > 0 else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

            precision_by_type[doc_type] = precision
            recall_by_type[doc_type] = recall
            f1_by_type[doc_type] = f1

            total_for_type = type_total.get(doc_type, 0)
            if total_for_type > 0:
                per_type_accuracy[doc_type] = (type_correct.get(doc_type, 0) / total_for_type) * 100.0

        # Serialize confusion matrix (defaultdict -> plain dict)
        confusion_dict = {
            actual: dict(predicted_counts)
            for actual, predicted_counts in confusion.items()
        }

        # Update dataset with latest results
        dataset.last_benchmark_accuracy = accuracy
        dataset.last_benchmark_date = datetime.now(timezone.utc)
        self.db.flush()

        result = BenchmarkResult(
            accuracy=accuracy,
            precision_by_type=precision_by_type,
            recall_by_type=recall_by_type,
            f1_by_type=f1_by_type,
            confusion_matrix=confusion_dict,
            sample_count=total,
            classifier_version=classifier_version,
            per_type_accuracy=per_type_accuracy,
        )

        logger.info(
            "Benchmark run complete: dataset=%s accuracy=%.2f%% samples=%d",
            dataset_id, accuracy, total,
        )
        return result

    # -------------------------------------------------------------------------
    # Accuracy Trend
    # -------------------------------------------------------------------------

    def get_accuracy_trend(
        self,
        org_id: int,
        days: int = 90,
    ) -> List[dict]:
        """Get daily accuracy trend based on correction data.

        Calculates per-day accuracy as the ratio of is_correct=True
        classifications to total reviewed classifications.

        Args:
            org_id: Organization ID.
            days: Lookback period.

        Returns:
            List of dicts with date, accuracy, total, correct, incorrect.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Query daily accuracy from classifications that have feedback
        rows = self.db.query(
            func.date(AIDocumentClassification.created_at).label("day"),
            func.count().label("total"),
            func.sum(
                case(
                    (AIDocumentClassification.is_correct == True, 1),  # noqa: E712
                    else_=0,
                )
            ).label("correct_count"),
            func.sum(
                case(
                    (AIDocumentClassification.is_correct == False, 1),  # noqa: E712
                    else_=0,
                )
            ).label("incorrect_count"),
        ).filter(
            AIDocumentClassification.organization_id == org_id,
            AIDocumentClassification.is_correct.isnot(None),
            AIDocumentClassification.created_at >= cutoff,
        ).group_by(
            func.date(AIDocumentClassification.created_at),
        ).order_by(
            func.date(AIDocumentClassification.created_at),
        ).all()

        trend = []
        for row in rows:
            total = row.total or 0
            correct = row.correct_count or 0
            incorrect = row.incorrect_count or 0
            accuracy = (correct / total * 100.0) if total > 0 else 0.0
            trend.append({
                "date": str(row.day),
                "accuracy": round(accuracy, 2),
                "total_reviewed": total,
                "correct": correct,
                "incorrect": incorrect,
            })

        return trend

    # -------------------------------------------------------------------------
    # Confusion Matrix
    # -------------------------------------------------------------------------

    def get_confusion_matrix(
        self,
        org_id: int,
        days: int = 30,
    ) -> dict:
        """Get confusion matrix showing which doc types get confused.

        Only considers classifications where is_correct=False and
        corrected_doc_type is set.

        Args:
            org_id: Organization ID.
            days: Lookback period.

        Returns:
            Dict with matrix, most_confused pairs, and total_misclassifications.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        misclassifications = self.db.query(AIDocumentClassification).filter(
            AIDocumentClassification.organization_id == org_id,
            AIDocumentClassification.is_correct == False,  # noqa: E712
            AIDocumentClassification.corrected_doc_type.isnot(None),
            AIDocumentClassification.created_at >= cutoff,
        ).all()

        matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        pair_counts: Dict[tuple, int] = defaultdict(int)

        for m in misclassifications:
            actual = m.corrected_doc_type
            predicted = m.predicted_doc_type
            matrix[actual][predicted] += 1
            pair_counts[(actual, predicted)] += 1

        # Find most confused pairs
        sorted_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)
        most_confused = [
            {
                "actual": pair[0],
                "predicted_as": pair[1],
                "count": count,
            }
            for pair, count in sorted_pairs[:10]
        ]

        return {
            "matrix": {k: dict(v) for k, v in matrix.items()},
            "most_confused": most_confused,
            "total_misclassifications": len(misclassifications),
            "period_days": days,
        }

    # -------------------------------------------------------------------------
    # Confidence Calibration
    # -------------------------------------------------------------------------

    def get_confidence_calibration(
        self,
        org_id: int,
    ) -> dict:
        """Evaluate confidence score calibration.

        Groups classifications by confidence bucket (0-10, 10-20, ..., 90-100)
        and compares predicted confidence against actual accuracy at each level.

        A well-calibrated classifier should have predicted confidence close to
        actual accuracy: when it says 90% confidence, it should be correct ~90%.

        Args:
            org_id: Organization ID.

        Returns:
            Dict with buckets containing predicted_confidence, actual_accuracy,
            sample_count, and calibration_error.
        """
        # Only look at classifications with human feedback
        reviewed = self.db.query(AIDocumentClassification).filter(
            AIDocumentClassification.organization_id == org_id,
            AIDocumentClassification.is_correct.isnot(None),
        ).all()

        if not reviewed:
            return {
                "buckets": [],
                "total_reviewed": 0,
                "mean_calibration_error": 0.0,
                "is_well_calibrated": True,
            }

        # Group by confidence bucket (10-point buckets)
        buckets: Dict[int, dict] = {}
        for bucket_start in range(0, 100, 10):
            buckets[bucket_start] = {
                "total": 0,
                "correct": 0,
            }

        for classification in reviewed:
            confidence = classification.prediction_confidence or 0
            bucket = min(90, (confidence // 10) * 10)
            buckets[bucket]["total"] += 1
            if classification.is_correct:
                buckets[bucket]["correct"] += 1

        # Calculate per-bucket metrics
        result_buckets = []
        calibration_errors = []

        for bucket_start in range(0, 100, 10):
            data = buckets[bucket_start]
            total = data["total"]
            if total == 0:
                continue

            actual_accuracy = (data["correct"] / total) * 100.0
            predicted_confidence = bucket_start + 5  # Midpoint of bucket
            calibration_error = abs(actual_accuracy - predicted_confidence)
            calibration_errors.append(calibration_error)

            result_buckets.append({
                "confidence_range": f"{bucket_start}-{bucket_start + 10}",
                "predicted_confidence_midpoint": predicted_confidence,
                "actual_accuracy": round(actual_accuracy, 2),
                "sample_count": total,
                "correct_count": data["correct"],
                "calibration_error": round(calibration_error, 2),
            })

        mean_error = sum(calibration_errors) / len(calibration_errors) if calibration_errors else 0.0

        return {
            "buckets": result_buckets,
            "total_reviewed": len(reviewed),
            "mean_calibration_error": round(mean_error, 2),
            "is_well_calibrated": mean_error < 15.0,  # <15% mean error = well calibrated
        }

    # -------------------------------------------------------------------------
    # Full Benchmark Report
    # -------------------------------------------------------------------------

    def generate_benchmark_report(
        self,
        org_id: int,
    ) -> dict:
        """Generate a comprehensive benchmark report.

        Combines overall accuracy, per-type accuracy from the latest benchmark,
        accuracy trend, confusion matrix highlights, calibration analysis,
        and actionable recommendations.

        Args:
            org_id: Organization ID.

        Returns:
            Dict with all benchmark data and recommendations.
        """
        # Overall accuracy from reviewed classifications
        total_reviewed = self.db.query(func.count()).filter(
            AIDocumentClassification.organization_id == org_id,
            AIDocumentClassification.is_correct.isnot(None),
        ).scalar() or 0

        total_correct = self.db.query(func.count()).filter(
            AIDocumentClassification.organization_id == org_id,
            AIDocumentClassification.is_correct == True,  # noqa: E712
        ).scalar() or 0

        overall_accuracy = (total_correct / total_reviewed * 100.0) if total_reviewed > 0 else 0.0

        # Per-type accuracy from corrections
        type_stats = self.db.query(
            AIDocumentClassification.predicted_doc_type,
            func.count().label("total"),
            func.sum(
                case(
                    (AIDocumentClassification.is_correct == True, 1),  # noqa: E712
                    else_=0,
                )
            ).label("correct"),
        ).filter(
            AIDocumentClassification.organization_id == org_id,
            AIDocumentClassification.is_correct.isnot(None),
        ).group_by(
            AIDocumentClassification.predicted_doc_type,
        ).all()

        per_type_accuracy = {}
        weak_types = []
        for row in type_stats:
            total = row.total or 0
            correct = row.correct or 0
            acc = (correct / total * 100.0) if total > 0 else 0.0
            per_type_accuracy[row.predicted_doc_type] = {
                "accuracy": round(acc, 2),
                "total_reviewed": total,
                "correct": correct,
            }
            if acc < 80.0 and total >= 3:
                weak_types.append({
                    "doc_type": row.predicted_doc_type,
                    "accuracy": round(acc, 2),
                    "sample_count": total,
                })

        # Accuracy trend (last 30 days)
        trend = self.get_accuracy_trend(org_id, days=30)

        # Confusion highlights
        confusion = self.get_confusion_matrix(org_id, days=30)

        # Calibration
        calibration = self.get_confidence_calibration(org_id)

        # Latest benchmark dataset results
        latest_dataset = self.db.query(AIBenchmarkDataset).filter(
            AIBenchmarkDataset.organization_id == org_id,
            AIBenchmarkDataset.last_benchmark_date.isnot(None),
        ).order_by(
            AIBenchmarkDataset.last_benchmark_date.desc(),
        ).first()

        # Build recommendations
        recommendations = []
        if overall_accuracy < 85.0 and total_reviewed >= 10:
            recommendations.append(
                f"Overall accuracy is {overall_accuracy:.1f}% - below 85% target. "
                "Review classifier prompts and training data."
            )
        for wt in weak_types[:3]:
            recommendations.append(
                f"{wt['doc_type']} has low accuracy ({wt['accuracy']}% over {wt['sample_count']} samples). "
                "Consider adding more training examples for this type."
            )
        if confusion.get("most_confused"):
            top = confusion["most_confused"][0]
            recommendations.append(
                f"Most common confusion: {top['actual']} misclassified as "
                f"{top['predicted_as']} ({top['count']} times). "
                "Review classification criteria for these types."
            )
        if not calibration.get("is_well_calibrated", True):
            recommendations.append(
                f"Confidence scores are poorly calibrated "
                f"(mean error: {calibration['mean_calibration_error']}%). "
                "Consider adjusting confidence thresholds."
            )
        if total_reviewed < 50:
            recommendations.append(
                f"Only {total_reviewed} reviewed samples. "
                "Encourage more human review to build reliable benchmarks."
            )

        return {
            "overall_accuracy": round(overall_accuracy, 2),
            "total_reviewed": total_reviewed,
            "total_correct": total_correct,
            "per_type_accuracy": per_type_accuracy,
            "weak_types": weak_types,
            "accuracy_trend_30d": trend,
            "confusion_highlights": confusion.get("most_confused", [])[:5],
            "calibration": {
                "mean_error": calibration.get("mean_calibration_error", 0.0),
                "is_well_calibrated": calibration.get("is_well_calibrated", True),
            },
            "latest_benchmark": {
                "dataset_name": latest_dataset.name if latest_dataset else None,
                "accuracy": latest_dataset.last_benchmark_accuracy if latest_dataset else None,
                "date": latest_dataset.last_benchmark_date.isoformat() if latest_dataset and latest_dataset.last_benchmark_date else None,
                "sample_count": latest_dataset.sample_count if latest_dataset else 0,
            },
            "recommendations": recommendations,
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _infer_category(doc_type: str) -> str:
        """Infer document category from document type string."""
        income_types = {"PAYSTUB", "W2", "TAX_RETURN", "BUSINESS_TAX_RETURN", "PROFIT_LOSS", "BALANCE_SHEET"}
        asset_types = {"BANK_STATEMENT", "INVESTMENT_STATEMENT", "GIFT_LETTER"}
        property_types = {"PURCHASE_CONTRACT", "APPRAISAL", "TITLE_REPORT", "HOMEOWNERS_INSURANCE", "LEASE_AGREEMENT"}
        identity_types = {"DRIVERS_LICENSE"}
        credit_types = {"BANKRUPTCY_DISCHARGE"}
        special_types = {"LOE", "FHA_CERT", "VA_COE", "DD214"}

        upper = doc_type.upper()
        if upper in income_types:
            return "income"
        elif upper in asset_types:
            return "assets"
        elif upper in property_types:
            return "property"
        elif upper in identity_types:
            return "identity"
        elif upper in credit_types:
            return "credit"
        elif upper in special_types:
            return "special"
        return "other"
