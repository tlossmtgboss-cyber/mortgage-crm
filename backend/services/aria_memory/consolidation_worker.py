"""
Consolidation Worker

After each call: extract structured facts from transcript via LLM,
run through exclusion filter, classify/route to destination,
write to staging queue (or auto-commit if above threshold).
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("aria.consolidation")

AUTO_COMMIT_THRESHOLD = 0.85
EXTRACTION_MODEL = "claude-haiku-4-5-20251001"
MAX_FACT_TEXT_LEN = 500


class ConsolidationWorker:
    def __init__(self, db: Session, redis=None):
        self._db = db
        self._redis = redis

    async def process_call(
        self,
        call_session_id: str,
        tenant_id: int,
        borrower_id: int,
        transcript: str,
        call_metadata: dict,
    ) -> dict:
        if self._check_idempotency(call_session_id):
            logger.info("Call %s already processed, skipping", call_session_id)
            return {"status": "skipped", "reason": "already_processed"}

        items = await self._extract_facts(transcript, tenant_id)

        if not items:
            self._log_audit("extraction", tenant_id, borrower_id, call_session_id,
                            details={"item_count": 0})
            return {"status": "complete", "extracted": 0, "staged": 0}

        items = self._apply_exclusion_filter(items, tenant_id, borrower_id)

        memory_items = [i for i in items if i["destination"] == "memory"]
        other_items = [i for i in items if i["destination"] != "memory"]

        staged_count = 0
        if memory_items:
            await self._write_to_staging(memory_items, tenant_id, borrower_id, call_session_id)
            staged_count = len(memory_items)

        for item in other_items:
            self._route_non_memory(item, tenant_id, borrower_id, call_session_id)

        self._log_audit("extraction", tenant_id, borrower_id, call_session_id,
                        details={
                            "item_count": len(items),
                            "staged": staged_count,
                            "discarded": sum(1 for i in items if i["destination"] == "discard"),
                        })

        try:
            await self._detect_false_negatives(transcript, tenant_id, borrower_id, call_session_id)
        except Exception as e:
            logger.warning("False-negative detection failed: %s", e)
            self._log_audit("false_negative_check_failed", tenant_id, borrower_id,
                            call_session_id, details={"error": str(e)})

        return {"status": "complete", "extracted": len(items), "staged": staged_count}

    def _check_idempotency(self, source_call_id: str) -> bool:
        sql = text("""
            SELECT id FROM memory_audit_events
            WHERE source_call_id = :call_id AND event_type = 'extraction'
            LIMIT 1
        """)
        row = self._db.execute(sql, {"call_id": source_call_id}).fetchone()
        return row is not None

    async def _extract_facts(self, transcript: str, tenant_id: int) -> list[dict]:
        from services.aria_memory.exclusion_list import ExclusionChecker
        checker = ExclusionChecker(self._db)
        exclusion_section = checker.get_exclusion_prompt_section()

        prompt = f"""Extract structured facts from this call transcript.

For each fact, provide:
- fact_text: the extracted fact (concise, one sentence)
- fact_type: preference | fact | context | insight | directive
- topic: documents | timeline | conditions | qualification | income | preferences | general | last_call_context | open_questions
- confidence: 0.0-1.0 (how certain this was explicitly stated)
- transcript_span: exact quote from transcript
- transcript_position: approximate character offset
- fact_key: for preferences, a structured slug (e.g. "contact_method", "best_call_time"). For other types, null.
- destination: memory | loan_notes | pipeline_intel | qa_signal | discard
- destination_reasoning: one sentence explaining classification

{exclusion_section}

Return a JSON array. If no facts to extract, return [].

