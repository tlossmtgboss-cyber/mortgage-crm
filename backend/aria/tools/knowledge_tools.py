"""
aria/tools/knowledge_tools.py
Perennia AI — Knowledge & Analysis Bridge for Aria

Handles guideline RAG questions and income analysis
by bridging to existing agent tools and services.
"""

import logging
from typing import Any, Dict

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)
client = AsyncAnthropic()

try:
    from services.guideline_search_service import GuidelineSearchService
except ImportError:
    GuidelineSearchService = None  # type: ignore[assignment,misc]


class KnowledgeTools:

    async def search_guidelines_rag(
        self,
        question: str,
        loan_program: str = None,
        agency: str = None,
        include_overlays: bool = True,
    ) -> dict:
        """
        Search mortgage underwriting guidelines using RAG.
        Returns AI-synthesized answer with citations from indexed guideline documents.
        """
        try:
            if GuidelineSearchService is None:
                raise ImportError("GuidelineSearchService not available")

            from database import SessionLocal

            db = None
            try:
                db = SessionLocal()
                service = GuidelineSearchService(db=db)
                agencies = [agency] if agency else None
                result = await service.search(
                    query=question,
                    tenant_id=1,
                    agencies=agencies,
                    loan_program=loan_program,
                    top_k=8,
                )
                result["rag_enabled"] = True
                return result
            finally:
                if db:
                    db.close()
        except Exception as e:
            logger.warning("RAG search failed, falling back to Claude: %s", e, exc_info=True)
            return await self._fallback_guideline_answer(question)

    async def _fallback_guideline_answer(self, question: str) -> dict:
        """Fallback to Claude training data when RAG is unavailable."""
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                system="You are a mortgage underwriting guidelines expert. Answer based on your training data. Add a disclaimer that the answer is from general knowledge, not from indexed official guidelines.",
                messages=[{"role": "user", "content": question}],
            )
            return {
                "answer": response.content[0].text,
                "citations": [],
                "sources": [],
                "confidence": None,
                "rag_enabled": False,
                "disclaimer": "Answer based on general knowledge. Not sourced from indexed official guidelines.",
                "query": question,
            }
        except Exception:
            return {
                "answer": "I was unable to search the guidelines at this time. Please try again.",
                "citations": [],
                "sources": [],
                "confidence": None,
                "rag_enabled": False,
                "query": question,
            }

    async def run_income_analysis(self, loan_id: int, org_id: str) -> Dict:
        """
        Run income analysis for a loan. Bridges to the existing
        income calculation service if available.
        """
        try:
            from services.income.income_calculation_service import IncomeCalculationService
            service = IncomeCalculationService()
            result = service.calculate_for_loan(loan_id, org_id)
            if result:
                return {
                    "qualifying_income": result.get("total_qualifying_income", 0),
                    "income_sources": result.get("income_sources", []),
                    "dti_ratio": result.get("dti_ratio"),
                    "analysis_notes": result.get("notes", ""),
                }
        except Exception as e:
            logger.warning(f"Income service not available, using AI analysis: {e}")

        return {
            "qualifying_income": None,
            "income_sources": [],
            "dti_ratio": None,
            "analysis_notes": "Income analysis requires manual review — income service not configured for this loan.",
        }
