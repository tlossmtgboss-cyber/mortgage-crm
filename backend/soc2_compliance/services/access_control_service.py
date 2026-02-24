"""
Access Control Service — Authentication logging, lockout, anomaly detection.
SOC 2 Criteria: CC6 (Access Controls)

Tracks all authentication events, enforces account lockout policies,
and detects anomalous access patterns.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import SOC2Config
from ..constants import AuditAction, SeverityLevel

logger = logging.getLogger("soc2.access_control")


class AccessControlService:
    """
    Authentication and access control auditing.

    Usage:
        access_svc = AccessControlService(db)

        # Log successful login
        access_svc.log_authentication(
            user_id=user.id, success=True,
            ip="1.2.3.4", user_agent="Mozilla/5.0..."
        )

        # Check if account is locked
        is_locked = access_svc.is_account_locked(email="user@example.com")
    """

    def __init__(self, db: Session, config: Optional[SOC2Config] = None):
        self.db = db
        self.config = config or SOC2Config.from_env()

    def log_authentication(
        self,
        success: bool,
        ip: str,
        user_agent: str,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        attempted_email: Optional[str] = None,
        event_type: Optional[str] = None,
        auth_method: str = "password",
        mfa_method: Optional[str] = None,
        session_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
        geo_location: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
    ) -> Optional[int]:
        """Log an authentication event and check for anomalies."""
        if event_type is None:
            event_type = AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED

        # Run anomaly detection
        is_anomalous = False
        anomaly_reason = None
        risk_score = 0

        if success and user_id:
            anomaly_result = self._detect_anomaly(user_id, ip, user_agent)
            is_anomalous = anomaly_result["is_anomalous"]
            anomaly_reason = anomaly_result.get("reason")
            risk_score = anomaly_result.get("risk_score", 0)

        try:
            result = self.db.execute(
                text("""
                    INSERT INTO soc2_access_event (
                        timestamp, user_id, attempted_email, tenant_id,
                        event_type, success, failure_reason,
                        auth_method, mfa_method, session_id,
                        ip_address, user_agent, geo_location, device_fingerprint,
                        is_anomalous, anomaly_reason, risk_score
                    ) VALUES (
                        :timestamp, :user_id, :attempted_email, :tenant_id,
                        :event_type, :success, :failure_reason,
                        :auth_method, :mfa_method, :session_id,
                        :ip_address::inet, :user_agent, :geo_location, :device_fingerprint,
                        :is_anomalous, :anomaly_reason, :risk_score
                    ) RETURNING id
                """),
                {
                    "timestamp": datetime.now(timezone.utc),
                    "user_id": str(user_id) if user_id else None,
                    "attempted_email": attempted_email,
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "event_type": event_type,
                    "success": success,
                    "failure_reason": failure_reason,
                    "auth_method": auth_method,
                    "mfa_method": mfa_method,
                    "session_id": session_id,
                    "ip_address": ip,
                    "user_agent": user_agent,
                    "geo_location": geo_location,
                    "device_fingerprint": device_fingerprint,
                    "is_anomalous": is_anomalous,
                    "anomaly_reason": anomaly_reason,
                    "risk_score": risk_score,
                }
            )
            self.db.commit()
            row = result.fetchone()
            event_id = row[0] if row else None
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to log auth event: {e}")
            return None

        # Check if we need to log lockout
        if not success and attempted_email:
            self._check_lockout(attempted_email, ip)

        # Log high-risk anomalous logins
        if is_anomalous:
            logger.warning(
                "anomalous_login_detected",
                extra={
                    "user_id": str(user_id),
                    "ip": ip,
                    "risk_score": risk_score,
                    "reason": anomaly_reason,
                }
            )

        return event_id

    def is_account_locked(
        self,
        email: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> bool:
        """
        Check if an account or IP is locked due to excessive failed attempts.
        """
        lockout_window = datetime.now(timezone.utc) - timedelta(
            minutes=self.config.lockout_duration_minutes
        )

        conditions = []
        params: Dict[str, Any] = {
            "lockout_window": lockout_window,
            "max_attempts": self.config.max_login_attempts,
        }

        if email:
            conditions.append("attempted_email = :email")
            params["email"] = email
        if ip:
            conditions.append("ip_address = :ip::inet")
            params["ip"] = ip

        if not conditions:
            return False

        where = " OR ".join(conditions)

        result = self.db.execute(
            text(f"""
                SELECT COUNT(*) as failed_count
                FROM soc2_access_event
                WHERE ({where})
                  AND success = FALSE
                  AND timestamp > :lockout_window
            """),
            params
        )
        row = result.fetchone()
        failed_count = row[0] if row else 0

        return failed_count >= self.config.max_login_attempts

    def get_failed_login_count(
        self,
        email: str,
        window_minutes: Optional[int] = None,
    ) -> int:
        """Get count of failed logins for an email within a time window."""
        window = window_minutes or self.config.lockout_duration_minutes
        since = datetime.now(timezone.utc) - timedelta(minutes=window)

        result = self.db.execute(
            text("""
                SELECT COUNT(*) FROM soc2_access_event
                WHERE attempted_email = :email
                  AND success = FALSE
                  AND timestamp > :since
            """),
            {"email": email, "since": since}
        )
        row = result.fetchone()
        return row[0] if row else 0

    def get_user_sessions(self, user_id: UUID) -> List[Dict]:
        """Get active sessions for a user."""
        result = self.db.execute(
            text("""
                SELECT id, created_at, last_activity, ip_address, user_agent
                FROM soc2_active_session
                WHERE user_id = :user_id AND is_active = TRUE
                ORDER BY last_activity DESC
            """),
            {"user_id": str(user_id)}
        )
        return [dict(row._mapping) for row in result.fetchall()]

    def terminate_session(
        self,
        session_id: str,
        reason: str = "forced",
        terminated_by: Optional[UUID] = None,
    ) -> bool:
        """Terminate a specific session."""
        self.db.execute(
            text("""
                UPDATE soc2_active_session
                SET is_active = FALSE, terminated_reason = :reason
                WHERE id = :session_id
            """),
            {"session_id": session_id, "reason": reason}
        )
        self.db.commit()

        logger.info(
            "session_terminated",
            extra={
                "session_id": session_id,
                "reason": reason,
                "terminated_by": str(terminated_by) if terminated_by else "system",
            }
        )
        return True

    def terminate_all_user_sessions(
        self,
        user_id: UUID,
        reason: str = "security_action",
        except_session_id: Optional[str] = None,
    ) -> int:
        """Terminate all sessions for a user (e.g., after password change)."""
        params: Dict[str, Any] = {"user_id": str(user_id), "reason": reason}
        exception_clause = ""
        if except_session_id:
            exception_clause = "AND id != :except_session"
            params["except_session"] = except_session_id

        result = self.db.execute(
            text(f"""
                UPDATE soc2_active_session
                SET is_active = FALSE, terminated_reason = :reason
                WHERE user_id = :user_id AND is_active = TRUE {exception_clause}
            """),
            params
        )
        self.db.commit()
        return result.rowcount

    def get_access_summary(
        self,
        tenant_id: UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """Generate access event summary for compliance reporting."""
        result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_events,
                    COUNT(*) FILTER (WHERE success = TRUE AND event_type = 'login') as successful_logins,
                    COUNT(*) FILTER (WHERE success = FALSE) as failed_logins,
                    COUNT(*) FILTER (WHERE is_anomalous = TRUE) as anomalous_events,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(DISTINCT ip_address) as unique_ips,
                    AVG(risk_score) FILTER (WHERE risk_score > 0) as avg_risk_score
                FROM soc2_access_event
                WHERE tenant_id = :tenant_id
                  AND timestamp BETWEEN :start_time AND :end_time
            """),
            {
                "tenant_id": str(tenant_id),
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        row = result.fetchone()
        return dict(row._mapping) if row else {}

    def _detect_anomaly(
        self,
        user_id: UUID,
        ip: str,
        user_agent: str,
    ) -> Dict[str, Any]:
        """
        Basic anomaly detection for login events.
        Checks for:
        - New IP address for this user
        - New user agent for this user
        - Multiple failed attempts before success
        """
        risk_score = 0
        reasons = []

        try:
            # Check if this IP has been used before by this user
            result = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM soc2_access_event
                    WHERE user_id = :user_id
                      AND ip_address = :ip::inet
                      AND success = TRUE
                      AND timestamp > NOW() - INTERVAL '90 days'
                """),
                {"user_id": str(user_id), "ip": ip}
            )
            ip_count = result.fetchone()[0]
            if ip_count == 0:
                risk_score += 30
                reasons.append("new_ip_address")

            # Check if user agent is new
            result = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM soc2_access_event
                    WHERE user_id = :user_id
                      AND user_agent = :user_agent
                      AND success = TRUE
                      AND timestamp > NOW() - INTERVAL '90 days'
                """),
                {"user_id": str(user_id), "user_agent": user_agent}
            )
            ua_count = result.fetchone()[0]
            if ua_count == 0:
                risk_score += 20
                reasons.append("new_device")

            # Check for recent failed attempts
            result = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM soc2_access_event
                    WHERE user_id = :user_id
                      AND success = FALSE
                      AND timestamp > NOW() - INTERVAL '1 hour'
                """),
                {"user_id": str(user_id)}
            )
            recent_failures = result.fetchone()[0]
            if recent_failures >= 3:
                risk_score += 25
                reasons.append(f"recent_failures:{recent_failures}")
        except Exception as e:
            logger.debug(f"Anomaly detection query failed (tables may not exist yet): {e}")

        return {
            "is_anomalous": risk_score >= 40,
            "risk_score": min(risk_score, 100),
            "reason": "; ".join(reasons) if reasons else None,
        }

    def _check_lockout(self, email: str, ip: str) -> None:
        """Check if lockout threshold is reached and log accordingly."""
        failed_count = self.get_failed_login_count(email)

        if failed_count >= self.config.max_login_attempts:
            logger.warning(
                "account_lockout_triggered",
                extra={
                    "email": email,
                    "ip": ip,
                    "failed_attempts": failed_count,
                    "lockout_duration_minutes": self.config.lockout_duration_minutes,
                }
            )
