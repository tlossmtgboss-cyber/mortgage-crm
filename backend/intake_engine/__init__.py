"""
Intake Engine
=============

Dynamic, conversational loan intake guide for URLA-mapped pre-qualification.

This engine provides:
- Smart question sequencing based on missingness + risk signals
- Party-aware data collection (borrower, co-borrower, NBS)
- Real-time hesitation detection and behavioral analysis
- Underwriting Truth Score (0-100) for data quality assessment
- LO Readiness Score (0-100) for file completeness
- Coaching overlays for loan officer guidance
- SLA task creation based on score bands and flags
- URLA-compliant payload generation
- Append-only audit trail with hash chaining

Usage:
------
    from intake_engine import create_engine

    # Create engine instance
    engine = create_engine(
        config_path="/path/to/config",
        redis_url="redis://localhost:6379",
        postgres_url="postgresql://localhost/intake",
    )

    # Create session
    session = engine.create_session(
        loan_id="L123",
        mode="intake_prequal",
        locale="en-US",
    )

    # Get next question
    next_q = engine.get_next_question(session)

    # Submit answer
    result = engine.submit_answer(
        session,
        question_id="Q_ID_0200",
        value={"first": "John", "last": "Doe"},
        response_time_ms=1500,
    )

    # Complete session
    completion = engine.complete_session(session)
    print(completion.urla_payload)
    print(completion.scores)

API Usage:
----------
    from fastapi import FastAPI
    from intake_engine.api import router

    app = FastAPI()
    app.include_router(router)
"""

from .runtime import (
    # Core Engine
    IntakeEngine,
    create_engine,

    # Storage
    SessionStorage,

    # Models
    Session,
    Party,
    PartyType,
    SessionStatus,
    AnswerMeta,
    Flag,
    FlagCategory,
    FlagSeverity,
    AuditEvent,
    EventType,
    Question,
    NextQuestion,
    AnswerResponse,
    SessionCompleteResponse,
    SLATask,
    Signals,
    Scores,
    ScoreBreakdown,
    HesitationBand,
    TruthBand,
    DataClass,
    ConsentRecord,
    EditHistory,
)

__version__ = "1.0.0"
__author__ = "Perennia AI"

__all__ = [
    # Core
    'IntakeEngine',
    'create_engine',
    'SessionStorage',

    # Models
    'Session',
    'Party',
    'PartyType',
    'SessionStatus',
    'AnswerMeta',
    'Flag',
    'FlagCategory',
    'FlagSeverity',
    'AuditEvent',
    'EventType',
    'Question',
    'NextQuestion',
    'AnswerResponse',
    'SessionCompleteResponse',
    'SLATask',
    'Signals',
    'Scores',
    'ScoreBreakdown',
    'HesitationBand',
    'TruthBand',
    'DataClass',
    'ConsentRecord',
    'EditHistory',

    # Version
    '__version__',
]
