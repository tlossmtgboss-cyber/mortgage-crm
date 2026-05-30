"""
Guideline Search Service — RAG orchestration layer.

Combines vector retrieval (AriaRetrievalService.retrieve_guidelines) with
Claude-powered answer synthesis.  Returns a structured response with:

- Synthesized answer with inline citations [1], [2], ...
- Citation list mapping each [N] to a specific guideline section
- Source aggregation by guideline name
- Confidence score (average similarity of retrieved sections)
"""

import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("guideline_search")


class GuidelineSearchService:
    """RAG orchestration for mortgage underwriting guideline queries."""

    def __init__(self, db: Session, redis=None):
        self._db = db
        self._redis = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        tenant_id: int,
        agencies: Optional[List[str]] = None,
        loan_program: Optional[str] = None,
        category: Optional[str] = None,
        top_k: int = 8,
    ) -> Dict[str, Any]:
        """Execute full RAG pipeline: retrieve -> synthesize -> format.

        Returns a dict with keys: answer, citations, sources, confidence, query.
        """
        retrieval_result = await self._retrieve(
            query=query,
            tenant_id=tenant_id,
            agencies=agencies,
            loan_program=loan_program,
            category=category,
            top_k=top_k,
        )

        if retrieval_result.no_results or not retrieval_result.guidelines:
            return {
                "answer": (
                    "I couldn't find specific guideline content matching your "
                    "query. Try rephrasing or broadening your search criteria."
                ),
                "citations": [],
                "sources": [],
                "confidence": 0.0,
                "query": query,
            }

        guidelines = retrieval_result.guidelines

        # Build numbered context block for the LLM
        context_block = self._build_context_block(guidelines)

        # Synthesize answer via Claude
        answer = await self._synthesize_answer(query, context_block, guidelines)

        # Format citations
        citations = self._format_citations(guidelines)

        # Aggregate sources
        sources = self._aggregate_sources(citations)

        # Confidence = average similarity
        confidence = (
            sum(g.similarity for g in guidelines) / len(guidelines)
            if guidelines
            else 0.0
        )

        return {
            "answer": answer,
            "citations": citations,
            "sources": sources,
            "confidence": round(confidence, 4),
            "query": query,
        }

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def _retrieve(
        self,
        query: str,
        tenant_id: int,
        agencies: Optional[List[str]],
        loan_program: Optional[str],
        category: Optional[str],
        top_k: int,
    ):
        """Delegate to AriaRetrievalService for vector search."""
        from services.aria_memory.retrieval_service import AriaRetrievalService

        retrieval = AriaRetrievalService(db=self._db, redis=self._redis)
        return await retrieval.retrieve_guidelines(
            query=query,
            tenant_id=tenant_id,
            agencies=agencies,
            loan_program=loan_program,
            category=category,
            top_k=top_k,
        )

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def _build_context_block(self, guidelines) -> str:
        """Build numbered excerpt block for the LLM prompt."""
        parts: List[str] = []
        for i, g in enumerate(guidelines, 1):
            header = f"[{i}] {g.guideline_name}"
            if g.section_number:
                header += f" — Section {g.section_number}"
            if g.section_title:
                header += f": {g.section_title}"
            if g.page_number is not None:
                header += f" (p. {g.page_number})"
            parts.append(f"{header}\n{g.text}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # LLM synthesis
    # ------------------------------------------------------------------

    _SYSTEM_PROMPT = (
        "You are a mortgage underwriting guidelines expert. "
        "Answer the user's question using ONLY the provided guideline excerpts. "
        "Use inline citations [1], [2], etc. to reference specific excerpts. "
        "When comparing numeric values (LTV limits, credit scores, DTI ratios), "
        "use a markdown table for clarity. "
        "If a company overlay differs from the agency guideline, explicitly flag "
        "the difference. "
        "Be precise and always cite section numbers and page numbers when available. "
        "If the excerpts do not contain enough information to answer, say so."
    )

    async def _synthesize_answer(
        self, query: str, context_block: str, guidelines
    ) -> str:
        """Call Claude to synthesize an answer from retrieved guideline excerpts."""
        try:
            import anthropic

            client = anthropic.AsyncAnthropic()

            user_message = (
                f"<guideline_excerpts>\n{context_block}\n</guideline_excerpts>\n\n"
                f"Question: {query}"
            )

            response = await client.messages.create(
                model=os.getenv(
                    "GUIDELINE_SEARCH_MODEL", "claude-sonnet-4-6"
                ),
                max_tokens=2048,
                system=self._SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            return response.content[0].text

        except Exception as e:
            logger.warning(
                "Claude synthesis failed, falling back to raw excerpts: %s", e
            )
            return self._fallback_answer(guidelines)

    def _fallback_answer(self, guidelines) -> str:
        """Format raw excerpts as a plain-text answer when LLM call fails."""
        parts: List[str] = []
        for g in guidelines:
            label = f"**{g.guideline_name}**"
            if g.section_number:
                label += f" ({g.section_number})"
            parts.append(f"{label}: {g.text}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Citation / source formatting
    # ------------------------------------------------------------------

    def _format_citations(self, guidelines) -> List[Dict[str, Any]]:
        """Build citation list from retrieved guidelines."""
        citations: List[Dict[str, Any]] = []
        for i, g in enumerate(guidelines, 1):
            citations.append({
                "index": i,
                "section_number": g.section_number,
                "section_title": g.section_title,
                "guideline_name": g.guideline_name,
                "guideline_type": g.guideline_type,
                "loan_program": g.loan_program,
                "page_number": g.page_number,
                "snippet": g.text[:200] if g.text else "",
                "similarity": round(g.similarity, 4),
                "is_overlay": g.overlay_priority < 4,
            })
        return citations

    def _aggregate_sources(
        self, citations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Aggregate citations by guideline_name."""
        source_map: Dict[str, Dict[str, Any]] = {}
        for c in citations:
            name = c["guideline_name"]
            if name not in source_map:
                source_map[name] = {
                    "guideline_name": name,
                    "guideline_type": c["guideline_type"],
                    "loan_program": c["loan_program"],
                    "citation_count": 0,
                }
            source_map[name]["citation_count"] += 1
        return list(source_map.values())
