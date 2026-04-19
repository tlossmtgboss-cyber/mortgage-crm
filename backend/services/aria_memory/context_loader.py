"""
Tier 1 Context Loader

Loads structured context at call start (~400-600 tokens).
Assembles borrower identity, preferences, active loan state,
topic-relevant episodic facts, and last interaction summary.
"""

import logging
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("aria.context_loader")

MAX_PREFERENCES = 10
MAX_PREFERENCE_VALUE_LEN = 200
MAX_FACTS = 5
MAX_FACT_LEN = 300
MAX_CONDITIONS = 10
MAX_NAME_LEN = 100


class ActiveLoanSummary(BaseModel):
    loan_id: int
    stage: str
    loan_amount: Optional[float] = None
    property_address: Optional[str] = None
    loan_officer_name: Optional[str] = None
    next_milestone: Optional[str] = None


class EpisodicFact(BaseModel):
    text: str
    topic: str
    source_call_date: Optional[date] = None
    freshness: Literal["fresh", "aging"]
    confidence: float


class BorrowerContext(BaseModel):
    borrower_name: str
    borrower_id: Optional[int] = None
    needs_identity_verification: bool = False
    preferences: dict = {}
    active_loan: Optional[ActiveLoanSummary] = None
    relevant_facts: list[EpisodicFact] = []
    last_interaction: Optional[str] = None
    pending_conditions: list[str] = []


class ContextLoadRequest(BaseModel):
    borrower_id: int
    tenant_id: int
    call_trigger: str
    loan_stage: Optional[str] = None


