"""
Underwriting Guidelines Service

Handles processing, indexing, and searching of underwriting guidelines
that the AI Underwriter agent can reference.
"""

import os
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import text, or_, and_
import anthropic

logger = logging.getLogger(__name__)

# Claude configuration
CLAUDE_MODEL = os.getenv("GUIDELINES_MODEL", "claude-sonnet-4-20250514")


# =============================================================================
# DOCUMENT PROCESSING
# =============================================================================

async def process_guideline(guideline_id: str, file_path: str, file_ext: str):
    """
    Process an uploaded guideline document.

    1. Extract text from the document
    2. Generate summary and key points using AI
    3. Extract keywords for searching
    4. Split into searchable sections
    """
    from database import get_db
    from models.call_monitoring_models import UnderwritingGuideline, GuidelineSection

    logger.info(f"Processing guideline {guideline_id}: {file_path}")

    db = next(get_db())

    try:
        guideline = db.query(UnderwritingGuideline).filter(
            UnderwritingGuideline.id == guideline_id
        ).first()

        if not guideline:
            logger.error(f"Guideline {guideline_id} not found")
            return

        # Extract text based on file type
        full_text = await extract_text_from_document(file_path, file_ext)

        if not full_text:
            guideline.processing_notes = "Could not extract text from document"
            guideline.is_processed = True
            db.commit()
            return

        # Store full text
        guideline.full_text = full_text

        # Generate summary and key points using AI
        try:
            analysis = await analyze_guideline_content(full_text, guideline.name)
            guideline.summary = analysis.get("summary")
            guideline.key_points = analysis.get("key_points", [])
            guideline.keywords = analysis.get("keywords", [])

            # If AI extracted structured rules, merge them
            if analysis.get("structured_rules"):
                existing_rules = guideline.structured_rules or {}
                existing_rules.update(analysis["structured_rules"])
                guideline.structured_rules = existing_rules

        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")
            guideline.processing_notes = f"AI analysis failed: {e}"

        # Split into sections for granular searching
        try:
            sections = split_into_sections(full_text, guideline.category)

            # Clear existing sections
            db.query(GuidelineSection).filter(
                GuidelineSection.guideline_id == guideline_id
            ).delete()

            # Add new sections
            for section_data in sections:
                section = GuidelineSection(
                    id=uuid.uuid4(),
                    guideline_id=guideline_id,
                    section_number=section_data.get("section_number"),
                    section_title=section_data.get("section_title"),
                    content=section_data.get("content"),
                    category=section_data.get("category") or guideline.category,
                    topics=section_data.get("topics", []),
                    position_start=section_data.get("position_start"),
                    position_end=section_data.get("position_end"),
                )
                db.add(section)

        except Exception as e:
            logger.warning(f"Section splitting failed: {e}")

        guideline.is_processed = True
        guideline.last_processed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Successfully processed guideline {guideline_id}")

    except Exception as e:
        logger.error(f"Error processing guideline {guideline_id}: {e}")
        try:
            guideline.processing_notes = f"Processing error: {e}"
            guideline.is_processed = True
            db.commit()
        except Exception as e:
            logger.error(f"Error saving processing notes for guideline {guideline_id}: {e}")

    finally:
        db.close()


async def extract_text_from_document(file_path: str, file_ext: str) -> Optional[str]:
    """Extract text from various document formats."""
    file_ext = file_ext.lower()

    try:
        if file_ext in [".txt", ".md"]:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()

        elif file_ext == ".pdf":
            return await extract_text_from_pdf(file_path)

        elif file_ext in [".docx", ".doc"]:
            return await extract_text_from_docx(file_path)

        elif file_ext == ".html":
            return await extract_text_from_html(file_path)

        else:
            logger.warning(f"Unsupported file type: {file_ext}")
            return None

    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        return None


async def extract_text_from_pdf(file_path: str) -> Optional[str]:
    """Extract text from PDF using available libraries."""
    text = ""

    # Try PyPDF2 first
    try:
        import PyPDF2
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n\n"

        if text.strip():
            return text.strip()

    except ImportError:
        logger.info("PyPDF2 not available")
    except Exception as e:
        logger.warning(f"PyPDF2 extraction failed: {e}")

    # Try pdfplumber as fallback
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"

        if text.strip():
            return text.strip()

    except ImportError:
        logger.info("pdfplumber not available")
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")

    # Try pymupdf (fitz) as last resort
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text() + "\n\n"
        doc.close()

        if text.strip():
            return text.strip()

    except ImportError:
        logger.info("PyMuPDF not available")
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed: {e}")

    logger.error("No PDF extraction library available or all failed")
    return None


