"""
Voice Co-Presenter Database Models (SQLAlchemy)
Database schema for the AI Voice Co-Presenter feature.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text, Float, Index
from datetime import datetime
import enum


# =============================================================================
# ENUMS
# =============================================================================

class CallSessionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    WAITING = "waiting"
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


class VideoProvider(str, enum.Enum):
    DAILY = "daily"
    TWILIO = "twilio"
    AGORA = "agora"
    INTERNAL = "internal"


class AIMode(str, enum.Enum):
    SILENT = "silent"
    PRESENTER = "presenter"
    QNA = "qna"


class RateSheetStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class TrainingSourceStatus(str, enum.Enum):
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    INGESTED = "INGESTED"
    FAILED = "FAILED"


class PendingActionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# =============================================================================
# MODEL FACTORY
# =============================================================================

def create_voice_copresenter_models(Base):
    """
    Factory function to create voice co-presenter models with the provided SQLAlchemy Base.
    """

    class CallSession(Base):
        """
        Video call session with AI co-presenter capabilities.
        """
        __tablename__ = "call_sessions"
        __table_args__ = (
            Index('ix_call_sessions_client_id', 'client_id'),
            Index('ix_call_sessions_created_by', 'created_by_user_id'),
            Index('ix_call_sessions_started_at', 'started_at'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)  # ULID
        client_id = Column(String(26), ForeignKey("clients.id"), nullable=True)
        lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
        loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
        created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        organization_id = Column(Integer, nullable=True, index=True)

        # Timestamps
        started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
        ended_at = Column(DateTime, nullable=True)

        # Video Provider
        channel_id = Column(String(255), nullable=False)  # Daily.co room name or Twilio SID
        provider = Column(String(20), nullable=False, default="daily")

        # Context
        context_type = Column(String(20), default="client")  # "client" | "lead" | "unknown"
        active_tab = Column(String(50), default="process")

        # AI State
        ai_enabled = Column(Boolean, default=False)
        ai_mode = Column(String(20), default="silent")
        active_playbook_id = Column(String(26), nullable=True)

        # Participants (JSONB)
        participants = Column(JSON, default=[])

        # State Snapshot (JSONB)
        state_snapshot = Column(JSON, default={})

        # Status
        status = Column(String(20), default="active")

        # Recording
        recording_url = Column(String(1000), nullable=True)
        recording_duration = Column(Integer, nullable=True)

        # Metadata
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class RateSheet(Base):
        """
        Uploaded rate sheet from lender.
        """
        __tablename__ = "rate_sheets"
        __table_args__ = (
            Index('ix_rate_sheets_effective_at', 'effective_at'),
            Index('ix_rate_sheets_status', 'status'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)
        name = Column(String(255), nullable=False)
        branch_code = Column(String(50), nullable=True)
        organization_id = Column(Integer, nullable=True, index=True)

        # Effective period
        effective_at = Column(DateTime, nullable=False)
        expires_at = Column(DateTime, nullable=True)

        # Upload info
        uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        source = Column(String(20), nullable=False, default="upload")

        # Pricing constraints
        price_cap_discount = Column(Float, default=4.0)
        price_cap_credit = Column(Float, default=-4.0)

        # File storage
        raw_file_url = Column(String(1000), nullable=False)

        # Status
        status = Column(String(20), default="pending")

        # Metadata
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class RateProduct(Base):
        """
        Loan product within a rate sheet.
        """
        __tablename__ = "rate_products"
        __table_args__ = (
            Index('ix_rate_products_rate_sheet_id', 'rate_sheet_id'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)
        rate_sheet_id = Column(String(26), ForeignKey("rate_sheets.id"), nullable=False)

        family = Column(String(20), nullable=False)  # AGENCY, GOV, JUMBO, NON_QM
        program = Column(String(100), nullable=False)
        program_code = Column(String(50), nullable=True)
        term = Column(String(20), nullable=False)

        created_at = Column(DateTime, default=datetime.utcnow)

    class RateLock(Base):
        """
        Lock period for a rate product.
        """
        __tablename__ = "rate_locks"
        __table_args__ = {'extend_existing': True}

        id = Column(String(26), primary_key=True)
        rate_product_id = Column(String(26), ForeignKey("rate_products.id"), nullable=False)

        lock_days = Column(Integer, nullable=False)

        created_at = Column(DateTime, default=datetime.utcnow)

    class RateRow(Base):
        """
        Individual rate/price combination.
        """
        __tablename__ = "rate_rows"
        __table_args__ = (
            Index('ix_rate_rows_rate_lock_id', 'rate_lock_id'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)
        rate_lock_id = Column(String(26), ForeignKey("rate_locks.id"), nullable=False)

        rate = Column(Float, nullable=False)
        price = Column(Float, nullable=False)
        is_par = Column(Boolean, default=False)

        created_at = Column(DateTime, default=datetime.utcnow)

    class Scenario(Base):
        """
        Loan scenario for comparison.
        """
        __tablename__ = "scenarios"
        __table_args__ = (
            Index('ix_scenarios_client_id', 'client_id'),
            Index('ix_scenarios_call_session_id', 'call_session_id'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)
        decision_packet_id = Column(String(26), nullable=True)
        client_id = Column(String(26), nullable=True)
        lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
        loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
        call_session_id = Column(String(26), ForeignKey("call_sessions.id"), nullable=True)

        name = Column(String(100), nullable=False)

        # Loan details
        program_id = Column(String(26), ForeignKey("rate_products.id"), nullable=False)
        rate_row_id = Column(String(26), ForeignKey("rate_rows.id"), nullable=False)
        loan_amount = Column(Float, nullable=False)

        # Calculated values (denormalized for speed)
        rate = Column(Float, nullable=False)
        price = Column(Float, nullable=False)
        points_dollars = Column(Float, nullable=False)

        payment_pi = Column(Float, nullable=False)
        payment_piti = Column(Float, nullable=False)
        cash_to_close = Column(Float, nullable=False)

        # Optional analytics
        breakeven_months = Column(Integer, nullable=True)
        total_cost_year_1 = Column(Float, nullable=True)
        total_cost_year_5 = Column(Float, nullable=True)

        # Flags
        is_recommended = Column(Boolean, default=False)

        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class DecisionPacket(Base):
        """
        Published decision packet for borrower portal.
        """
        __tablename__ = "decision_packets"
        __table_args__ = (
            Index('ix_decision_packets_client_id', 'client_id'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)
        call_session_id = Column(String(26), ForeignKey("call_sessions.id"), nullable=False)
        client_id = Column(String(26), nullable=True)
        lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
        loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

        created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        published_at = Column(DateTime, nullable=False, default=datetime.utcnow)

        # Frozen context
        rate_sheet_id = Column(String(26), ForeignKey("rate_sheets.id"), nullable=False)
        effective_at = Column(DateTime, nullable=False)

        # Approved content (JSONB)
        approved_tabs = Column(JSON, default=[])
        scenarios = Column(JSON, default=[])
        assumptions = Column(JSON, default={})

        # Compliance
        disclosures = Column(JSON, default={})
        disclaimer_text = Column(Text, nullable=False)

        # Attachments
        pdf_url = Column(String(1000), nullable=True)

        # Versioning
        version = Column(Integer, nullable=False, default=1)
        supersedes = Column(String(26), nullable=True)

        created_at = Column(DateTime, default=datetime.utcnow)

    class TrainingSource(Base):
        """
        Training source for AI playbook generation.
        """
        __tablename__ = "training_sources"
        __table_args__ = {'extend_existing': True}

        id = Column(String(26), primary_key=True)
        type = Column(String(20), nullable=False)
        title = Column(String(255), nullable=False)
        url = Column(String(1000), nullable=True)
        organization_id = Column(Integer, nullable=True, index=True)

        status = Column(String(20), default="PENDING")
        error = Column(Text, nullable=True)

        total_chunks = Column(Integer, nullable=True)
        processed_chunks = Column(Integer, nullable=True)

        created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class TranscriptChunk(Base):
        """
        Chunked transcript segment for RAG.
        """
        __tablename__ = "transcript_chunks"
        __table_args__ = (
            Index('ix_transcript_chunks_training_source_id', 'training_source_id'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)
        training_source_id = Column(String(26), ForeignKey("training_sources.id"), nullable=False)

        start_sec = Column(Integer, nullable=True)
        end_sec = Column(Integer, nullable=True)

        text = Column(Text, nullable=False)
        speaker = Column(String(100), nullable=True)
        tokens = Column(Integer, nullable=False)

        embedding_id = Column(String(100), nullable=True)

        module = Column(String(50), nullable=True)
        tab_relevance = Column(JSON, nullable=True)
        intent = Column(String(50), nullable=True)

        created_at = Column(DateTime, default=datetime.utcnow)

    class Playbook(Base):
        """
        AI playbook generated from training sources.
        """
        __tablename__ = "playbooks"
        __table_args__ = {'extend_existing': True}

        id = Column(String(26), primary_key=True)
        training_source_id = Column(String(26), ForeignKey("training_sources.id"), nullable=False)
        organization_id = Column(Integer, nullable=True, index=True)

        name = Column(String(255), nullable=False)
        version = Column(Integer, default=1)
        active = Column(Boolean, default=False)

        created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class PlaybookModuleRecord(Base):
        """
        Module within a playbook.
        """
        __tablename__ = "playbook_modules"
        __table_args__ = {'extend_existing': True}

        id = Column(String(26), primary_key=True)
        playbook_id = Column(String(26), ForeignKey("playbooks.id"), nullable=False)

        module = Column(String(50), nullable=False)

        summary = Column(Text, nullable=False)
        key_phrases = Column(JSON, default=[])
        question_bank = Column(JSON, default=[])
        anti_patterns = Column(JSON, default=[])

        created_at = Column(DateTime, default=datetime.utcnow)

    class TabScript(Base):
        """
        Tab-specific script for AI responses.
        """
        __tablename__ = "tab_scripts"
        __table_args__ = {'extend_existing': True}

        id = Column(String(26), primary_key=True)
        playbook_id = Column(String(26), ForeignKey("playbooks.id"), nullable=False)

        tab = Column(String(50), nullable=False)

        explain_template = Column(Text, nullable=False)
        clarifying_questions = Column(JSON, default=[])
        common_confusions = Column(JSON, default=[])
        short_analogies = Column(JSON, default=[])

        created_at = Column(DateTime, default=datetime.utcnow)

    class ComplianceLibrary(Base):
        """
        Compliance rules for AI responses.
        """
        __tablename__ = "compliance_libraries"
        __table_args__ = {'extend_existing': True}

        id = Column(String(26), primary_key=True)
        playbook_id = Column(String(26), ForeignKey("playbooks.id"), nullable=False)

        must_say = Column(JSON, default=[])
        must_not_say = Column(JSON, default=[])
        required_disclosures = Column(JSON, default=[])

        created_at = Column(DateTime, default=datetime.utcnow)

    class AIEventLog(Base):
        """
        Audit trail for AI actions during calls.
        """
        __tablename__ = "ai_event_logs"
        __table_args__ = (
            Index('ix_ai_event_logs_call_session_id', 'call_session_id'),
            Index('ix_ai_event_logs_timestamp', 'timestamp'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)
        call_session_id = Column(String(26), ForeignKey("call_sessions.id"), nullable=False)

        event_type = Column(String(50), nullable=False)
        timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

        speaker = Column(String(20), nullable=True)
        transcript_text = Column(Text, nullable=True)

        ai_utterance = Column(Text, nullable=True)
        tts_audio_id = Column(String(100), nullable=True)

        training_chunks_used = Column(JSON, nullable=True)

        tool_name = Column(String(100), nullable=True)
        tool_input = Column(JSON, nullable=True)
        tool_output = Column(JSON, nullable=True)

        action_proposed = Column(JSON, nullable=True)
        action_approved = Column(Boolean, nullable=True)
        approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

        created_at = Column(DateTime, default=datetime.utcnow)

    class PendingAction(Base):
        """
        Actions proposed by AI awaiting LO approval.
        """
        __tablename__ = "pending_actions"
        __table_args__ = (
            Index('ix_pending_actions_call_session_id', 'call_session_id'),
            {'extend_existing': True}
        )

        id = Column(String(26), primary_key=True)
        call_session_id = Column(String(26), ForeignKey("call_sessions.id"), nullable=False)

        action_type = Column(String(50), nullable=False)
        proposed_by = Column(String(50), nullable=False)
        proposed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

        status = Column(String(20), default="PENDING")
        reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
        reviewed_at = Column(DateTime, nullable=True)

        payload = Column(JSON, nullable=False)

        created_at = Column(DateTime, default=datetime.utcnow)

    # Return all models as a dictionary
    return {
        'CallSession': CallSession,
        'RateSheet': RateSheet,
        'RateProduct': RateProduct,
        'RateLock': RateLock,
        'RateRow': RateRow,
        'Scenario': Scenario,
        'DecisionPacket': DecisionPacket,
        'TrainingSource': TrainingSource,
        'TranscriptChunk': TranscriptChunk,
        'Playbook': Playbook,
        'PlaybookModuleRecord': PlaybookModuleRecord,
        'TabScript': TabScript,
        'ComplianceLibrary': ComplianceLibrary,
        'AIEventLog': AIEventLog,
        'PendingAction': PendingAction
    }
