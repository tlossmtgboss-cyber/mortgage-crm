"""
Estimate Parser API Routes

Endpoints for parsing loan estimates, fee worksheets, and closing disclosures.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from services.estimate_parser_service import (
    EstimateParserService,
    LoanEstimate,
    ParseResult,
    ComparisonResult,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/estimate-parser", tags=["estimate-parser"])


# ============================================================================
# SCHEMAS
# ============================================================================

class ParseResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    request_id: str


class CompareRequest(BaseModel):
    estimate_a_hash: str
    estimate_b_hash: str
    session_id: Optional[str] = None


class CompareResponse(BaseModel):
    success: bool
    winner: Optional[str] = None
    reason: Optional[str] = None
    savings_amount: Optional[float] = None
    savings_message: Optional[str] = None
    estimate_a: Optional[dict] = None
    estimate_b: Optional[dict] = None
    comparison_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    environment: dict


# ============================================================================
# RATE LIMITING (Simple in-memory)
# ============================================================================

from collections import defaultdict
from datetime import datetime, timedelta
import threading

_rate_limits = defaultdict(list)
_rate_lock = threading.Lock()

RATE_LIMIT_REQUESTS = 20  # per hour
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds


def check_rate_limit(ip: str) -> bool:
    """Check if IP is within rate limit"""
    now = datetime.now()
    cutoff = now - timedelta(seconds=RATE_LIMIT_WINDOW)

    with _rate_lock:
        # Clean old entries
        _rate_limits[ip] = [t for t in _rate_limits[ip] if t > cutoff]

        # Check limit
        if len(_rate_limits[ip]) >= RATE_LIMIT_REQUESTS:
            return False

        # Record request
        _rate_limits[ip].append(now)
        return True


def get_client_ip(request: Request) -> str:
    """Get client IP from request"""
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    Returns configuration status without exposing sensitive values.
    """
    import os

    env_vars = [
        'DATABASE_URL',
        'AWS_REGION',
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY',
        'TEXTRACT_S3_BUCKET',
        'ANTHROPIC_API_KEY',
        'OPENAI_API_KEY',
        'LLM_API_KEY',
    ]

    environment = {}
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'KEY' in var or 'SECRET' in var or 'URL' in var:
                environment[var] = 'configured'
            else:
                environment[var] = value
        else:
            environment[var] = 'not configured'

    return HealthResponse(
        status='healthy',
        environment=environment
    )