async def extract_text_from_docx(file_path: str) -> Optional[str]:
    """Extract text from DOCX files."""
    try:
        import docx
        doc = docx.Document(file_path)
        text = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        return text.strip() if text else None

    except ImportError:
        logger.warning("python-docx not available")
        return None
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        return None


async def extract_text_from_html(file_path: str) -> Optional[str]:
    """Extract text from HTML files."""
    try:
        from bs4 import BeautifulSoup
        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        text = soup.get_text(separator="\n")
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        text = "\n".join(line for line in lines if line)

        return text

    except ImportError:
        logger.warning("BeautifulSoup not available")
        return None
    except Exception as e:
        logger.error(f"HTML extraction failed: {e}")
        return None


# =============================================================================
# AI ANALYSIS
# =============================================================================

async def analyze_guideline_content(text: str, guideline_name: str) -> Dict[str, Any]:
    """Use Claude to analyze guideline content and extract key information."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Truncate if too long
    if len(text) > 100000:
        text = text[:50000] + "\n\n[...content truncated...]\n\n" + text[-50000:]

    prompt = f"""Analyze this underwriting guideline document and extract key information.

Document Name: {guideline_name}

Document Content:
{text}

---

Please provide a JSON response with:
1. "summary": A 2-3 sentence summary of what this guideline covers
2. "key_points": List of 5-10 key requirements or rules (each should be a specific, actionable requirement)
3. "keywords": List of 10-20 keywords for searching this guideline
4. "structured_rules": If applicable, extract any specific numeric requirements like:
   - Credit score minimums
   - DTI maximums
   - LTV limits
   - Reserve requirements
   - Waiting periods for credit events

Format as JSON:
```json
{{
    "summary": "...",
    "key_points": ["...", "..."],
    "keywords": ["...", "..."],
    "structured_rules": {{
        "min_credit_score": {{}},
        "max_dti": {{}},
        "max_ltv": {{}},
        ...
    }}
}}
```

Only include structured_rules if specific numbers are mentioned in the document."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text

        # Extract JSON
        import json
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        else:
            json_str = response_text

        return json.loads(json_str)

    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return {
            "summary": None,
            "key_points": [],
            "keywords": [],
            "structured_rules": {}
        }


async def extract_key_points(text: str) -> List[str]:
    """Extract key points from guideline text."""
    result = await analyze_guideline_content(text, "Guideline")
    return result.get("key_points", [])


# =============================================================================
# SECTION SPLITTING
# =============================================================================

