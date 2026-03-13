"""
Tests for AI Classification Benchmarking Service

Covers:
- Benchmark dataset creation
- Sample collection from human corrections
- Benchmark run with known data (accuracy, precision, recall, F1)
- Confusion matrix generation
- Confidence calibration analysis
- Accuracy trend tracking
- Full report generation

Uses in-memory SQLite database with mock data to avoid external dependencies.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import Base
from database.models.ai_benchmark import AIBenchmarkDataset, AIBenchmarkSample
from database.models.document_intelligence import AIDocumentClassification
from services.smart_docs.ai_benchmarking_service import AIBenchmarkingService, BenchmarkResult


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def bench_engine():
    """Create an in-memory SQLite engine with benchmark tables."""
    engine = create_engine("sqlite:///:memory:")
    # Create only the tables we need
    for table_name in ("ai_benchmark_datasets", "ai_benchmark_samples", "ai_document_classifications"):
        table = Base.metadata.tables.get(table_name)
        if table is not None:
            table.create(bind=engine, checkfirst=True)
    return engine


@pytest.fixture
def bench_session(bench_engine):
    """Create a fresh session for each test, rolling back after."""
    Session = sessionmaker(bind=bench_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def service(bench_session):
    """AIBenchmarkingService instance."""
    return AIBenchmarkingService(bench_session)


@pytest.fixture
def sample_classifications(bench_session):
    """Seed AIDocumentClassification records with known outcomes."""
    org_id = 1
    now = datetime.now(timezone.utc)
    records = [
        # Correct predictions
        AIDocumentClassification(
            id=100 + i,
            organization_id=org_id,
            document_id=1000 + i,
            predicted_doc_type="W2",
            prediction_confidence=92,
            is_correct=True,
            created_at=now - timedelta(days=i),
        )
        for i in range(5)
    ] + [
        # Correct PAYSTUB predictions
        AIDocumentClassification(
            id=200 + i,
            organization_id=org_id,
            document_id=2000 + i,
            predicted_doc_type="PAYSTUB",
            prediction_confidence=88,
            is_correct=True,
            created_at=now - timedelta(days=i),
        )
        for i in range(3)
    ] + [
        # Incorrect predictions (W2 predicted as PAYSTUB)
        AIDocumentClassification(
            id=300,
            organization_id=org_id,
            document_id=3000,
            predicted_doc_type="PAYSTUB",
            prediction_confidence=65,
            is_correct=False,
            corrected_doc_type="W2",
            corrected_by="admin@test.com",
            corrected_at=now,
            created_at=now - timedelta(days=2),
        ),
        AIDocumentClassification(
            id=301,
            organization_id=org_id,
            document_id=3001,
            predicted_doc_type="PAYSTUB",
            prediction_confidence=55,
            is_correct=False,
            corrected_doc_type="W2",
            corrected_by="admin@test.com",
            corrected_at=now,
            created_at=now - timedelta(days=3),
        ),
        # Incorrect prediction (BANK_STATEMENT predicted as TAX_RETURN)
        AIDocumentClassification(
            id=302,
            organization_id=org_id,
            document_id=3002,
            predicted_doc_type="TAX_RETURN",
            prediction_confidence=45,
            is_correct=False,
            corrected_doc_type="BANK_STATEMENT",
            corrected_by="admin@test.com",
            corrected_at=now,
            created_at=now - timedelta(days=1),
        ),
    ]
    for r in records:
        bench_session.merge(r)
    bench_session.flush()
    return records


# =============================================================================
# DATASET CREATION TESTS
# =============================================================================

@pytest.mark.unit
class TestDatasetCreation:
    """Test benchmark dataset CRUD operations."""

    def test_create_dataset(self, service, bench_session):
        """Creating a dataset returns a valid ID and persists to DB."""
        dataset_id = service.create_benchmark_dataset(
            org_id=1,
            name="Test Dataset",
            description="A test benchmark dataset",
        )
        assert dataset_id > 0

        dataset = bench_session.query(AIBenchmarkDataset).get(dataset_id)
        assert dataset is not None
        assert dataset.name == "Test Dataset"
        assert dataset.description == "A test benchmark dataset"
        assert dataset.organization_id == 1
        assert dataset.sample_count == 0

    def test_add_labeled_sample(self, service, bench_session):
        """Adding a sample increments the dataset count."""
        dataset_id = service.create_benchmark_dataset(org_id=1, name="Sample Test")
        sample_id = service.add_labeled_sample(
            dataset_id=dataset_id,
            document_hash="abc123def456",
            actual_doc_type="W2",
            actual_category="income",
            metadata={"filename": "w2_2025.pdf"},
        )
        assert sample_id > 0

        sample = bench_session.query(AIBenchmarkSample).get(sample_id)
        assert sample.actual_doc_type == "W2"
        assert sample.actual_category == "income"
        assert sample.source == "manual_label"

        dataset = bench_session.query(AIBenchmarkDataset).get(dataset_id)
        assert dataset.sample_count == 1

    def test_add_sample_to_nonexistent_dataset_raises(self, service):
        """Adding a sample to a nonexistent dataset raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            service.add_labeled_sample(
                dataset_id=99999,
                document_hash="xyz",
                actual_doc_type="W2",
                actual_category="income",
            )