class AriaContextLoader:
    def __init__(self, db: Session):
        self._db = db

    async def load_context(self, req: ContextLoadRequest) -> BorrowerContext:
        lead = self._get_lead(req.borrower_id, req.tenant_id)
        if lead is None:
            return BorrowerContext(
                borrower_name="",
                borrower_id=None,
                needs_identity_verification=True,
            )

        self._verify_tenant(lead, req.tenant_id)

        borrower_name = self._safe_name(lead)
        preferences = self._load_preferences(req.borrower_id, req.tenant_id)
        active_loan = self._load_active_loan(req.borrower_id, req.tenant_id)
        loan_stage = req.loan_stage or (active_loan.stage if active_loan else None)

        topics = self._resolve_topics(req.call_trigger, loan_stage, req.tenant_id)
        facts = self._load_relevant_facts(req.borrower_id, req.tenant_id, topics)
        last_interaction = self._load_last_interaction(req.borrower_id, req.tenant_id)
        conditions = self._load_conditions(active_loan.loan_id if active_loan else None)

        return BorrowerContext(
            borrower_name=borrower_name,
            borrower_id=req.borrower_id,
            needs_identity_verification=False,
            preferences=preferences,
            active_loan=active_loan,
            relevant_facts=facts,
            last_interaction=last_interaction,
            pending_conditions=conditions,
        )

    def _get_lead(self, borrower_id: int, tenant_id: int):
        from database.models.lead_loan import Lead
        return (
            self._db.query(Lead)
            .filter(Lead.id == borrower_id, Lead.organization_id == tenant_id)
            .first()
        )

    def _verify_tenant(self, lead, tenant_id: int) -> None:
        from fastapi import HTTPException
        if lead.organization_id != tenant_id:
            raise HTTPException(status_code=403, detail="Tenant mismatch")

    def _safe_name(self, lead) -> str:
        import re
        name = f"{getattr(lead, 'first_name', '') or ''} {getattr(lead, 'last_name', '') or ''}".strip()
        name = re.sub(r"[^a-zA-Z\s\-']", "", name)
        return name[:MAX_NAME_LEN]

    def _load_preferences(self, borrower_id: int, tenant_id: int) -> dict:
        sql = text("""
            SELECT key, value FROM agent_memories
            WHERE borrower_id = :borrower_id
              AND organization_id = :tenant_id
              AND memory_type = 'preference'
              AND superseded_by IS NULL
              AND fact_key IS NOT NULL
            ORDER BY last_verified_at DESC NULLS LAST
            LIMIT :max_prefs
        """)
        rows = self._db.execute(sql, {
            "borrower_id": borrower_id,
            "tenant_id": tenant_id,
            "max_prefs": MAX_PREFERENCES,
        }).fetchall()

        prefs = {}
        for row in rows:
            key = row.key
            val = row.value[:MAX_PREFERENCE_VALUE_LEN] if row.value else ""
            if key and val:
                prefs[key] = val
        return prefs

    def _load_active_loan(self, borrower_id: int, tenant_id: int) -> Optional[ActiveLoanSummary]:
        from database.models.lead_loan import Lead
        lead = self._db.query(Lead).filter(
            Lead.id == borrower_id, Lead.organization_id == tenant_id
        ).first()
        if not lead or not lead.email:
            return None

        sql = text("""
            SELECT l.id, l.stage, l.amount, l.property_address,
                   l.loan_officer_name AS lo_name
            FROM loans l
            WHERE l.borrower_email = :email
              AND l.organization_id = :tenant_id
              AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY', 'NURTURE')
            ORDER BY l.created_at DESC
            LIMIT 1
        """)
        row = self._db.execute(sql, {
            "email": lead.email,
            "tenant_id": tenant_id,
        }).fetchone()

        if not row:
            return None

        return ActiveLoanSummary(
            loan_id=row.id,
            stage=row.stage or "UNKNOWN",
            loan_amount=float(row.amount) if row.amount else None,
            property_address=row.property_address,
            loan_officer_name=(row.lo_name or "").strip() or None,
        )

    def _resolve_topics(
        self, call_trigger: str, loan_stage: Optional[str], tenant_id: int
    ) -> list[str]:
        from database.models.memory_topic_config import MemoryTopicConfig

        configs = (
            self._db.query(MemoryTopicConfig)
            .filter(
                MemoryTopicConfig.call_trigger == call_trigger,
                (MemoryTopicConfig.tenant_id == tenant_id) | (MemoryTopicConfig.tenant_id.is_(None)),
            )
            .order_by(MemoryTopicConfig.priority.desc())
            .all()
        )

        for cfg in configs:
            if cfg.tenant_id == tenant_id and cfg.loan_stage == loan_stage:
                return cfg.topics or []
            if cfg.tenant_id == tenant_id and cfg.loan_stage is None:
                return cfg.topics or []

        for cfg in configs:
            if cfg.tenant_id is None and cfg.loan_stage == loan_stage:
                return cfg.topics or []
            if cfg.tenant_id is None and cfg.loan_stage is None:
                return cfg.topics or []

        return ["general", "preferences"]

    def _load_relevant_facts(
        self, borrower_id: int, tenant_id: int, topics: list[str]
    ) -> list[EpisodicFact]:
        if not topics:
            return []

        placeholders = ", ".join(f":topic_{i}" for i in range(len(topics)))
        params = {
            "borrower_id": borrower_id,
            "tenant_id": tenant_id,
        }
        for i, t in enumerate(topics):
            params[f"topic_{i}"] = t

        sql = text(f"""
            SELECT value, topic, confidence, last_verified_at, created_at
            FROM agent_memories
            WHERE borrower_id = :borrower_id
              AND organization_id = :tenant_id
              AND superseded_by IS NULL
              AND topic IN ({placeholders})
              AND last_verified_at > NOW() - interval '90 days'
            ORDER BY
                CASE WHEN last_verified_at > NOW() - interval '30 days' THEN 0 ELSE 1 END,
                confidence DESC
            LIMIT {MAX_FACTS}
        """)
        rows = self._db.execute(sql, params).fetchall()

        facts = []
        for row in rows:
            if row.last_verified_at:
                from datetime import timedelta
                age = datetime.now(timezone.utc) - (
                    row.last_verified_at.replace(tzinfo=timezone.utc)
                    if row.last_verified_at.tzinfo is None else row.last_verified_at
                )
                freshness = "fresh" if age < timedelta(days=30) else "aging"
            else:
                freshness = "aging"

            facts.append(EpisodicFact(
                text=row.value[:MAX_FACT_LEN],
                topic=row.topic or "general",
                source_call_date=row.created_at.date() if row.created_at else None,
                freshness=freshness,
                confidence=row.confidence or 0.0,
            ))
        return facts

    def _load_last_interaction(self, borrower_id: int, tenant_id: int) -> Optional[str]:
        sql = text("""
            SELECT summary, started_at FROM agent_conversations
            WHERE user_id = :user_id
              AND organization_id = :tenant_id
              AND summary IS NOT NULL
            ORDER BY started_at DESC
            LIMIT 1
        """)
        row = self._db.execute(sql, {
            "user_id": borrower_id, "tenant_id": tenant_id,
        }).fetchone()

        if not row or not row.summary:
            return None

        date_str = row.started_at.strftime("%-m/%d") if row.started_at else "recently"
        summary = row.summary[:150]
        return f"Spoke {date_str} -- {summary}"[:200]

    def _load_conditions(self, loan_id: Optional[int]) -> list[str]:
        if not loan_id:
            return []

        sql = text("""
            SELECT title FROM tasks
            WHERE loan_id = :loan_id
              AND status NOT IN ('completed', 'cancelled')
            ORDER BY due_date ASC NULLS LAST
            LIMIT :max_cond
        """)
        rows = self._db.execute(sql, {
            "loan_id": loan_id, "max_cond": MAX_CONDITIONS,
        }).fetchall()
        return [row.title[:200] for row in rows if row.title]