def split_into_sections(text: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Split guideline text into searchable sections."""
    sections = []

    # Try to detect section patterns
    # Pattern 1: Fannie Mae style (B3-3.1-07)
    fannie_pattern = r"([A-Z]\d+-\d+(?:\.\d+)?(?:-\d+)?)\s+([^\n]+)"

    # Pattern 2: Numbered sections (1.1, 2.3.4)
    numbered_pattern = r"(\d+(?:\.\d+)+)\s+([^\n]+)"

    # Pattern 3: Simple headers (ALL CAPS or Title Case lines)
    header_pattern = r"^([A-Z][A-Z\s]{10,}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){2,})$"

    # Try Fannie Mae pattern first
    matches = list(re.finditer(fannie_pattern, text))

    if len(matches) >= 3:
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            sections.append({
                "section_number": match.group(1),
                "section_title": match.group(2).strip(),
                "content": text[start:end].strip(),
                "position_start": start,
                "position_end": end,
                "topics": [],
            })

        return sections

    # Try numbered pattern
    matches = list(re.finditer(numbered_pattern, text, re.MULTILINE))

    if len(matches) >= 3:
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            sections.append({
                "section_number": match.group(1),
                "section_title": match.group(2).strip(),
                "content": text[start:end].strip(),
                "position_start": start,
                "position_end": end,
                "topics": [],
            })

        return sections

    # Fallback: split by paragraphs for long documents
    if len(text) > 5000:
        paragraphs = text.split("\n\n")
        chunk_size = 2000  # Characters per section

        current_chunk = ""
        current_start = 0
        section_num = 1

        for para in paragraphs:
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                sections.append({
                    "section_number": str(section_num),
                    "section_title": f"Section {section_num}",
                    "content": current_chunk.strip(),
                    "position_start": current_start,
                    "position_end": current_start + len(current_chunk),
                    "topics": [],
                })
                section_num += 1
                current_start += len(current_chunk)
                current_chunk = para
            else:
                current_chunk += "\n\n" + para

        # Add final chunk
        if current_chunk:
            sections.append({
                "section_number": str(section_num),
                "section_title": f"Section {section_num}",
                "content": current_chunk.strip(),
                "position_start": current_start,
                "position_end": len(text),
                "topics": [],
            })

    return sections


# =============================================================================
# SEARCH
# =============================================================================

async def search_guidelines(
    db: Session,
    query: str,
    loan_program: Optional[str] = None,
    category: Optional[str] = None,
    guideline_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search guidelines for relevant content.

    Uses keyword matching on full text and sections.
    """
    from models.call_monitoring_models import UnderwritingGuideline, GuidelineSection

    results = []

    # Clean query
    query_lower = query.lower()
    query_terms = [t.strip() for t in query_lower.split() if len(t.strip()) > 2]

    # Build base guideline filter
    guideline_filter = [UnderwritingGuideline.is_active == True]

    # Tenant isolation: show org-specific guidelines + global guidelines (no org)
    if organization_id:
        guideline_filter.append(
            or_(
                UnderwritingGuideline.organization_id == organization_id,
                UnderwritingGuideline.organization_id.is_(None)
            )
        )

    if loan_program:
        guideline_filter.append(
            or_(
                UnderwritingGuideline.loan_program == loan_program,
                UnderwritingGuideline.loan_program == "all"
            )
        )
    if category:
        guideline_filter.append(UnderwritingGuideline.category == category)
    if guideline_type:
        guideline_filter.append(UnderwritingGuideline.guideline_type == guideline_type)

    # Get matching guidelines
    guidelines = db.query(UnderwritingGuideline).filter(and_(*guideline_filter)).all()

    for guideline in guidelines:
        # Check if query matches guideline level
        guideline_score = 0

        # Check name
        if query_lower in (guideline.name or "").lower():
            guideline_score += 10

        # Check keywords
        for keyword in (guideline.keywords or []):
            if query_lower in keyword.lower() or keyword.lower() in query_lower:
                guideline_score += 5

        # Check tags
        for tag in (guideline.tags or []):
            if query_lower in tag.lower() or tag.lower() in query_lower:
                guideline_score += 3

        # Check key points
        for point in (guideline.key_points or []):
            if any(term in point.lower() for term in query_terms):
                guideline_score += 2

        # Search sections
        sections = db.query(GuidelineSection).filter(
            GuidelineSection.guideline_id == guideline.id
        ).all()

        for section in sections:
            section_score = guideline_score

            # Score based on content match
            content_lower = (section.content or "").lower()
            title_lower = (section.section_title or "").lower()

            # Title match is weighted higher
            if query_lower in title_lower:
                section_score += 15

            # Count term matches in content
            term_matches = sum(1 for term in query_terms if term in content_lower)
            section_score += term_matches * 2

            # Check topics
            for topic in (section.topics or []):
                if query_lower in topic.lower():
                    section_score += 5

            if section_score > 0:
                # Extract relevant snippet
                snippet = extract_relevant_snippet(section.content, query_terms)

                results.append({
                    "guideline_id": str(guideline.id),
                    "guideline_name": guideline.name,
                    "section_id": str(section.id),
                    "section_title": section.section_title,
                    "content_snippet": snippet,
                    "relevance_score": section_score,
                    "category": section.category or guideline.category,
                    "loan_program": guideline.loan_program,
                })

        # If no sections matched but guideline did, include guideline-level result
        if guideline_score > 0 and not any(
            r["guideline_id"] == str(guideline.id) for r in results
        ):
            snippet = extract_relevant_snippet(guideline.full_text or "", query_terms)
            results.append({
                "guideline_id": str(guideline.id),
                "guideline_name": guideline.name,
                "section_id": None,
                "section_title": None,
                "content_snippet": snippet or (guideline.summary or "")[:200],
                "relevance_score": guideline_score,
                "category": guideline.category,
                "loan_program": guideline.loan_program,
            })

    # Sort by relevance and limit
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:limit]