# =============================================================================
# AUTO-COLLECTION TESTS
# =============================================================================

@pytest.mark.unit
class TestAutoCollection:
    """Test auto-collection of samples from human corrections."""

    def test_collect_from_corrections(self, service, bench_session, sample_classifications):
        """Auto-collection should find corrected classifications and create samples."""
        dataset_id = service.create_benchmark_dataset(org_id=1, name="Collection Test")
        collected = service.auto_collect_from_corrections(
            org_id=1,
            days=30,
            dataset_id=dataset_id,
        )
        # Should collect 3 corrections (IDs 300, 301, 302)
        assert collected == 3

        samples = bench_session.query(AIBenchmarkSample).filter(
            AIBenchmarkSample.dataset_id == dataset_id,
        ).all()
        assert len(samples) == 3

        # Verify sources are all human_correction
        for s in samples:
            assert s.source == "human_correction"

    def test_collect_deduplicates(self, service, bench_session, sample_classifications):
        """Running collection twice should not duplicate samples."""
        dataset_id = service.create_benchmark_dataset(org_id=1, name="Dedup Test")
        first = service.auto_collect_from_corrections(org_id=1, days=30, dataset_id=dataset_id)
        second = service.auto_collect_from_corrections(org_id=1, days=30, dataset_id=dataset_id)
        assert first == 3
        assert second == 0  # No new samples

    def test_collect_creates_default_dataset(self, service, bench_session, sample_classifications):
        """When no dataset_id is given, auto-creates 'Auto-Collected Corrections'."""
        collected = service.auto_collect_from_corrections(org_id=1, days=30)
        assert collected >= 0

        dataset = bench_session.query(AIBenchmarkDataset).filter(
            AIBenchmarkDataset.name == "Auto-Collected Corrections",
            AIBenchmarkDataset.organization_id == 1,
        ).first()
        assert dataset is not None


# =============================================================================
# BENCHMARK RUN TESTS
# =============================================================================

