"""
Shared Retrieval Service

One service, two corpora (memory now, guidelines in Phase B).
Metadata-filter-before-vector-search, Redis hot-cache (60s TTL),
unified audit logging.
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.aria_memory.pii_scrubber import scrub_pii, scrub_pii_for_embedding

logger = logging.getLogger("aria.retrieval")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
CACHE_TTL_SECONDS = 60
FRESHNESS_FRESH_DAYS = 30
FRESHNESS_AGING_DAYS = 90
MIN_RELEVANCE_THRESHOLD = 0.3


class RetrievedFact(BaseModel):
    text: str
    topic: str
    source_call_date: Optional[date] = None
    transcript_span: Optional[str] = None
    confidence: float
    freshness: Literal["fresh", "aging", "stale"]
    fact_type: Literal["preference", "fact", "context", "insight", "directive"]


class RetrievalResult(BaseModel):
    facts: list[RetrievedFact]
    no_results: bool


class RetrievedGuideline(BaseModel):
    text: str
    section_number: str
    section_title: str
    guideline_name: str
    guideline_type: str
    loan_program: str
    page_number: Optional[int] = None
    similarity: float
    category: Optional[str] = None
    overlay_priority: int = 4


class GuidelineRetrievalResult(BaseModel):
    guidelines: list[RetrievedGuideline]
    no_results: bool


GUIDELINE_CACHE_TTL_SECONDS = 300


class AriaRetrievalService:
    def __init__(self, db: Session, redis=None):
        self._db = db
        self._redis = redis

    async def retrieve(
        self,
        scope: Literal["memory", "guideline"],
        query: str,
        tenant_id: int,
        borrower_id: Optional[int] = None,
        jurisdiction: Optional[str] = None,
        effective_date: Optional[date] = None,
        top_k: int = 5,
        time_scope_days: Optional[int] = None,
        topic: Optional[str] = None,
    ) -> RetrievalResult:
        start_ms = time.monotonic()

        cache_key = self._cache_key(scope, tenant_id, borrower_id or jurisdiction, query)
        cached = self._cache_get(cache_key)
        if cached is not None:
            self._log_audit_event(
                event_type="cache_hit", tenant_id=tenant_id,
                borrower_id=borrower_id, query_text=query,
                result_count=len(cached.facts),
                latency_ms=int((time.monotonic() - start_ms) * 1000),
            )
            return cached

        embedding = await self._embed_query(query)

        if embedding is None:
            return RetrievalResult(facts=[], no_results=True)

        if scope == "guideline":
            guideline_result = await self.retrieve_guidelines(
                query=query, tenant_id=tenant_id,
                loan_program=topic, top_k=top_k,
                _embedding=embedding,
            )
            facts = [
                RetrievedFact(
                    text=g.text, topic=g.loan_program,
                    confidence=g.similarity, freshness="fresh",
                    fact_type="fact",
                )
                for g in guideline_result.guidelines
            ]
            result = RetrievalResult(facts=facts, no_results=guideline_result.no_results)
            self._cache_set(cache_key, result)
            latency = int((time.monotonic() - start_ms) * 1000)
            self._log_audit_event(
                event_type="guideline_retrieval", tenant_id=tenant_id,
                query_text=query, result_count=len(facts),
                latency_ms=latency,
            )
            return result

        where_clauses = ["am.organization_id = :org_id"]
        params: Dict[str, Any] = {"org_id": tenant_id, "top_k": top_k, "min_relevance": MIN_RELEVANCE_THRESHOLD}

        where_clauses.append("(am.expires_at IS NULL OR am.expires_at > NOW())")
        where_clauses.append("am.superseded_by IS NULL")

        if scope == "memory":
            if borrower_id is None:
                return RetrievalResult(facts=[], no_results=True)
            where_clauses.append("am.borrower_id = :borrower_id")
            params["borrower_id"] = borrower_id

        if topic:
            where_clauses.append("am.topic = :topic")
            params["topic"] = topic

        if time_scope_days:
            where_clauses.append(
                "am.last_verified_at > NOW() - :time_scope * interval '1 day'"
            )
            params["time_scope"] = time_scope_days

        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        params["embedding"] = embedding_str
        where_sql = " AND ".join(where_clauses)

        sql = text(f"""
            SELECT
                am.value AS value,
                am.topic,
                am.source_call_id,
                am.transcript_span,
                am.confidence,
                am.memory_type,
                am.last_verified_at,
                am.created_at,
                1 - (am.embedding <=> CAST(:embedding AS vector)) AS relevance_score
            FROM agent_memories am
            WHERE {where_sql}
              AND am.embedding IS NOT NULL
              AND 1 - (am.embedding <=> CAST(:embedding AS vector)) > :min_relevance
            ORDER BY am.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)

        rows = self._db.execute(sql, params).fetchall()

        facts = []
        for row in rows:
            freshness = self._compute_freshness(row.last_verified_at)
            source_date = None
            if row.source_call_id:
                created_at = getattr(row, "created_at", None)
                if isinstance(created_at, datetime):
                    source_date = created_at

            mem_type = row.memory_type
            if hasattr(mem_type, "value"):
                mem_type = mem_type.value
            # Normalize enum value to lowercase for Pydantic model validation
            mem_type = mem_type.lower() if isinstance(mem_type, str) else mem_type

            facts.append(RetrievedFact(
                text=row.value,
                topic=row.topic or "general",
                source_call_date=source_date.date() if source_date else None,
                transcript_span=scrub_pii(row.transcript_span) if row.transcript_span else None,
                confidence=row.confidence or 0.0,
                freshness=freshness,
                fact_type=mem_type,
            ))

        result = RetrievalResult(facts=facts, no_results=len(facts) == 0)

        self._cache_set(cache_key, result)

        latency = int((time.monotonic() - start_ms) * 1000)
        self._log_audit_event(
            event_type="retrieval", tenant_id=tenant_id,
            borrower_id=borrower_id, query_text=query,
            result_count=len(facts), latency_ms=latency,
        )

        return result

    def _compute_freshness(
        self, last_verified_at: Optional[datetime]
    ) -> Literal["fresh", "aging", "stale"]:
        if last_verified_at is None:
            return "stale"
        now = datetime.now(timezone.utc)
        if last_verified_at.tzinfo is None:
            last_verified_at = last_verified_at.replace(tzinfo=timezone.utc)
        age = now - last_verified_at
        if age < timedelta(days=FRESHNESS_FRESH_DAYS):
            return "fresh"
        if age < timedelta(days=FRESHNESS_AGING_DAYS):
            return "aging"
        return "stale"

    async def retrieve_guidelines(
        self,
        query: str,
        tenant_id: int,
        agencies: Optional[list[str]] = None,
        loan_program: Optional[str] = None,
        category: Optional[str] = None,
        top_k: int = 5,
        _embedding: Optional[list[float]] = None,
    ) -> GuidelineRetrievalResult:
        """Retrieve relevant guideline sections via vector similarity search.

        Args:
            query: Natural-language question.
            tenant_id: Organization id for tenant scoping.
            agencies: Optional list of agency loan-program values to filter on.
            loan_program: Optional loan program (matches exact or 'all').
            category: Optional section category filter.
            top_k: Maximum results to return.
            _embedding: Pre-computed query embedding (avoids double-embed when
                called from ``retrieve()``).
        """
        start_ms = time.monotonic()

        # Build a deterministic filter hash for the cache key
        filter_parts = []
        if agencies:
            filter_parts.append("a:" + ",".join(sorted(agencies)))
        if loan_program:
            filter_parts.append("lp:" + loan_program)
        if category:
            filter_parts.append("c:" + category)
        filter_hash = hashlib.sha256("|".join(filter_parts).encode()).hexdigest()[:16] if filter_parts else "none"
        query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()[:24]
        cache_key = f"aria:cache:guideline:{tenant_id}:{filter_hash}:{query_hash}"

        cached = self._cache_get_guidelines(cache_key)
        if cached is not None:
            return cached

        embedding = _embedding if _embedding is not None else await self._embed_query(query)
        if embedding is None:
            return GuidelineRetrievalResult(guidelines=[], no_results=True)

        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        where_clauses = [
            "ug.is_active = true",
            "gs.content_embedding IS NOT NULL",
            "(ug.organization_id IS NULL OR ug.organization_id = CAST(:org_id AS uuid))",
        ]
        params: Dict[str, Any] = {
            "org_id": str(tenant_id),
            "top_k": top_k,
            "min_relevance": MIN_RELEVANCE_THRESHOLD,
            "embedding": embedding_str,
        }

        if agencies:
            placeholders = ", ".join(f":agency_{i}" for i in range(len(agencies)))
            where_clauses.append(f"ug.loan_program IN ({placeholders})")
            for i, agency in enumerate(agencies):
                params[f"agency_{i}"] = agency

        if loan_program:
            where_clauses.append("(ug.loan_program = :loan_program OR ug.loan_program = 'all')")
            params["loan_program"] = loan_program

        if category:
            where_clauses.append("gs.category = :category")
            params["category"] = category

        where_sql = " AND ".join(where_clauses)

        sql = text(f"""
            SELECT
                gs.content AS content,
                gs.section_number,
                gs.section_title,
                ug.name AS guideline_name,
                ug.guideline_type,
                ug.loan_program,
                gs.page_number,
                gs.category,
                ug.overlay_priority,
                1 - (gs.content_embedding <=> CAST(:embedding AS vector)) AS relevance_score
            FROM guideline_sections gs
            JOIN underwriting_guidelines ug ON ug.id = gs.guideline_id
            WHERE {where_sql}
              AND 1 - (gs.content_embedding <=> CAST(:embedding AS vector)) > :min_relevance
            ORDER BY ug.overlay_priority ASC,
                     gs.content_embedding <=> CAST(:embedding AS vector) ASC
            LIMIT :top_k
        """)

        rows = self._db.execute(sql, params).fetchall()

        guidelines = []
        for row in rows:
            guidelines.append(RetrievedGuideline(
                text=row.content,
                section_number=row.section_number or "",
                section_title=row.section_title or "",
                guideline_name=row.guideline_name or "",
                guideline_type=row.guideline_type or "",
                loan_program=row.loan_program or "all",
                page_number=row.page_number,
                similarity=float(row.relevance_score),
                category=row.category,
                overlay_priority=row.overlay_priority if row.overlay_priority is not None else 4,
            ))

        result = GuidelineRetrievalResult(guidelines=guidelines, no_results=len(guidelines) == 0)
        self._cache_set_guidelines(cache_key, result)

        latency = int((time.monotonic() - start_ms) * 1000)
        self._log_audit_event(
            event_type="guideline_retrieval", tenant_id=tenant_id,
            query_text=query, result_count=len(guidelines),
            latency_ms=latency,
        )

        return result

    async def _embed_query(self, text_input: str) -> Optional[list[float]]:
        try:
            from services.aria_memory.embedding_service import _normalize_text
            text_input = scrub_pii_for_embedding(text_input)
            normalized = _normalize_text(text_input)

            import openai
            client = openai.AsyncOpenAI()
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=normalized,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("Query embedding failed (retrieval will return empty): %s", e)
            return None

    def _cache_key(self, scope: str, tenant_id: int, entity_id, query: str) -> str:
        query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()[:24]
        return f"aria:cache:{scope}:{tenant_id}:{entity_id}:{query_hash}"

    def _cache_get(self, key: str) -> Optional[RetrievalResult]:
        if not self._redis:
            return None
        try:
            data = self._redis.get(key)
            if data is None:
                return None
            parsed = json.loads(data)
            return RetrievalResult.model_validate(parsed)
        except Exception:
            return None

    def _cache_set(self, key: str, result: RetrievalResult) -> None:
        if not self._redis:
            return
        try:
            self._redis.setex(key, CACHE_TTL_SECONDS, result.model_dump_json())
        except Exception:
            logger.warning("Redis cache set failed for %s", key)

    def _cache_get_guidelines(self, key: str) -> Optional[GuidelineRetrievalResult]:
        if not self._redis:
            return None
        try:
            data = self._redis.get(key)
            if data is None:
                return None
            parsed = json.loads(data)
            return GuidelineRetrievalResult.model_validate(parsed)
        except Exception:
            return None

    def _cache_set_guidelines(self, key: str, result: GuidelineRetrievalResult) -> None:
        if not self._redis:
            return
        try:
            self._redis.setex(key, GUIDELINE_CACHE_TTL_SECONDS, result.model_dump_json())
        except Exception:
            logger.warning("Redis guideline cache set failed for %s", key)

    def invalidate_cache(self, scope: str, tenant_id: int, borrower_id: int) -> None:
        if not self._redis:
            return
        try:
            pattern = f"aria:cache:{scope}:{tenant_id}:{borrower_id}:*"
            keys = self._redis.keys(pattern)
            if keys:
                self._redis.delete(*keys)
        except Exception:
            logger.warning("Redis cache invalidation failed")

    def _log_audit_event(self, **kwargs) -> None:
        try:
            from database.models.memory_audit import MemoryAuditEvent
            event = MemoryAuditEvent(
                organization_id=kwargs.get("tenant_id"),
                borrower_id=kwargs.get("borrower_id"),
                event_type=kwargs.get("event_type", "retrieval"),
                query_text=kwargs.get("query_text"),
                result_count=kwargs.get("result_count"),
                latency_ms=kwargs.get("latency_ms"),
                source_call_id=kwargs.get("source_call_id"),
                memory_id=kwargs.get("memory_id"),
                details=kwargs.get("details"),
            )
            self._db.add(event)
            self._db.flush()
        except Exception as e:
            logger.warning("Audit event logging failed: %s", e)