def extract_relevant_snippet(text: str, query_terms: List[str], context_chars: int = 150) -> str:
    """Extract a snippet around the most relevant part of the text."""
    if not text:
        return ""

    text_lower = text.lower()

    # Find the position with the most term matches nearby
    best_pos = 0
    best_score = 0

    for i in range(0, len(text), 50):
        window = text_lower[max(0, i - 100):min(len(text), i + 100)]
        score = sum(1 for term in query_terms if term in window)
        if score > best_score:
            best_score = score
            best_pos = i

    # Extract snippet around best position
    start = max(0, best_pos - context_chars)
    end = min(len(text), best_pos + context_chars)

    snippet = text[start:end].strip()

    # Add ellipsis if truncated
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet


# =============================================================================
# GUIDELINE RETRIEVAL FOR AI AGENTS
# =============================================================================

async def get_relevant_guidelines_for_context(
    db: Session,
    loan_type: Optional[str] = None,
    topics: Optional[List[str]] = None,
    max_chars: int = 8000,
) -> str:
    """
    Get relevant guideline content for AI agent context.

    Returns formatted text that can be included in agent prompts.
    """
    from models.call_monitoring_models import UnderwritingGuideline

    # Get active guidelines for the loan program
    query = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.is_active == True
    )

    if loan_type:
        query = query.filter(
            or_(
                UnderwritingGuideline.loan_program == loan_type.lower(),
                UnderwritingGuideline.loan_program == "all"
            )
        )

    # Prioritize by type
    guidelines = query.order_by(
        # Company overlays first, then investor, then agency
        text("CASE WHEN guideline_type = 'company' THEN 1 "
             "WHEN guideline_type = 'investor' THEN 2 "
             "WHEN guideline_type = 'state' THEN 3 "
             "ELSE 4 END")
    ).all()

    if not guidelines:
        return ""

    # Build context string
    context_parts = []
    current_chars = 0

    for guideline in guidelines:
        # Add key points
        if guideline.key_points:
            points_text = f"\n**{guideline.name}**:\n"
            points_text += "\n".join(f"- {point}" for point in guideline.key_points[:5])

            if current_chars + len(points_text) < max_chars:
                context_parts.append(points_text)
                current_chars += len(points_text)

        # Add structured rules summary
        if guideline.structured_rules:
            rules_text = f"\n**{guideline.name} Rules**:\n"
            rules = guideline.structured_rules

            if "min_credit_score" in rules:
                rules_text += f"- Min Credit: {rules['min_credit_score']}\n"
            if "max_dti" in rules:
                rules_text += f"- Max DTI: {rules['max_dti']}\n"
            if "max_ltv" in rules:
                rules_text += f"- Max LTV: {rules['max_ltv']}\n"

            if current_chars + len(rules_text) < max_chars:
                context_parts.append(rules_text)
                current_chars += len(rules_text)

    return "\n".join(context_parts)


async def get_guideline_answer(
    db: Session,
    question: str,
    loan_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Answer a specific question using the guidelines database.

    Uses AI to find and synthesize relevant information.
    """
    # Search for relevant content
    search_results = await search_guidelines(
        db=db,
        query=question,
        loan_program=loan_type,
        limit=5
    )

    if not search_results:
        return {
            "answer": "No relevant guidelines found for this question.",
            "sources": [],
            "confidence": 0.0
        }

    # Build context from search results
    context = "\n\n".join([
        f"**{r['guideline_name']}** ({r['section_title'] or 'General'}):\n{r['content_snippet']}"
        for r in search_results
    ])

    # Use AI to answer
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""Based on the following underwriting guideline excerpts, answer this question:

Question: {question}

Relevant Guidelines:
{context}

---

Provide a clear, specific answer based only on the information in the guidelines above.
If the guidelines don't fully answer the question, say what is known and what is unclear.
Include specific guideline citations where possible."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        return {
            "answer": response.content[0].text,
            "sources": [
                {"name": r["guideline_name"], "section": r["section_title"]}
                for r in search_results
            ],
            "confidence": min(search_results[0]["relevance_score"] / 20, 1.0)
        }

    except Exception as e:
        logger.error(f"AI answer generation failed: {e}")
        return {
            "answer": f"Found relevant guidelines but could not generate answer: {e}",
            "sources": [
                {"name": r["guideline_name"], "section": r["section_title"]}
                for r in search_results
            ],
            "confidence": 0.3
        }