@pytest.mark.unit
class TestBenchmarkRun:
    """Test running benchmarks against labeled datasets."""

    def _setup_benchmark_dataset(self, service, bench_session, sample_classifications):
        """Helper to create a dataset with matched samples."""
        dataset_id = service.create_benchmark_dataset(org_id=1, name="Run Test")

        # Add samples that correspond to classifications in sample_classifications
        # 5 W2 samples (doc_ids 1000-1004) - classifier predicts W2 correctly
        for i in range(5):
            service.add_labeled_sample(
                dataset_id=dataset_id,
                document_hash=str(1000 + i),
                actual_doc_type="W2",
                actual_category="income",
            )
        # 3 PAYSTUB samples (doc_ids 2000-2002) - classifier predicts PAYSTUB correctly
        for i in range(3):
            service.add_labeled_sample(
                dataset_id=dataset_id,
                document_hash=str(2000 + i),
                actual_doc_type="PAYSTUB",
                actual_category="income",
            )
        # 2 W2 samples that classifier predicted as PAYSTUB (doc_ids 3000, 3001)
        service.add_labeled_sample(
            dataset_id=dataset_id,
            document_hash="3000",
            actual_doc_type="W2",
            actual_category="income",
        )
        service.add_labeled_sample(
            dataset_id=dataset_id,
            document_hash="3001",
            actual_doc_type="W2",
            actual_category="income",
        )
        # 1 BANK_STATEMENT that classifier predicted as TAX_RETURN (doc_id 3002)
        service.add_labeled_sample(
            dataset_id=dataset_id,
            document_hash="3002",
            actual_doc_type="BANK_STATEMENT",
            actual_category="assets",
        )

        return dataset_id

    def test_benchmark_accuracy(self, service, bench_session, sample_classifications):
        """Benchmark should calculate correct overall accuracy."""
        dataset_id = self._setup_benchmark_dataset(service, bench_session, sample_classifications)
        result = service.run_benchmark(dataset_id)

        # 5 W2 correct + 3 PAYSTUB correct = 8 correct out of 11 total
        # (2 W2 misclassified as PAYSTUB + 1 BANK_STATEMENT as TAX_RETURN = 3 wrong)
        assert isinstance(result, BenchmarkResult)
        expected_accuracy = (8 / 11) * 100.0
        assert abs(result.accuracy - expected_accuracy) < 0.1
        assert result.sample_count == 11

    def test_benchmark_precision_recall(self, service, bench_session, sample_classifications):
        """Precision and recall should be calculated per type."""
        dataset_id = self._setup_benchmark_dataset(service, bench_session, sample_classifications)
        result = service.run_benchmark(dataset_id)

        # W2: tp=5, fp=0, fn=2 -> precision=100%, recall=5/7=71.4%
        assert result.precision_by_type.get("W2", 0) == pytest.approx(100.0, abs=0.1)
        assert result.recall_by_type.get("W2", 0) == pytest.approx(71.4, abs=0.2)

        # PAYSTUB: tp=3, fp=2, fn=0 -> precision=3/5=60%, recall=100%
        assert result.precision_by_type.get("PAYSTUB", 0) == pytest.approx(60.0, abs=0.1)
        assert result.recall_by_type.get("PAYSTUB", 0) == pytest.approx(100.0, abs=0.1)

    def test_benchmark_confusion_matrix(self, service, bench_session, sample_classifications):
        """Confusion matrix should record actual vs predicted counts."""
        dataset_id = self._setup_benchmark_dataset(service, bench_session, sample_classifications)
        result = service.run_benchmark(dataset_id)

        # W2 actual: 5 predicted as W2, 2 predicted as PAYSTUB
        assert result.confusion_matrix.get("W2", {}).get("W2") == 5
        assert result.confusion_matrix.get("W2", {}).get("PAYSTUB") == 2

        # BANK_STATEMENT actual: 1 predicted as TAX_RETURN
        assert result.confusion_matrix.get("BANK_STATEMENT", {}).get("TAX_RETURN") == 1

    def test_benchmark_f1_scores(self, service, bench_session, sample_classifications):
        """F1 scores should be calculated correctly."""
        dataset_id = self._setup_benchmark_dataset(service, bench_session, sample_classifications)
        result = service.run_benchmark(dataset_id)

        # F1 for each type should be between 0 and 100
        for doc_type, f1 in result.f1_by_type.items():
            assert 0 <= f1 <= 100, f"F1 for {doc_type} out of range: {f1}"

        # W2 F1: 2 * (100 * 71.4) / (100 + 71.4) = 83.3
        assert result.f1_by_type.get("W2", 0) == pytest.approx(83.3, abs=0.5)

    def test_benchmark_updates_dataset(self, service, bench_session, sample_classifications):
        """Running a benchmark should update dataset's last accuracy and date."""
        dataset_id = self._setup_benchmark_dataset(service, bench_session, sample_classifications)
        result = service.run_benchmark(dataset_id)

        dataset = bench_session.query(AIBenchmarkDataset).get(dataset_id)
        assert dataset.last_benchmark_accuracy is not None
        assert abs(dataset.last_benchmark_accuracy - result.accuracy) < 0.01
        assert dataset.last_benchmark_date is not None

    def test_benchmark_empty_dataset_raises(self, service, bench_session):
        """Running benchmark on an empty dataset should raise ValueError."""
        dataset_id = service.create_benchmark_dataset(org_id=1, name="Empty")
        with pytest.raises(ValueError, match="no samples"):
            service.run_benchmark(dataset_id)

    def test_benchmark_result_serialization(self, service, bench_session, sample_classifications):
        """BenchmarkResult.to_dict() should produce a JSON-serializable dict."""
        dataset_id = self._setup_benchmark_dataset(service, bench_session, sample_classifications)
        result = service.run_benchmark(dataset_id)
        d = result.to_dict()

        assert isinstance(d, dict)
        assert "accuracy" in d
        assert "confusion_matrix" in d
        assert "precision_by_type" in d
        assert isinstance(d["accuracy"], float)


# =============================================================================
# ACCURACY TREND TESTS
# =============================================================================

@pytest.mark.unit
class TestAccuracyTrend:
    """Test accuracy trend tracking."""

    def test_get_accuracy_trend(self, service, bench_session, sample_classifications):
        """Should return daily accuracy data points."""
        trend = service.get_accuracy_trend(org_id=1, days=30)

        assert isinstance(trend, list)
        assert len(trend) > 0

        for point in trend:
            assert "date" in point
            assert "accuracy" in point
            assert "total_reviewed" in point
            assert 0 <= point["accuracy"] <= 100
            assert point["total_reviewed"] > 0

    def test_trend_empty_org(self, service, bench_session):
        """Trend for an org with no data should return empty list."""
        trend = service.get_accuracy_trend(org_id=99999, days=30)
        assert trend == []


# =============================================================================
# CONFUSION MATRIX TESTS
# =============================================================================

