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


class KnowledgeTools:

    async def answer_guideline_question(self, question: str) -> Dict:
        """
        Answer a mortgage guideline question using Claude with built-in
        mortgage knowledge. In production, this would layer in RAG from
        a guideline vector store.
        """
        prompt = f"""You are a mortgage guidelines expert. Answer this question accurately and concisely.
If you're not sure about a specific limit or threshold, say so rather than guessing.
Always specify which loan program (FHA, VA, Conventional, USDA) the answer applies to.

Question: {question}

Provide your answer in 2-4 sentences. Include specific numbers, limits, or thresholds where applicable.
"""
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        answer_text = response.content[0].text.strip()
        return {
            "text": answer_text,
            "sources": ["Mortgage industry guidelines"],
            "confidence": 0.85,
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

        # Fallback: return placeholder indicating manual review needed
        return {
            "qualifying_income": None,
            "income_sources": [],
            "dti_ratio": None,
            "analysis_notes": "Income analysis requires manual review — income service not configured for this loan.",
        }
