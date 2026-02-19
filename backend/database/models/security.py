"""
Security Models

Models for audit logging, user sessions, and security monitoring.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.security import AuditLog, UserSession, EmergencyRevocation

    # Query audit logs
    logs = db.query(AuditLog).filter(AuditLog.user_id == user_id).all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship

# Import Base from the db module
from db import Base


# ============================================================================
# AUDIT LOGGING
# ============================================================================

class AuditLog(Base):
    """Audit log for tracking all changes to user profiles and permissions.

    Immutability enforced via DB triggers (prevent UPDATE/DELETE).
    Tamper detection via SHA-256 hash chain (each record includes hash of previous).
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    change_type = Column(String, nullable=False, index=True)  # 'permission', 'role', 'profile', 'workflow', 'milestone', 'goal', 'skill'
    entity_type = Column(String, nullable=False)  # 'user_permissions', 'user_profile', 'workflow_settings', etc.
    entity_id = Column(Integer, nullable=True)
    before_state = Column(JSON, nullable=True)  # State before the change
    after_state = Column(JSON, nullable=True)  # State after the change
    ip_address = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Hash chain for tamper detection (P0-4)
    sequence_number = Column(Integer, nullable=True, index=True)
    record_hash = Column(String(64), nullable=True)       # SHA-256 of this record
    previous_hash = Column(String(64), nullable=True)      # Hash of previous record (NULL for first)
    hash_algorithm = Column(String(10), default="sha256")


# ============================================================================
# USER SESSIONS
# ============================================================================

class UserSession(Base):
    """Track active user sessions for security monitoring"""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ip_address = Column(String, nullable=True)
    location = Column(String, nullable=True)  # Geographic location
    device = Column(String, nullable=True)  # Device description (browser, OS)
    user_agent = Column(Text, nullable=True)  # Full user agent string
    logged_in_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    last_activity = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    is_active = Column(Boolean, default=True, index=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    revoke_reason = Column(Text, nullable=True)


# ============================================================================
# EMERGENCY ACCESS CONTROL
# ============================================================================

class EmergencyRevocation(Base):
    """Track emergency access revocations for compliance and audit"""
    __tablename__ = "emergency_revocations"

    id = Column(Integer, primary_key=True, index=True)
    revocation_id = Column(String, unique=True, index=True, nullable=False)  # Format: REV-YYYY-NNNNNN
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    revoked_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String, nullable=False)  # 'termination', 'security_incident', 'policy_violation', 'investigation', 'other'
    details = Column(Text, nullable=False)
    sessions_terminated = Column(Integer, default=0)
    permissions_revoked = Column(Integer, default=0)
    notifications_sent = Column(JSON, nullable=True)  # Array of who was notified
    reinstate_type = Column(String, nullable=False)  # 'manual' or 'automatic'
    reinstate_date = Column(DateTime, nullable=True)
    reinstated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class AccessCertification(Base):
    """Access certification for compliance reviews"""
    __tablename__ = "access_certifications"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    certification_period = Column(String(20), nullable=False)  # e.g., "Q4-2025"
    due_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), default='pending', index=True)  # 'pending', 'certified', 'overdue', 'skipped'

    certified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    certified_at = Column(DateTime, nullable=True)
    certification_notes = Column(Text, nullable=True)

    permissions_snapshot = Column(JSON, nullable=True)  # Snapshot of permissions at certification time
    permissions_changed = Column(JSON, nullable=True)  # Any changes made during certification

    reminder_sent_30d = Column(Boolean, default=False)
    reminder_sent_7d = Column(Boolean, default=False)
    reminder_sent_overdue = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# SECURITY MONITORING
# ============================================================================

class SecuritySnapshotDaily(Base):
    """Daily security metrics for Mission Control"""
    __tablename__ = "security_snapshot_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    active_users_with_2fa = Column(Integer, default=0)
    active_users_total = Column(Integer, default=0)
    high_privilege_actions_24h = Column(Integer, default=0)
    failed_login_attempts_24h = Column(Integer, default=0)
    password_changes_24h = Column(Integer, default=0)
    last_permission_change_user = Column(String, nullable=True)
    last_permission_change_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# INTEGRATION STATUS
# ============================================================================

class IntegrationStatusLog(Base):
    """Log of integration health checks for Mission Control"""
    __tablename__ = "integration_status_log"

    id = Column(Integer, primary_key=True, index=True)
    integration_name = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)  # 'connected', 'degraded', 'down'
    last_success_at = Column(DateTime, nullable=True)
    error_count_24h = Column(Integer, default=0)
    latency_ms = Column(Integer, nullable=True)
    last_error_message = Column(Text, nullable=True)
    checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class SystemAlert(Base):
    """System alerts and recommended actions for Mission Control"""
    __tablename__ = "system_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String, nullable=False)  # 'integration', 'security', 'performance', etc.
    severity = Column(String, nullable=False)  # 'critical', 'warning', 'info'
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    suggested_action = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class SystemJobsLog(Base):
    """Log of system jobs (email sync, data pipelines, etc.) for Mission Control"""
    __tablename__ = "system_jobs_log"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String, nullable=False, index=True)
    job_type = Column(String, nullable=True)  # 'email_sync', 'data_pipeline', 'cleanup', etc.
    status = Column(String, nullable=False)  # 'success', 'failed', 'running'
    duration_ms = Column(Integer, nullable=True)
    records_processed = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    last_run_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


# ============================================================================
# NOTIFICATIONS
# ============================================================================

class Notification(Base):
    """User notifications"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # 'permission_approved', 'permission_denied', 'milestone_due', 'assessment_reminder', 'goal_reminder', 'feedback_added'
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    link = Column(String(500), nullable=True)  # URL to navigate to when clicked
    is_read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Audit
    "AuditLog",
    # Sessions
    "UserSession",
    # Access Control
    "EmergencyRevocation",
    "AccessCertification",
    # Security Monitoring
    "SecuritySnapshotDaily",
    # Integration Status
    "IntegrationStatusLog",
    "SystemAlert",
    "SystemJobsLog",
    # Notifications
    "Notification",
]