TRANSCRIPT:
{transcript}"""

        return await self._call_extraction_llm(prompt)

    async def _call_extraction_llm(self, prompt: str) -> list[dict]:
        import anthropic

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        text_content = response.content[0].text.strip()
        if text_content.startswith("```"):
            lines = text_content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text_content = "\n".join(lines).strip()

        try:
            return json.loads(text_content)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Extraction LLM returned unparseable JSON, returning empty")
            return []

    def _check_exclusions(self, items: list[dict]) -> list[dict]:
        """Hook for patching in tests; production path uses _apply_exclusion_filter."""
        return items

    def _get_exclusion_checker(self):
        from services.aria_memory.exclusion_list import ExclusionChecker
        return ExclusionChecker(self._db)

    def _apply_exclusion_filter(
        self, items: list[dict], tenant_id: int, borrower_id: int
    ) -> list[dict]:
        checker = self._get_exclusion_checker()
        filtered = []
        for item in items:
            result = checker.check(item["fact_text"], item["fact_type"], item.get("topic", ""))
            if result.excluded:
                item["destination"] = "discard"
                item["destination_reasoning"] = f"Excluded: {result.category}"
                self._log_audit("exclusion", tenant_id, borrower_id, details={
                    "category": result.category,
                    "fact_text": item["fact_text"][:100],
                })
            elif result.transformation:
                item["destination_reasoning"] += f" (transformed: {result.transformation})"
            filtered.append(item)
        return filtered

    def _should_auto_commit(self, confidence: float, exclusion_flagged: bool) -> bool:
        if exclusion_flagged:
            return False
        return confidence >= AUTO_COMMIT_THRESHOLD

    async def _write_to_staging(
        self,
        items: list[dict],
        tenant_id: int,
        borrower_id: int,
        source_call_id: str,
    ) -> None:
        from database.models.memory_staging import MemoryStaging

        for item in items:
            item["fact_text"] = item["fact_text"][:MAX_FACT_TEXT_LEN]
            confidence = item.get("confidence", 0.0)
            content_hash = hashlib.sha256(item["fact_text"].encode()).hexdigest()[:32]

            if self._should_auto_commit(confidence, exclusion_flagged=False):
                # High-confidence fact: auto-commit directly to agent_memories
                await self._auto_commit_to_memory(
                    item, tenant_id, borrower_id, source_call_id, content_hash,
                )
            else:
                staging = MemoryStaging(
                    organization_id=tenant_id,
                    borrower_id=borrower_id,
                    source_call_id=source_call_id,
                    fact_text=item["fact_text"],
                    fact_type=item["fact_type"],
                    topic=item.get("topic"),
                    confidence=confidence,
                    transcript_span=item.get("transcript_span"),
                    fact_key=item.get("fact_key"),
                    destination=item["destination"],
                    status="pending_review",
                    content_hash=content_hash,
                )
                self._db.add(staging)

        self._db.commit()

    async def _auto_commit_to_memory(
        self,
        item: dict,
        tenant_id: int,
        borrower_id: int,
        source_call_id: str,
        content_hash: str,
    ) -> None:
        """Auto-commit a high-confidence fact directly to agent_memories with embedding."""
        from database.models.agent_memory import AgentMemory, MemoryType
        from services.aria_memory.embedding_service import generate_embedding_async, EMBEDDING_MODEL

        type_map = {
            "preference": MemoryType.PREFERENCE,
            "fact": MemoryType.FACT,
            "context": MemoryType.CONTEXT,
            "insight": MemoryType.INSIGHT,
            "directive": MemoryType.DIRECTIVE,
        }

        # Dedup: check if this exact content already exists
        existing = self._db.query(AgentMemory).filter(
            AgentMemory.borrower_id == borrower_id,
            AgentMemory.organization_id == tenant_id,
            AgentMemory.content_hash == content_hash,
            AgentMemory.superseded_by.is_(None),
        ).first()
        if existing:
            existing.last_verified_at = datetime.now(timezone.utc)
            logger.info("Auto-commit dedup: refreshed memory %d", existing.id)
            return

        # Supersession for preferences with same fact_key
        superseded_id = None
        fact_key = item.get("fact_key")
        if fact_key:
            old = self._db.query(AgentMemory).filter(
                AgentMemory.borrower_id == borrower_id,
                AgentMemory.organization_id == tenant_id,
                AgentMemory.fact_key == fact_key,
                AgentMemory.superseded_by.is_(None),
            ).first()
            if old:
                superseded_id = old.id

        # Generate embedding
        embedding = await generate_embedding_async(item["fact_text"])

        memory = AgentMemory(
            user_id=borrower_id,
            organization_id=tenant_id,
            memory_type=type_map.get(item.get("fact_type"), MemoryType.FACT),
            key=fact_key or f"auto_{item.get('fact_type', 'fact')}_{source_call_id[:8]}",
            value=item["fact_text"][:MAX_FACT_TEXT_LEN],
            confidence=item.get("confidence", 0.0),
            agent_role="consolidation_worker",
            borrower_id=borrower_id,
            topic=item.get("topic"),
            source_call_id=source_call_id,
            transcript_span=item.get("transcript_span"),
            fact_key=fact_key,
            content_hash=content_hash,
            embedding=embedding,
            embedding_model=EMBEDDING_MODEL if embedding else None,
        )
        self._db.add(memory)
        self._db.flush()

        if superseded_id:
            old_mem = self._db.query(AgentMemory).filter(AgentMemory.id == superseded_id).first()
            if old_mem:
                old_mem.superseded_by = memory.id

        self._log_audit(
            "auto_commit", tenant_id, borrower_id, source_call_id,
            details={
                "memory_id": memory.id,
                "confidence": item.get("confidence"),
                "fact_key": fact_key,
                "has_embedding": embedding is not None,
            },
        )
        logger.info(
            "Auto-committed memory %d (confidence=%.2f, embedding=%s)",
            memory.id, item.get("confidence", 0), "yes" if embedding else "no",
        )

    def _route_non_memory(
        self, item: dict, tenant_id: int, borrower_id: int, source_call_id: str
    ) -> None:
        dest = item["destination"]
        if dest == "discard":
            return
        self._log_audit(f"routed_{dest}", tenant_id, borrower_id, source_call_id,
                        details={"fact_text": item["fact_text"][:200], "destination": dest})

    async def _detect_false_negatives(
        self, transcript: str, tenant_id: int, borrower_id: int, source_call_id: str
    ) -> None:
        import anthropic

        prompt = f"""Analyze this call transcript. Did the borrower reference prior context
