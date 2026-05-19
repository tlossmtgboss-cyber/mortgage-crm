"""
AI Underwriter Chat Routes

Provides the /api/v1/ai-underwriter/ask endpoint for the AI Underwriter chat interface.
This endpoint answers mortgage lending questions by searching guidelines and using AI.
"""

import os
import logging
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import anthropic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai-underwriter", tags=["AI Underwriter"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class AskRequest(BaseModel):
    """Request model for asking a question."""
    question: str
    category: Optional[str] = "all"  # conventional, fha, va, usda, jumbo, non-qm, all
    loan_context: Optional[dict] = None  # Optional loan data for context


class Source(BaseModel):
    """Source reference for an answer."""
    title: str
    url: Optional[str] = None
    guideline_id: Optional[str] = None
    section: Optional[str] = None


class AskResponse(BaseModel):
    """Response model for a question answer."""
    answer: str
    sources: List[Source] = []
    confidence: float = 0.0
    category: Optional[str] = None
    timestamp: str


# =============================================================================
# DEPENDENCIES
# =============================================================================

_get_db = None
_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    """Set the database and user dependencies from main app."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """Get database session."""
    if _get_db is None:
        raise RuntimeError("Database dependency not configured. Call set_dependencies first.")
    yield from _get_db()


from auth.dependencies import get_current_user  # dedup: was local wrapper
# =============================================================================
# GUIDELINE KNOWLEDGE BASE
# =============================================================================

# Built-in guideline knowledge for quick responses
GUIDELINE_KNOWLEDGE = {
    "conventional": {
        "credit_score": {
            "min": 620,
            "description": "Minimum credit score for conventional loans is 620. Lower scores may qualify with higher down payments or additional compensating factors."
        },
        "dti": {
            "max": 50,
            "description": "Maximum DTI for conventional loans is typically 45%, but can go up to 50% with strong compensating factors like reserves or high credit score."
        },
        "ltv": {
            "primary": 97,
            "second_home": 90,
            "investment": 85,
            "description": "Primary residence: up to 97% LTV with PMI. Second homes: 90% max. Investment properties: 85% max."
        },
        "reserves": {
            "primary": 0,
            "second_home": 2,
            "investment": 6,
            "description": "Primary: No reserves required (may need 2 months with layered risk). Second home: 2 months. Investment: 6 months."
        },
        "loan_limits": {
            "standard": 832750,
            "high_cost": 1249125,
            "description": "2026 conforming loan limit: $832,750 (standard), $1,249,125 (high-cost areas)."
        }
    },
    "fha": {
        "credit_score": {
            "min_3.5": 580,
            "min_10": 500,
            "description": "FHA requires 580+ credit for 3.5% down, 500-579 requires 10% down. Most lenders have overlays requiring 620+."
        },
        "dti": {
            "max": 56.99,
            "standard": 43,
            "description": "FHA allows DTI up to 56.99% with AUS approval. Manual underwriting typically capped at 43%."
        },
        "ltv": {
            "purchase": 96.5,
            "refinance": 97.75,
            "description": "Purchase: 96.5% LTV (3.5% down). Streamline refinance: up to 97.75% LTV."
        },
        "mip": {
            "upfront": 1.75,
            "annual_above_95": 0.85,
            "annual_below_95": 0.80,
            "description": "Upfront MIP: 1.75% of loan amount. Annual MIP: 0.85% for LTV >95%, 0.80% for LTV <=95% (terms >15 years)."
        },
        "waiting_periods": {
            "bankruptcy_ch7": "2 years",
            "bankruptcy_ch13": "1 year into plan",
            "foreclosure": "3 years",
            "short_sale": "3 years",
            "description": "Chapter 7 BK: 2 years. Chapter 13: 1 year into plan. Foreclosure/Short sale: 3 years."
        }
    },
    "va": {
        "credit_score": {
            "min": None,
            "typical_overlay": 620,
            "description": "VA has no minimum credit score requirement, but most lenders require 620+ as an overlay."
        },
        "dti": {
            "max": None,
            "description": "VA has no maximum DTI. Residual income is the primary qualification factor. DTI above 41% requires additional analysis."
        },
        "ltv": {
            "max": 100,
            "description": "VA allows 100% financing (no down payment required) for eligible veterans."
        },
        "funding_fee": {
            "first_use_0_down": 2.15,
            "first_use_5_down": 1.5,
            "subsequent_0_down": 3.3,
            "exempt": "Veterans with service-connected disability are exempt.",
            "description": "First use with 0% down: 2.15%. First use with 5%+ down: 1.5%. Subsequent use: 3.3% (0% down)."
        },
        "eligibility": {
            "description": "Requires Certificate of Eligibility (COE). Eligible: Active duty, veterans, National Guard, Reserve members, and surviving spouses."
        }
    },
    "usda": {
        "credit_score": {
            "min": 640,
            "description": "USDA requires minimum 640 credit score for GUS approval. Manual underwriting may go lower with compensating factors."
        },
        "dti": {
            "front_end": 29,
            "back_end": 41,
            "description": "Standard DTI limits: 29% front-end, 41% back-end. Can exceed with compensating factors."
        },
        "ltv": {
            "max": 100,
            "description": "USDA allows 100% financing in eligible rural areas."
        },
        "income_limits": {
            "description": "Household income cannot exceed 115% of area median income. Limits vary by location and household size."
        },
        "eligibility": {
            "description": "Property must be in USDA-eligible rural area. Income limits apply. Primary residence only."
        }
    },
    "jumbo": {
        "credit_score": {
            "min": 700,
            "preferred": 720,
            "description": "Jumbo loans typically require 700+ credit, with best rates at 720+."
        },
        "dti": {
            "max": 43,
            "description": "Most jumbo lenders cap DTI at 43%, though some allow higher with strong assets."
        },
        "ltv": {
            "max": 80,
            "high_value": 70,
            "description": "Standard max LTV is 80%. Higher loan amounts may require 70% LTV or lower."
        },
        "reserves": {
            "months": 12,
            "description": "Typically require 12 months of reserves. Higher loan amounts may require 18-24 months."
        },
        "loan_amounts": {
            "description": "Loans exceeding conforming limits ($832,750 standard, $1,249,125 high-cost). No maximum set by agencies."
        }
    },
    "non-qm": {
        "types": {
            "bank_statement": "12-24 months bank statements for income",
            "dscr": "Debt Service Coverage Ratio for investment properties",
            "asset_depletion": "Qualify using assets divided over loan term",
            "foreign_national": "Programs for non-US citizens",
            "recent_credit_event": "Programs allowing recent BK/foreclosure",
            "description": "Non-QM loans don't meet QM standards but serve borrowers who don't fit conventional guidelines."
        },
        "credit_score": {
            "bank_statement": 620,
            "dscr": 660,
            "description": "Bank statement typically 620+. DSCR typically 660+. Varies by lender."
        },
        "dti": {
            "description": "Non-QM may not use traditional DTI. Bank statement uses calculated income. DSCR uses rental income ratio."
        },
        "dscr": {
            "min": 1.0,
            "preferred": 1.25,
            "description": "DSCR = Rental Income / PITIA. Minimum 1.0, preferred 1.25+. Below 1.0 may be possible with lower LTV."
        }
    }
}


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Ask a mortgage lending question and get an AI-powered answer.

    The AI searches the guideline knowledge base and uses Claude to provide
    accurate, sourced answers to underwriting questions.
    """
    question = request.question.strip()
    category = request.category or "all"

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Build context from knowledge base
    knowledge_context = _build_knowledge_context(question, category)

    # Search stored guidelines if available
    stored_guidelines = []
    try:
        from services.call_monitoring.guidelines_service import search_guidelines
        results = await search_guidelines(
            db=db,
            query=question,
            loan_program=category if category != "all" else None,
            organization_id=str(getattr(current_user, 'organization_id', None) or (current_user.get('organization_id') if isinstance(current_user, dict) else None) or ''),
            limit=5
        )
        stored_guidelines = results
    except Exception as e:
        logger.debug(f"Guideline search failed: {e}")

    # Build the prompt for Claude
    system_prompt = """You are an expert mortgage underwriter assistant. Answer questions about mortgage lending guidelines accurately and concisely.

Key responsibilities:
1. Provide accurate information based on agency guidelines (Fannie Mae, Freddie Mac, FHA, VA, USDA)
2. Cite specific requirements (credit scores, DTI limits, LTV limits, etc.)
3. Mention when lender overlays may differ from agency guidelines
4. Flag when information might vary by lender or situation

Format your response:
- Be concise but complete
- Use bullet points for lists of requirements
- Mention the specific program(s) the information applies to
- If uncertain, say so and suggest verifying with current guidelines"""

    user_prompt = f"""Question: {question}

Category focus: {category.upper() if category != "all" else "All loan types"}

Reference Information:
{knowledge_context}

{_format_stored_guidelines(stored_guidelines) if stored_guidelines else ""}

Please provide an accurate, helpful answer based on this information."""

    # Call Claude for the answer
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        answer = response.content[0].text
        confidence = 0.85  # Base confidence
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        # Fallback to knowledge base only
        answer = _generate_fallback_answer(question, category)
        confidence = 0.5

    # Build sources list
    sources = []

    # Add relevant category as source
    if category != "all" and category in GUIDELINE_KNOWLEDGE:
        sources.append(Source(
            title=f"{category.upper()} Guidelines",
            section="Built-in knowledge base"
        ))

    # Add stored guideline sources
    for guide in stored_guidelines[:3]:
        sources.append(Source(
            title=guide.get("guideline_name", "Guideline"),
            guideline_id=guide.get("guideline_id"),
            section=guide.get("section_title")
        ))

    return AskResponse(
        answer=answer,
        sources=sources,
        confidence=confidence,
        category=category,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/guidelines/quick-reference")
async def get_quick_reference(
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get quick reference information from the built-in knowledge base.
    Useful for displaying reference cards in the UI.
    """
    if category and category in GUIDELINE_KNOWLEDGE:
        return {
            "category": category,
            "guidelines": GUIDELINE_KNOWLEDGE[category]
        }

    # Return summary of all categories
    summary = {}
    for cat, data in GUIDELINE_KNOWLEDGE.items():
        summary[cat] = {
            "min_credit": data.get("credit_score", {}).get("min") or data.get("credit_score", {}).get("min_3.5"),
            "max_dti": data.get("dti", {}).get("max"),
            "max_ltv": data.get("ltv", {}).get("max") or data.get("ltv", {}).get("primary"),
        }

    return {
        "categories": list(GUIDELINE_KNOWLEDGE.keys()),
        "summary": summary
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _build_knowledge_context(question: str, category: str) -> str:
    """Build relevant context from the knowledge base."""
    question_lower = question.lower()
    context_parts = []

    # Determine which categories to include
    if category == "all":
        categories_to_check = list(GUIDELINE_KNOWLEDGE.keys())
    else:
        categories_to_check = [category] if category in GUIDELINE_KNOWLEDGE else []

    for cat in categories_to_check:
        cat_data = GUIDELINE_KNOWLEDGE[cat]

        # Check if question relates to specific topics
        if any(term in question_lower for term in ["credit", "score", "fico"]):
            if "credit_score" in cat_data:
                context_parts.append(f"{cat.upper()} Credit Score: {cat_data['credit_score'].get('description', '')}")

        if any(term in question_lower for term in ["dti", "debt", "income ratio"]):
            if "dti" in cat_data:
                context_parts.append(f"{cat.upper()} DTI: {cat_data['dti'].get('description', '')}")

        if any(term in question_lower for term in ["ltv", "down payment", "loan to value"]):
            if "ltv" in cat_data:
                context_parts.append(f"{cat.upper()} LTV: {cat_data['ltv'].get('description', '')}")

        if any(term in question_lower for term in ["reserve", "reserves"]):
            if "reserves" in cat_data:
                context_parts.append(f"{cat.upper()} Reserves: {cat_data['reserves'].get('description', '')}")

        if any(term in question_lower for term in ["mip", "mortgage insurance", "pmi", "funding fee"]):
            if "mip" in cat_data:
                context_parts.append(f"{cat.upper()} MIP: {cat_data['mip'].get('description', '')}")
            if "funding_fee" in cat_data:
                context_parts.append(f"{cat.upper()} Funding Fee: {cat_data['funding_fee'].get('description', '')}")

        if any(term in question_lower for term in ["bankruptcy", "foreclosure", "short sale", "waiting"]):
            if "waiting_periods" in cat_data:
                context_parts.append(f"{cat.upper()} Waiting Periods: {cat_data['waiting_periods'].get('description', '')}")

        if any(term in question_lower for term in ["loan limit", "conforming", "jumbo"]):
            if "loan_limits" in cat_data:
                context_parts.append(f"{cat.upper()} Loan Limits: {cat_data['loan_limits'].get('description', '')}")

        if any(term in question_lower for term in ["eligibility", "eligible", "qualify"]):
            if "eligibility" in cat_data:
                context_parts.append(f"{cat.upper()} Eligibility: {cat_data['eligibility'].get('description', '')}")

    # If no specific topics found, include general info for the category
    if not context_parts and category != "all":
        cat_data = GUIDELINE_KNOWLEDGE.get(category, {})
        for key, value in cat_data.items():
            if isinstance(value, dict) and "description" in value:
                context_parts.append(f"{category.upper()} {key}: {value['description']}")

    return "\n\n".join(context_parts) if context_parts else "No specific guideline data found for this question."


def _format_stored_guidelines(guidelines: List[dict]) -> str:
    """Format stored guidelines for the prompt."""
    if not guidelines:
        return ""

    parts = ["Additional Guidelines from Database:"]
    for guide in guidelines[:5]:
        parts.append(f"- {guide.get('guideline_name', 'Unknown')}: {guide.get('content', '')[:500]}")

    return "\n".join(parts)


def _generate_fallback_answer(question: str, category: str) -> str:
    """Generate a fallback answer when Claude is unavailable."""
    question_lower = question.lower()
    cat_data = GUIDELINE_KNOWLEDGE.get(category, {})

    if not cat_data and category != "all":
        return f"I don't have specific information about {category} loans. Please try asking about conventional, FHA, VA, USDA, jumbo, or non-QM loans."

    # Try to match the question to known topics
    if any(term in question_lower for term in ["credit", "score"]):
        if "credit_score" in cat_data:
            return f"For {category.upper()} loans: {cat_data['credit_score'].get('description', 'Please consult current guidelines.')}"

    if any(term in question_lower for term in ["dti"]):
        if "dti" in cat_data:
            return f"For {category.upper()} loans: {cat_data['dti'].get('description', 'Please consult current guidelines.')}"

    if any(term in question_lower for term in ["ltv", "down"]):
        if "ltv" in cat_data:
            return f"For {category.upper()} loans: {cat_data['ltv'].get('description', 'Please consult current guidelines.')}"

    return "I apologize, but I couldn't generate a complete answer at this time. Please try rephrasing your question or consult the official agency guidelines directly."