@router.post("/parse", response_model=ParseResponse)
async def parse_estimate(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Parse a loan estimate document.

    Accepts PDF or image (JPG, PNG, WebP) files up to 15MB.
    Returns structured JSON with loan details, confidence score, and provenance snippets.

    **File Types:**
    - PDF (native text or scanned)
    - JPEG/JPG
    - PNG
    - WebP

    **Response includes:**
    - loan_amount, interest_rate, apr
    - monthly_principal_and_interest
    - total_closing_costs, cash_to_close
    - loan_type, loan_term
    - confidence score and review flag
    - provenance snippets showing source text
    """
    request_id = str(uuid.uuid4())

    # Rate limiting
    client_ip = get_client_ip(request)
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={
                'success': False,
                'error': 'Rate limit exceeded. Please try again later.',
                'request_id': request_id,
            },
            headers={
                'X-RateLimit-Limit': str(RATE_LIMIT_REQUESTS),
                'Retry-After': str(RATE_LIMIT_WINDOW),
            }
        )

    try:
        # Validate content type
        content_type = file.content_type or ''
        if content_type not in ALLOWED_MIME_TYPES:
            return ParseResponse(
                success=False,
                error=f'File type {content_type} not supported. Please upload PDF or image (JPG, PNG, WebP).',
                request_id=request_id
            )

        # Read file content
        content = await file.read()

        # Validate size
        if len(content) > MAX_FILE_SIZE:
            size_mb = len(content) / (1024 * 1024)
            return ParseResponse(
                success=False,
                error=f'File too large ({size_mb:.1f}MB). Maximum size is 15MB.',
                request_id=request_id
            )

        # Parse document
        service = EstimateParserService(db)
        service.request_id = request_id

        result = await service.parse_estimate(
            file_content=content,
            filename=file.filename or 'document',
            mime_type=content_type,
        )

        if result.success:
            return ParseResponse(
                success=True,
                data=result.data.dict() if result.data else None,
                request_id=request_id
            )
        else:
            return ParseResponse(
                success=False,
                error=result.error,
                request_id=request_id
            )

    except Exception as e:
        logger.exception(f"[{request_id}] Parse endpoint error: {e}")
        return ParseResponse(
            success=False,
            error='Internal server error',
            request_id=request_id
        )


@router.post("/compare", response_model=CompareResponse)
async def compare_estimates(
    request: Request,
    data: CompareRequest,
    db: Session = Depends(get_db),
    user_id: Optional[int] = None,  # Could come from auth
):
    """
    Compare two parsed estimates.

    Requires doc_hash values from previous parse operations.
    Returns winner, reason, and savings amount.

    **Comparison Priority:**
    1. Cash to Close (lower wins)
    2. Total Closing Costs (lower wins)
    3. APR (lower wins)
    4. Monthly P&I (lower wins)
    """
    comparison_id = str(uuid.uuid4())

    try:
        # Fetch both estimates from cache
        result_a = db.execute(text("""
            SELECT parsed_json FROM estimate_parse_cache WHERE doc_hash = :hash
        """), {'hash': data.estimate_a_hash}).fetchone()

        result_b = db.execute(text("""
            SELECT parsed_json FROM estimate_parse_cache WHERE doc_hash = :hash
        """), {'hash': data.estimate_b_hash}).fetchone()

        if not result_a:
            raise HTTPException(status_code=404, detail='First estimate not found. Please re-upload.')

        if not result_b:
            raise HTTPException(status_code=404, detail='Second estimate not found. Please re-upload.')

        # Parse into models
        estimate_a = LoanEstimate(**result_a[0])
        estimate_b = LoanEstimate(**result_b[0])

        # Compare
        service = EstimateParserService(db)
        comparison = service.compare_estimates(estimate_a, estimate_b)

        # Generate savings message
        savings_message = None
        if comparison.savings_amount:
            if comparison.savings_amount >= 1500:
                savings_message = f"Save about ${int(comparison.savings_amount / 100) * 100:,}"
            elif comparison.savings_amount >= 500:
                savings_message = "Often tighten by around $1,500"
            else:
                savings_message = "Want me to try to cut $1,500?"

        # Store comparison for analytics
        try:
            db.execute(text("""
                INSERT INTO estimate_comparisons (
                    id, user_id, session_id, estimate_a_hash, estimate_b_hash,
                    winner, winner_reason, savings_amount
                ) VALUES (
                    :id, :user_id, :session_id, :a_hash, :b_hash,
                    :winner, :reason, :savings
                )
            """), {
                'id': comparison_id,
                'user_id': user_id,
                'session_id': data.session_id,
                'a_hash': data.estimate_a_hash,
                'b_hash': data.estimate_b_hash,
                'winner': comparison.winner,
                'reason': comparison.reason,
                'savings': comparison.savings_amount,
            })
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to store comparison: {e}")
            db.rollback()

        return CompareResponse(
            success=True,
            winner=comparison.winner,
            reason=comparison.reason,
            savings_amount=comparison.savings_amount,
            savings_message=savings_message,
            estimate_a=estimate_a.dict(),
            estimate_b=estimate_b.dict(),
            comparison_id=comparison_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Compare endpoint error: {e}")
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post("/compare/convert")
async def mark_comparison_converted(
    comparison_id: str = Query(..., description="Comparison ID to mark as converted"),
    db: Session = Depends(get_db),
):
    """
    Mark a comparison as converted (user clicked CTA).
    Used for conversion tracking and analytics.
    """
    try:
        result = db.execute(text("""
            UPDATE estimate_comparisons
            SET converted = true
            WHERE id = :id
            RETURNING id
        """), {'id': comparison_id})

        if result.fetchone():
            db.commit()
            return {'success': True, 'comparison_id': comparison_id}
        else:
            raise HTTPException(status_code=404, detail='Comparison not found')

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Convert endpoint error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get("/compare/{comparison_id}/pdf")
async def download_comparison_pdf(
    comparison_id: str,
    db: Session = Depends(get_db),
):
    """
    Download comparison results as PDF.
    Returns a PDF document with side-by-side comparison.
    """
    from fastapi.responses import Response

    try:
        # Fetch comparison data
        comp = db.execute(text("""
            SELECT
                ec.id, ec.estimate_a_hash, ec.estimate_b_hash,
                ec.winner, ec.winner_reason, ec.savings_amount,
                ea.parsed_json as estimate_a_json,
                eb.parsed_json as estimate_b_json
            FROM estimate_comparisons ec
            LEFT JOIN estimate_parse_cache ea ON ea.doc_hash = ec.estimate_a_hash
            LEFT JOIN estimate_parse_cache eb ON eb.doc_hash = ec.estimate_b_hash
            WHERE ec.id = :id
        """), {'id': comparison_id}).fetchone()

        if not comp:
            raise HTTPException(status_code=404, detail='Comparison not found')

        # Reconstruct LoanEstimate objects
        estimate_a = LoanEstimate(**comp[6]) if comp[6] else None
        estimate_b = LoanEstimate(**comp[7]) if comp[7] else None

        from services.estimate_parser_service import ComparisonResult
        comparison = ComparisonResult(
            winner=comp[3],
            reason=comp[4],
            savings_amount=float(comp[5]) if comp[5] else None,
            estimate_a=estimate_a,
            estimate_b=estimate_b
        )

        # Generate PDF
        service = EstimateParserService(db)
        pdf_bytes = service.generate_comparison_pdf(comparison, comparison_id)

        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="loan_comparison_{comparison_id[:8]}.pdf"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"PDF generation error: {e}")
        raise HTTPException(status_code=500, detail='Failed to generate PDF')


@router.get("/stats")
async def get_parse_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """
    Get parsing statistics for monitoring.
    """
    try:
        # Cache stats
        cache_stats = db.execute(text("""
            SELECT
                COUNT(*) as total_cached,
                COUNT(CASE WHEN needs_review THEN 1 END) as needs_review,
                AVG(confidence_score) as avg_confidence,
                SUM(access_count) as total_accesses
            FROM estimate_parse_cache
            WHERE created_at >= NOW() - :days * INTERVAL '1 day'
        """), {'days': days}).fetchone()

        # Failure stats
        failure_stats = db.execute(text("""
            SELECT
                error_stage,
                COUNT(*) as count
            FROM estimate_parse_failures
            WHERE created_at >= NOW() - :days * INTERVAL '1 day'
            GROUP BY error_stage
            ORDER BY count DESC
        """), {'days': days}).fetchall()

        # Comparison stats
        comparison_stats = db.execute(text("""
            SELECT
                COUNT(*) as total_comparisons,
                COUNT(CASE WHEN converted THEN 1 END) as conversions,
                COUNT(CASE WHEN winner = 'A' THEN 1 END) as estimate_a_wins,
                COUNT(CASE WHEN winner = 'B' THEN 1 END) as estimate_b_wins,
                AVG(savings_amount) as avg_savings
            FROM estimate_comparisons
            WHERE created_at >= NOW() - :days * INTERVAL '1 day'
        """), {'days': days}).fetchone()

        return {
            'period_days': days,
            'cache': {
                'total_cached': cache_stats[0] or 0,
                'needs_review': cache_stats[1] or 0,
                'avg_confidence': float(cache_stats[2] or 0),
                'total_accesses': cache_stats[3] or 0,
            },
            'failures': {row[0]: row[1] for row in failure_stats},
            'comparisons': {
                'total': comparison_stats[0] or 0,
                'conversions': comparison_stats[1] or 0,
                'conversion_rate': (comparison_stats[1] / comparison_stats[0] * 100) if comparison_stats[0] else 0,
                'estimate_a_wins': comparison_stats[2] or 0,
                'estimate_b_wins': comparison_stats[3] or 0,
                'avg_savings': float(comparison_stats[4] or 0),
            }
        }

    except Exception as e:
        logger.error(f"Stats endpoint error: {e}")
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get("/cache/{doc_hash}")
async def get_cached_estimate(
    doc_hash: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve a cached estimate by document hash.
    """
    try:
        result = db.execute(text("""
            SELECT parsed_json, confidence_score, needs_review, source_type, created_at
            FROM estimate_parse_cache
            WHERE doc_hash = :hash
        """), {'hash': doc_hash}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail='Estimate not found')

        return {
            'doc_hash': doc_hash,
            'data': result[0],
            'confidence_score': float(result[1]) if result[1] else None,
            'needs_review': result[2],
            'source_type': result[3],
            'created_at': result[4].isoformat() if result[4] else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cache lookup error: {e}")
        raise HTTPException(status_code=500, detail='Internal server error')


# ============================================================================
# AI CRITIQUE & Q&A ENDPOINTS (Connected to Agent Orchestration)
# ============================================================================

class CritiqueRequest(BaseModel):
    comparison_id: Optional[str] = None
    estimate_a: dict
    estimate_b: dict
    winner: Optional[str] = None
    savings_amount: Optional[float] = None


class CritiqueResponse(BaseModel):
    success: bool
    critique: Optional[str] = None
    error: Optional[str] = None


class AskRequest(BaseModel):
    question: str
    comparison_id: Optional[str] = None
    estimate_a: Optional[dict] = None
    estimate_b: Optional[dict] = None
    context: Optional[str] = None
    conversation_history: Optional[list] = None


class AskResponse(BaseModel):
    success: bool
    answer: Optional[str] = None
    error: Optional[str] = None
    suggested_action: Optional[str] = None


def format_currency(amount):
    """Format amount as currency string"""
    if amount is None:
        return "N/A"
    return f"${amount:,.0f}"


def format_rate(rate):
    """Format rate as percentage string"""
    if rate is None:
        return "N/A"
    return f"{rate:.3f}%"


@router.post("/critique", response_model=CritiqueResponse)
async def generate_critique(
    request: Request,
    data: CritiqueRequest,
):
    """
    Generate AI critique of two loan estimates.

    Uses the Estimate Advisor agent (Sarah - Senior Loan Officer) to provide
    expert analysis and guide users toward scheduling a consultation.
    """
    import os
    import anthropic

    try:
        # Build context for AI
        estimate_a = data.estimate_a
        estimate_b = data.estimate_b
        winner = data.winner or "A"
        savings = data.savings_amount or 0

        # Create system prompt as a Loan Officer
        system_prompt = """You are Sarah, a Senior Loan Officer with 15 years of experience. You're analyzing two loan estimates for a potential client.

Your personality:
- Expert and knowledgeable, but approachable
- You explain things clearly without jargon
- You're consultative - you help them understand their options
- You genuinely want to help them save money
- You're confident you can often beat the rates they're seeing

Your goal: Help them understand the estimates AND guide them toward scheduling a free consultation call where you can find them an even better deal.

Important rules:
- Be concise (under 150 words)
- Use specific numbers from the estimates
- End with a soft call-to-action about scheduling a call
- Don't be pushy, be helpful
- Use "I" and speak as yourself (Sarah)"""

        # Build the comparison context
        user_message = f"""Please analyze these two loan estimates and provide your expert critique:

**Estimate A:**
- Loan Amount: {format_currency(estimate_a.get('loan_amount'))}
- Interest Rate: {format_rate(estimate_a.get('interest_rate'))}
- APR: {format_rate(estimate_a.get('apr'))}
- Monthly P&I: {format_currency(estimate_a.get('monthly_principal_and_interest'))}
- Total Closing Costs: {format_currency(estimate_a.get('total_closing_costs'))}
- Cash to Close: {format_currency(estimate_a.get('cash_to_close'))}

**Estimate B:**
- Loan Amount: {format_currency(estimate_b.get('loan_amount'))}
- Interest Rate: {format_rate(estimate_b.get('interest_rate'))}
- APR: {format_rate(estimate_b.get('apr'))}
- Monthly P&I: {format_currency(estimate_b.get('monthly_principal_and_interest'))}
- Total Closing Costs: {format_currency(estimate_b.get('total_closing_costs'))}
- Cash to Close: {format_currency(estimate_b.get('cash_to_close'))}

**Analysis shows:** Estimate {winner} is better{f', saving approximately {format_currency(savings)}' if savings > 0 else ''}.

Provide your expert analysis as Sarah the Loan Officer. Help them understand the key differences and what they mean for their wallet. End by offering to see if you can find them something even better."""

        # Call Claude API
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )

        critique = response.content[0].text

        return CritiqueResponse(
            success=True,
            critique=critique
        )

    except Exception as e:
        logger.exception(f"Critique generation error: {e}")
        return CritiqueResponse(
            success=False,
            error=str(e)
        )


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: Request,
    data: AskRequest,
):
    """
    Answer questions about loan estimates using AI.

    Uses the Estimate Advisor agent (Sarah - Senior Loan Officer) to provide
    expert answers and guide users toward scheduling a consultation.
    """
    import os
    import anthropic

    try:
        # Build context
        estimate_a = data.estimate_a or {}
        estimate_b = data.estimate_b or {}

        # Create system prompt as a Loan Officer
        system_prompt = """You are Sarah, a Senior Loan Officer with 15 years of experience helping people find the best mortgage rates.

Your personality:
- Expert and knowledgeable, but friendly and approachable
- You explain mortgage concepts clearly without jargon
- You're genuinely helpful and want them to get the best deal
- You're confident you can often find better rates than what they're seeing

Your goal: Answer their question helpfully AND when appropriate, suggest scheduling a free consultation call where you can help them further.

Important rules:
- Keep answers concise (under 100 words)
- Use specific numbers when relevant
- Be helpful first, promotional second
- If they ask about rates/deals, mention you might be able to find something better
- Sign off as "- Sarah" occasionally to feel personal
- Don't be pushy, be genuinely helpful"""

        # Build context message
        context_parts = []

        if estimate_a:
            context_parts.append(f"""Estimate A: {format_currency(estimate_a.get('loan_amount'))} loan at {format_rate(estimate_a.get('interest_rate'))}, {format_currency(estimate_a.get('cash_to_close'))} cash to close""")

        if estimate_b:
            context_parts.append(f"""Estimate B: {format_currency(estimate_b.get('loan_amount'))} loan at {format_rate(estimate_b.get('interest_rate'))}, {format_currency(estimate_b.get('cash_to_close'))} cash to close""")

        if data.context:
            context_parts.append(f"Previous analysis: {data.context[:500]}")

        context_str = "\n".join(context_parts) if context_parts else "No specific estimate context provided."

        user_message = f"""Context about the loan estimates being compared:
{context_str}

The user asks: "{data.question}"

Please answer as Sarah the Loan Officer. Be helpful and specific. If relevant, mention that a quick call could help them explore better options."""

        # Call Claude API
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )

        answer = response.content[0].text

        # Determine if we should suggest scheduling
        suggested_action = None
        question_lower = data.question.lower()
        if any(word in question_lower for word in ['better', 'best', 'recommend', 'should', 'help', 'what do you think']):
            suggested_action = "schedule_call"

        return AskResponse(
            success=True,
            answer=answer,
            suggested_action=suggested_action
        )

    except Exception as e:
        logger.exception(f"Ask endpoint error: {e}")
        return AskResponse(
            success=False,
            error=str(e)
        )


@router.get("/failures")
async def get_parse_failures(
    limit: int = Query(50, ge=1, le=200),
    stage: Optional[str] = Query(None, description="Filter by error stage"),
    db: Session = Depends(get_db),
):
    """
    Get recent parse failures for review.
    """
    try:
        if stage:
            result = db.execute(text("""
                SELECT id, request_id, doc_hash, error_stage, error_message, created_at
                FROM estimate_parse_failures
                WHERE error_stage = :stage
                ORDER BY created_at DESC
                LIMIT :limit
            """), {'stage': stage, 'limit': limit}).fetchall()
        else:
            result = db.execute(text("""
                SELECT id, request_id, doc_hash, error_stage, error_message, created_at
                FROM estimate_parse_failures
                ORDER BY created_at DESC
                LIMIT :limit
            """), {'limit': limit}).fetchall()

        return {
            'failures': [
                {
                    'id': row[0],
                    'request_id': row[1],
                    'doc_hash': row[2],
                    'error_stage': row[3],
                    'error_message': row[4],
                    'created_at': row[5].isoformat() if row[5] else None,
                }
                for row in result
            ]
        }

    except Exception as e:
        logger.error(f"Failures endpoint error: {e}")
        raise HTTPException(status_code=500, detail='Internal server error')