@pytest.mark.unit
class TestConfusionMatrix:
    """Test confusion matrix generation."""

    def test_confusion_matrix_structure(self, service, bench_session, sample_classifications):
        """Confusion matrix should have correct structure."""
        result = service.get_confusion_matrix(org_id=1, days=30)

        assert "matrix" in result
        assert "most_confused" in result
        assert "total_misclassifications" in result
        assert result["total_misclassifications"] == 3

    def test_most_confused_pairs(self, service, bench_session, sample_classifications):
        """Most confused pairs should be ordered by frequency."""
        result = service.get_confusion_matrix(org_id=1, days=30)

        pairs = result["most_confused"]
        assert len(pairs) > 0
        # W2 -> PAYSTUB confusion (2 times) should be first
        assert pairs[0]["actual"] == "W2"
        assert pairs[0]["predicted_as"] == "PAYSTUB"
        assert pairs[0]["count"] == 2

    def test_confusion_matrix_empty_org(self, service, bench_session):
        """Confusion matrix for org with no misclassifications should be empty."""
        result = service.get_confusion_matrix(org_id=99999, days=30)
        assert result["total_misclassifications"] == 0
        assert result["most_confused"] == []


# =============================================================================
# CALIBRATION TESTS
# =============================================================================

@pytest.mark.unit
class TestCalibration:
    """Test confidence calibration analysis."""

    def test_calibration_buckets(self, service, bench_session, sample_classifications):
        """Calibration should return bucket-level accuracy vs confidence."""
        result = service.get_confidence_calibration(org_id=1)

        assert "buckets" in result
        assert "total_reviewed" in result
        assert "mean_calibration_error" in result
        assert "is_well_calibrated" in result
        assert result["total_reviewed"] > 0

        for bucket in result["buckets"]:
            assert "confidence_range" in bucket
            assert "actual_accuracy" in bucket
            assert "sample_count" in bucket
            assert "calibration_error" in bucket

    def test_calibration_empty_org(self, service, bench_session):
        """Calibration for org with no data should return empty buckets."""
        result = service.get_confidence_calibration(org_id=99999)
        assert result["buckets"] == []
        assert result["total_reviewed"] == 0
        assert result["is_well_calibrated"] is True


# =============================================================================
# REPORT TESTS
# =============================================================================

@pytest.mark.unit
class TestBenchmarkReport:
    """Test full benchmark report generation."""

    def test_report_structure(self, service, bench_session, sample_classifications):
        """Report should contain all expected sections."""
        report = service.generate_benchmark_report(org_id=1)

        assert "overall_accuracy" in report
        assert "total_reviewed" in report
        assert "per_type_accuracy" in report
        assert "weak_types" in report
        assert "accuracy_trend_30d" in report
        assert "confusion_highlights" in report
        assert "calibration" in report
        assert "recommendations" in report
        assert "latest_benchmark" in report

    def test_report_accuracy_values(self, service, bench_session, sample_classifications):
        """Report overall accuracy should match manual calculation."""
        report = service.generate_benchmark_report(org_id=1)

        total = report["total_reviewed"]
        correct = report["total_correct"]
        assert total > 0
        expected = correct / total * 100.0
        assert abs(report["overall_accuracy"] - expected) < 0.01

    def test_report_recommendations(self, service, bench_session, sample_classifications):
        """Report should generate actionable recommendations."""
        report = service.generate_benchmark_report(org_id=1)

        # Should have at least one recommendation (confusion or sample count)
        assert isinstance(report["recommendations"], list)

    def test_report_empty_org(self, service, bench_session):
        """Report for org with no data should still return valid structure."""
        report = service.generate_benchmark_report(org_id=99999)
        assert report["overall_accuracy"] == 0
        assert report["total_reviewed"] == 0


# =============================================================================
# CATEGORY INFERENCE TESTS
# =============================================================================

@pytest.mark.unit
class TestCategoryInference:
    """Test the _infer_category helper method."""

    def test_income_types(self):
        """Income document types should map to 'income' category."""
        for doc_type in ("W2", "PAYSTUB", "TAX_RETURN", "PROFIT_LOSS"):
            assert AIBenchmarkingService._infer_category(doc_type) == "income"

    def test_asset_types(self):
        """Asset document types should map to 'assets' category."""
        for doc_type in ("BANK_STATEMENT", "INVESTMENT_STATEMENT", "GIFT_LETTER"):
            assert AIBenchmarkingService._infer_category(doc_type) == "assets"

    def test_property_types(self):
        """Property document types should map to 'property' category."""
        for doc_type in ("PURCHASE_CONTRACT", "APPRAISAL", "TITLE_REPORT"):
            assert AIBenchmarkingService._infer_category(doc_type) == "property"

    def test_unknown_type(self):
        """Unknown document types should map to 'other' category."""
        assert AIBenchmarkingService._infer_category("SOME_UNKNOWN_TYPE") == "other"
