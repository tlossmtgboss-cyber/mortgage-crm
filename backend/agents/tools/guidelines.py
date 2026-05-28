"""
Perennia AI - Underwriting Guideline Tools
==========================================
Lets AI agents ground their answers in the lender's own uploaded underwriting
guidelines (agency, investor, and company overlays) instead of relying on
generic knowledge. Backed by the underwriting_guidelines / guideline_sections
tables populated via the Guideline Management screen.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
)


@mortgage_tool(
    name="search_underwriting_guidelines",
    description=(
        "Search the lender's uploaded underwriting guidelines (agency, investor, "
        "and company overlays) for requirements relevant to a question — e.g. "
        "minimum credit score, max DTI/LTV, reserve requirements, waiting periods "
        "after bankruptcy/foreclosure, documentation rules. Returns the most "
        "relevant guideline excerpts with their source document and section so the "
        "agent can cite the actual policy."
    ),
    agent_roles=[
        "underwriter",
        "compliance_checker",
        "document_tracker",
        "pipeline_analyst",
        "loan_officer",
    ],
    risk_level="LOW",
    parameters={
        "query": "Natural-language guideline question or keywords (required)",
        "loan_program": "Optional program filter: conventional, fha, va, usda",
        "limit": "Max excerpts to return (default 6, max 25)",
    },
)
def search_underwriting_guidelines(
    query: str,
    loan_program: Optional[str] = None,
    limit: int = 6,
) -> ToolResult:
    """Full-text search over uploaded guideline sections (with a document-level fallback)."""
    if not query or len(query.strip()) < 2:
        return ToolResult.error("Provide a search query of at least 2 characters")

    try:
        limit = max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        limit = 6

    params = {"q": query.strip(), "limit": limit}
    program_clause = ""
    if loan_program:
        params["program"] = loan_program.strip().lower()
        program_clause = (
            "AND (lower(g.loan_program) = :program "
            "OR g.loan_program = 'all' OR g.loan_program IS NULL)"
        )

    # Section-level matches — most granular and best for grounding answers.
    # organization_id is selected so execute_query's tenant isolation applies
    # (keeps the caller's org rows plus org-NULL shared guidelines).
    rows = execute_query(f"""
        SELECT g.organization_id AS organization_id,
               g.name AS guideline_name,
               g.guideline_type,
               g.loan_program,
               g.investor_name,
               s.section_number,
               s.section_title,
               s.content,
               ts_rank(
                   to_tsvector('english', coalesce(s.section_title, '') || ' ' || coalesce(s.content, '')),
                   plainto_tsquery('english', :q)
               ) AS rank
        FROM guideline_sections s
        JOIN underwriting_guidelines g ON g.id = s.guideline_id
        WHERE g.is_active = TRUE
          AND to_tsvector('english', coalesce(s.section_title, '') || ' ' || coalesce(s.content, ''))
              @@ plainto_tsquery('english', :q)
          {program_clause}
        ORDER BY rank DESC
        LIMIT :limit
    """, params)

    # Fallback: document-level full_text match when sections aren't available yet
    # (e.g. a guideline uploaded but not yet chunked into sections).
    if not rows:
        rows = execute_query(f"""
            SELECT g.organization_id AS organization_id,
                   g.name AS guideline_name,
                   g.guideline_type,
                   g.loan_program,
                   g.investor_name,
                   NULL AS section_number,
                   NULL AS section_title,
                   left(g.full_text, 1500) AS content,
                   ts_rank(to_tsvector('english', coalesce(g.full_text, '')),
                           plainto_tsquery('english', :q)) AS rank
            FROM underwriting_guidelines g
            WHERE g.is_active = TRUE
              AND g.full_text IS NOT NULL
              AND to_tsvector('english', coalesce(g.full_text, '')) @@ plainto_tsquery('english', :q)
              {program_clause}
            ORDER BY rank DESC
            LIMIT :limit
        """, params)

    matches = [{
        "guideline": r.get("guideline_name"),
        "type": r.get("guideline_type"),
        "loan_program": r.get("loan_program"),
        "investor": r.get("investor_name"),
        "section_number": r.get("section_number"),
        "section_title": r.get("section_title"),
        "excerpt": (r.get("content") or "")[:1500],
    } for r in (rows or [])]

    if not matches:
        return ToolResult.success(
            {"query": query, "matches": []},
            message=(
                "No matching underwriting guidelines found. The relevant guideline "
                "may not be uploaded yet, or is still processing."
            ),
        )

    return ToolResult.success(
        {"query": query, "matches": matches},
        message=f"Found {len(matches)} guideline excerpt(s) matching '{query}'.",
    )
