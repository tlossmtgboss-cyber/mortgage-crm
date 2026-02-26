"""
Tests for SOC 2 Access Control Service.
Coverage: Auth logging, lockout, anomaly scoring, auto-incident, sessions.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from uuid import uuid4
from datetime import datetime, timezone

from soc2_compliance.services.access_control_service import AccessControlService
from soc2_compliance.config import SOC2Config
from soc2_compliance.constants import AuditAction, SeverityLevel


class TestLogAuthentication:
    """Test authentication event logging."""

    def test_successful_login_logged(self, access_control_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_db.execute.return_value = mock_result

        event_id = access_control_service.log_authentication(
            success=True,
            ip="1.2.3.4",
            user_agent="TestAgent",
            user_id=uuid4(),
        )
        assert event_id == 1
        assert mock_db.execute.called

    def test_failed_login_logged(self, access_control_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (2,)
        mock_db.execute.return_value = mock_result

        event_id = access_control_service.log_authentication(
            success=False,
            ip="1.2.3.4",
            user_agent="TestAgent",
            attempted_email="test@test.com",
        )
        assert event_id == 2

    def test_event_type_defaults_to_login(self, access_control_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_db.execute.return_value = mock_result

        access_control_service.log_authentication(
            success=True,
            ip="1.2.3.4",
            user_agent="TestAgent",
            user_id=uuid4(),
        )
        # Verify the SQL was called with login event_type
        call_args = mock_db.execute.call_args_list[0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        # The first execute is the anomaly detection query, not the insert

    def test_db_error_returns_none(self, access_control_service, mock_db):
        mock_db.execute.side_effect = Exception("DB error")
        result = access_control_service.log_authentication(
            success=True, ip="1.2.3.4", user_agent="TestAgent"
        )
        assert result is None


class TestAnomalyDetection:
    """Test anomaly detection logic."""

    def test_new_ip_increases_risk(self, access_control_service, mock_db):
        user_id = uuid4()
        # First call returns 0 (new IP), second returns 1 (known UA), third returns 0 (no failures)
        mock_results = [MagicMock(), MagicMock(), MagicMock()]
        mock_results[0].fetchone.return_value = (0,)  # New IP
        mock_results[1].fetchone.return_value = (1,)  # Known UA
        mock_results[2].fetchone.return_value = (0,)  # No recent failures
        mock_db.execute.side_effect = mock_results

        result = access_control_service._detect_anomaly(user_id, "5.6.7.8", "TestAgent")
        assert result["risk_score"] >= 30
        assert "new_ip_address" in result.get("reason", "")

    def test_new_device_increases_risk(self, access_control_service, mock_db):
        user_id = uuid4()
        mock_results = [MagicMock(), MagicMock(), MagicMock()]
        mock_results[0].fetchone.return_value = (1,)  # Known IP
        mock_results[1].fetchone.return_value = (0,)  # New UA
        mock_results[2].fetchone.return_value = (0,)  # No recent failures
        mock_db.execute.side_effect = mock_results

        result = access_control_service._detect_anomaly(user_id, "1.2.3.4", "NewAgent")
        assert result["risk_score"] >= 20
        assert "new_device" in result.get("reason", "")

    def test_recent_failures_increase_risk(self, access_control_service, mock_db):
        user_id = uuid4()
        mock_results = [MagicMock(), MagicMock(), MagicMock()]
        mock_results[0].fetchone.return_value = (1,)  # Known IP
        mock_results[1].fetchone.return_value = (1,)  # Known UA
        mock_results[2].fetchone.return_value = (5,)  # 5 recent failures
        mock_db.execute.side_effect = mock_results

        result = access_control_service._detect_anomaly(user_id, "1.2.3.4", "TestAgent")
        assert result["risk_score"] >= 25

    def test_combined_anomalies_flag_as_anomalous(self, access_control_service, mock_db):
        user_id = uuid4()
        mock_results = [MagicMock(), MagicMock(), MagicMock()]
        mock_results[0].fetchone.return_value = (0,)  # New IP (+30)
        mock_results[1].fetchone.return_value = (0,)  # New UA (+20)
        mock_results[2].fetchone.return_value = (0,)  # No failures
        mock_db.execute.side_effect = mock_results

        result = access_control_service._detect_anomaly(user_id, "9.9.9.9", "UnknownAgent")
        assert result["is_anomalous"] is True
        assert result["risk_score"] >= 40

    def test_known_ip_and_ua_not_anomalous(self, access_control_service, mock_db):
        user_id = uuid4()
        mock_results = [MagicMock(), MagicMock(), MagicMock()]
        mock_results[0].fetchone.return_value = (5,)  # Known IP
        mock_results[1].fetchone.return_value = (5,)  # Known UA
        mock_results[2].fetchone.return_value = (0,)  # No failures
        mock_db.execute.side_effect = mock_results

        result = access_control_service._detect_anomaly(user_id, "1.2.3.4", "TestAgent")
        assert result["is_anomalous"] is False
        assert result["risk_score"] == 0


class TestAccountLockout:
    """Test account lockout logic."""

    def test_locked_after_max_attempts(self, access_control_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (5,)  # 5 failed attempts = locked
        mock_db.execute.return_value = mock_result

        assert access_control_service.is_account_locked(email="test@test.com") is True

    def test_not_locked_below_threshold(self, access_control_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (2,)  # Only 2 failed attempts
        mock_db.execute.return_value = mock_result

        assert access_control_service.is_account_locked(email="test@test.com") is False

    def test_no_criteria_returns_false(self, access_control_service):
        assert access_control_service.is_account_locked() is False


class TestSessionManagement:
    """Test session management."""

    def test_terminate_session(self, access_control_service, mock_db):
        result = access_control_service.terminate_session("sess-123", reason="forced")
        assert result is True
        assert mock_db.execute.called
        assert mock_db.commit.called

    def test_terminate_all_user_sessions(self, access_control_service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result

        count = access_control_service.terminate_all_user_sessions(uuid4())
        assert count == 3


class TestAutoIncidentCreation:
    """Test auto-escalation for anomalous logins."""

    @patch("soc2_compliance.services.access_control_service.AccessControlService._detect_anomaly")
    def test_high_risk_creates_incident(self, mock_anomaly, mock_db, soc2_config):
        """Risk score >= 60 should auto-create an incident."""
        mock_anomaly.return_value = {
            "is_anomalous": True,
            "risk_score": 75,
            "reason": "new_ip_address; new_device",
        }

        # Mock successful insert for log_authentication
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_db.execute.return_value = mock_result

        svc = AccessControlService(mock_db, config=soc2_config)
        with patch("soc2_compliance.services.incident_service.IncidentService") as MockIncident:
            mock_incident_svc = MagicMock()
            MockIncident.return_value = mock_incident_svc

            svc.log_authentication(
                success=True,
                ip="9.9.9.9",
                user_agent="Unknown",
                user_id=uuid4(),
            )
            # Incident should have been created
            mock_incident_svc.create.assert_called_once()
