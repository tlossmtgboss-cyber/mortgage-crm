"""
Tests for BriefingThread, BriefingTask, and BriefingAuditLog models.

No DB required — verifies model instantiation, column existence, and defaults.
"""

import uuid
from datetime import date, datetime, timezone

from database.models.briefing_thread import (
    BriefingAuditLog,
    BriefingTask,
    BriefingThread,
)


# =============================================================================
# BriefingThread
# =============================================================================

class TestBriefingThread:
    def test_tablename(self):
        assert BriefingThread.__tablename__ == "briefing_threads"

    def test_instantiation_minimal(self):
        t = BriefingThread(organization_id=1, user_id=2)
        assert t.organization_id == 1
        assert t.user_id == 2

    def test_default_state(self):
        col = BriefingThread.__table__.c.state
        assert col.default.arg == "BRIEFING_SENT"

    def test_default_trust_mode(self):
        col = BriefingThread.__table__.c.trust_mode
        assert col.default.arg == 3

    def test_default_loop_count(self):
        col = BriefingThread.__table__.c.loop_count
        assert col.default.arg == 0

    def test_thread_token_column_exists(self):
        """thread_token column should be defined on the mapper."""
        col = BriefingThread.__table__.c.thread_token
        assert col is not None
        assert col.unique is True
        assert col.nullable is False

    def test_set_optional_fields(self):
        t = BriefingThread(
            organization_id=5,
            user_id=10,
            morning_briefing_id=42,
            outbound_message_id="msg_abc123",
            state="AWAITING_REPLY",
            trust_mode=2,
            loop_count=1,
            briefing_items=[{"item": 1, "summary": "Call John"}],
            extracted_tasks=[{"tool": "send_sms", "params": {}}],
            lo_reply_raw="Go ahead and send the follow-up.",
            lo_approval_raw="Yes, approved.",
        )
        assert t.morning_briefing_id == 42
        assert t.outbound_message_id == "msg_abc123"
        assert t.state == "AWAITING_REPLY"
        assert t.trust_mode == 2
        assert t.loop_count == 1
        assert t.briefing_items[0]["item"] == 1
        assert t.lo_reply_raw == "Go ahead and send the follow-up."
        assert t.lo_approval_raw == "Yes, approved."

    def test_relationships_defined(self):
        """tasks and audit_entries relationships should be present."""
        mapper = BriefingThread.__mapper__
        assert "tasks" in mapper.relationships
        assert "audit_entries" in mapper.relationships

    def test_table_args_includes_composite_index(self):
        """Composite index on org+user+state should be present."""
        index_names = {idx.name for idx in BriefingThread.__table__.indexes}
        assert "ix_briefing_threads_org_user_state" in index_names

    def test_table_args_includes_partial_index(self):
        index_names = {idx.name for idx in BriefingThread.__table__.indexes}
        assert "ix_briefing_threads_active_expiry" in index_names

    def test_table_args_includes_outbound_message_id_index(self):
        index_names = {idx.name for idx in BriefingThread.__table__.indexes}
        assert "ix_briefing_threads_outbound_message_id" in index_names

    def test_unique_constraint_on_token(self):
        constraint_names = {c.name for c in BriefingThread.__table__.constraints}
        assert "uq_briefing_threads_token" in constraint_names


# =============================================================================
# BriefingTask
# =============================================================================

class TestBriefingTask:
    def test_tablename(self):
        assert BriefingTask.__tablename__ == "briefing_tasks"

    def test_instantiation_minimal(self):
        task = BriefingTask(thread_id=1, organization_id=5)
        assert task.thread_id == 1
        assert task.organization_id == 5

    def test_default_status(self):
        col = BriefingTask.__table__.c.status
        assert col.default.arg == "pending"

    def test_default_risk_level(self):
        col = BriefingTask.__table__.c.risk_level
        assert col.default.arg == "low"

    def test_set_all_fields(self):
        task = BriefingTask(
            thread_id=3,
            organization_id=7,
            briefing_item_number=2,
            briefing_item_summary="Send follow-up email to Jane",
            action_type="send_email",
            action_params={"to": "jane@example.com"},
            tool_name="send_email_tool",
            lo_override_notes="Use the template from last week.",
            confidence_score=0.93,
            risk_level="medium",
            preflight_result={"valid": True},
            idempotency_key="thread-3-item-2-v1",
            status="approved",
            carryover_target_date=date(2026, 5, 8),
            result_data={"sent": True},
            error_message=None,
            executed_at=datetime.now(timezone.utc),
        )
        assert task.briefing_item_number == 2
        assert task.action_type == "send_email"
        assert task.tool_name == "send_email_tool"
        assert task.confidence_score == 0.93
        assert task.risk_level == "medium"
        assert task.idempotency_key == "thread-3-item-2-v1"
        assert task.status == "approved"
        assert task.carryover_target_date == date(2026, 5, 8)

    def test_idempotency_key_is_unique(self):
        col = BriefingTask.__table__.c.idempotency_key
        assert col.unique is True

    def test_relationship_thread_defined(self):
        mapper = BriefingTask.__mapper__
        assert "thread" in mapper.relationships

    def test_indexes_present(self):
        index_names = {idx.name for idx in BriefingTask.__table__.indexes}
        assert "ix_briefing_tasks_thread_status" in index_names
        assert "ix_briefing_tasks_organization_id" in index_names


# =============================================================================
# BriefingAuditLog
# =============================================================================

class TestBriefingAuditLog:
    def test_tablename(self):
        assert BriefingAuditLog.__tablename__ == "briefing_audit_logs"

    def test_instantiation_minimal(self):
        entry = BriefingAuditLog(organization_id=1)
        assert entry.organization_id == 1

    def test_pk_is_biginteger(self):
        from sqlalchemy import BigInteger
        pk_col = BriefingAuditLog.__table__.c.id
        assert isinstance(pk_col.type, BigInteger)

    def test_set_all_fields(self):
        entry = BriefingAuditLog(
            organization_id=9,
            thread_id=5,
            task_id=12,
            event_type="task_executed",
            actor="aria",
            payload={"tool": "send_sms", "result": "ok"},
            payload_hash="a" * 64,
            prev_hash="b" * 64,
        )
        assert entry.event_type == "task_executed"
        assert entry.actor == "aria"
        assert entry.payload_hash == "a" * 64
        assert entry.prev_hash == "b" * 64

    def test_relationship_thread_defined(self):
        mapper = BriefingAuditLog.__mapper__
        assert "thread" in mapper.relationships

    def test_composite_index_present(self):
        index_names = {idx.name for idx in BriefingAuditLog.__table__.indexes}
        assert "ix_briefing_audit_logs_org_created_at" in index_names

    def test_task_id_nullable(self):
        col = BriefingAuditLog.__table__.c.task_id
        assert col.nullable is True


# =============================================================================
# Import via __init__ package
# =============================================================================

def test_importable_from_database_models_package():
    from database.models import BriefingAuditLog as A
    from database.models import BriefingTask as T
    from database.models import BriefingThread as Th
    assert Th.__tablename__ == "briefing_threads"
    assert T.__tablename__ == "briefing_tasks"
    assert A.__tablename__ == "briefing_audit_logs"