(e.g., "we discussed", "last time", "you said", "you told me", "remember when")
that the AI assistant failed to address or retrieve?

If yes, return a JSON array of objects with:
- transcript_span: the exact quote where prior context was referenced
- unaddressed: true if the assistant didn't acknowledge or retrieve the information

If no references to prior context, return [].

TRANSCRIPT:
{transcript}"""

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        text_content = response.content[0].text.strip()
        if text_content.startswith("```"):
            lines = text_content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text_content = "\n".join(lines).strip()

        try:
            refs = json.loads(text_content)
        except (json.JSONDecodeError, ValueError):
            logger.warning("False-negative detection returned unparseable JSON")
            return

        if not isinstance(refs, list):
            return
        for ref in refs:
            if ref.get("unaddressed"):
                self._log_audit(
                    "false_negative_detected", tenant_id, borrower_id,
                    source_call_id,
                    details={"transcript_span": ref.get("transcript_span", "")},
                )

    def _log_audit(
        self, event_type: str, tenant_id: int, borrower_id: int = None,
        source_call_id: str = None, **kwargs
    ) -> None:
        try:
            from database.models.memory_audit import MemoryAuditEvent
            event = MemoryAuditEvent(
                organization_id=tenant_id,
                borrower_id=borrower_id,
                event_type=event_type,
                source_call_id=source_call_id,
                details=kwargs.get("details"),
            )
            self._db.add(event)
            self._db.flush()
        except Exception as e:
            logger.warning("Audit event logging failed: %s", e)
