"""
Tests for SOC 2 Compliance Reporter.
Coverage: Full report, A1/privacy sections, executive summary.
"""
import pytest
from unittest.mock import MagicMock, call
from uuid import uuid4
from datetime import datetime, timezone

from soc2_compliance.services.compliance_reporter import ComplianceReporter


@pytest.fixture
def reporter(mock_db):
    return ComplianceReporter(mock_db)


@pytest.fixture
def report_params():
    return {
        "tenant_id": uuid4(),
        "start_date": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "end_date": datetime(2025, 12, 31, tzinfo=timezone.utc),
    }


class TestFullReport:
    """Test full report generation."""

    def test_report_has_all_sections(self, reporter, mock_db, report_params):
        mock_row = MagicMock()
        mock_row._mapping = {"total": 0}
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        report = reporter.generate_full_report(**report_params)

        assert "report_metadata" in report
        assert "executive_summary" in report
        assert "cc6_access_controls" in report
        assert "cc7_incident_response" in report
        assert "cc8_change_management" in report
        assert "c1_confidentiality" in report
        assert "cc4_monitoring" in report
        assert "a1_availability" in report
        assert "p1_privacy" in report
        assert "compliance_checks" in report
        assert "data_retention" in report

    def test_report_metadata(self, reporter, mock_db, report_params):
        mock_row = MagicMock()
        mock_row._mapping = {"total": 0}
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        report = reporter.generate_full_report(**report_params)

        meta = report["report_metadata"]
        assert meta["report_type"] == "SOC 2 Type II Evidence Report"
        assert meta["tenant_id"] == str(report_params["tenant_id"])


class TestAvailabilityEvidence:
    """Test A1 availability evidence section."""

    def test_availability_includes_rate_limits(self, reporter, mock_db, report_params):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = reporter._availability_evidence(
            report_params["tenant_id"],
            report_params["start_date"],
            report_params["end_date"],
        )
        assert "rate_limit_events" in result
        assert "daily_request_summary" in result
        assert "availability_incidents" in result


class TestPrivacyEvidence:
    """Test P1-P8 privacy evidence section."""

    def test_privacy_includes_classification(self, reporter, mock_db, report_params):
        mock_row = MagicMock()
        mock_row._mapping = {
            "total_classified": 50,
            "pii_columns": 15,
            "pii_encrypted": 12,
            "with_retention_policy": 40,
        }
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = reporter._privacy_evidence(
            report_params["tenant_id"],
            report_params["start_date"],
            report_params["end_date"],
        )
        assert "data_classification_coverage" in result
        assert "retention_enforcement_history" in result
        assert "pii_access_by_role" in result


class TestExecutiveSummary:
    """Test executive summary generation."""

    def test_summary_has_all_categories(self, reporter, mock_db, report_params):
        mock_row = MagicMock()
        mock_row._mapping = {
            "total_audit_events": 1000,
            "unique_users": 10,
            "high_severity_events": 2,
            "pii_events": 50,
            "successful_logins": 500,
            "failed_logins": 20,
            "anomalous_events": 3,
            "total_incidents": 1,
            "critical_incidents": 0,
            "data_breaches": 0,
            "resolved_incidents": 1,
            "total_changes": 25,
            "successful_changes": 24,
            "rollbacks": 1,
        }
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        summary = reporter._executive_summary(
            report_params["tenant_id"],
            report_params["start_date"],
            report_params["end_date"],
        )
        assert "audit" in summary
        assert "access" in summary
        assert "incidents" in summary
        assert "changes" in summary
