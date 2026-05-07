"""
Intelligent Email Monitor - FastAPI Routes
3-stage filtering with Claude AI
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc, case
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import anthropic
import re
import json
import logging
import os

logger = logging.getLogger(__name__)

from database import get_db
# Lazy import to avoid circular imports
async def get_current_user_flexible(request: Request, db: Session = Depends(get_db)):
    """Lazy import wrapper to avoid circular imports"""
    from auth.dependencies import get_current_user_flexible as _get_current_user_flexible
    return await _get_current_user_flexible(request, db)

from models.email_monitor import (
    EmailMonitorCaptured,
    EmailCRMLink,
    EmailRelevanceAnalysis,
    EmailFilterWhitelist,
    EmailFilterBlacklist,
    EmailProviderConfig,
    EmailMonitorLog,
    EmailMonitorRule,
    EmailProviderEnum,
    ProcessingStatusEnum,
    FilterStageEnum
)

router = APIRouter(prefix="/api/v1/email-monitor", tags=["email-monitor"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class EmailAnalysisResult(BaseModel):
    is_relevant: bool
    category: str
    confidence: float
    reason: str
    matched_entities: List[Dict[str, Any]] = []
    auto_link: List[Dict[str, Any]] = []
    filter_stage: str


class CapturedEmailResponse(BaseModel):
    id: int
    email_provider: str
    from_email: str
    subject: str
    received_date: datetime
    processing_status: str
    linked_entities: List[Dict[str, Any]] = []
    ai_confidence: Optional[float]
    relevance_category: Optional[str]

    class Config:
        from_attributes = True


class ProviderStatsResponse(BaseModel):
    email_provider: str
    total_captured: int
    auto_linked_count: int
    pending_review: int
    avg_confidence: float


class WhitelistRequest(BaseModel):
    email_pattern: str
    description: Optional[str] = None
    whitelist_type: str = "email"
    auto_assign_category: Optional[str] = None


class BlacklistRequest(BaseModel):
    email_pattern: str
    description: Optional[str] = None
    blacklist_type: str = "email"
    reason: Optional[str] = None


class TestAnalysisRequest(BaseModel):
    from_email: EmailStr
    subject: str
    body_preview: str


# ============================================================================
# EMAIL INTELLIGENCE FILTER
# ============================================================================

class EmailIntelligenceFilter:
    """3-stage intelligent email filtering"""

    SPAM_INDICATORS = [
        'unsubscribe', 'marketing@', 'noreply@', 'do-not-reply',
        'newsletter', 'promotional', 'special offer', 'limited time',
        'black friday', 'cyber monday', 'holiday sale', 'flash sale',
        'deal of the day', 'exclusive offer', 'act now', 'don\'t miss',
        'save big', 'discount code', 'promo code', 'coupon',
        'clearance', 'final sale', 'last chance', 'ends today',
        'free shipping', 'buy one get one', 'doorbuster'
    ]

    def __init__(self, db: Session, anthropic_api_key: str):
        self.db = db
        self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)

    async def analyze_email_relevance(self, email_data: Dict[str, Any]) -> EmailAnalysisResult:
        """Main entry point - 3 stages"""

        # Stage 1: Quick spam detection
        spam_check = self._quick_spam_check(email_data)
        if spam_check['is_spam']:
            return EmailAnalysisResult(
                is_relevant=False,
                category="SPAM",
                confidence=1.0,
                reason=spam_check['reason'],
                filter_stage="quick_spam"
            )

        # Stage 2: CRM entity matching
        crm_matches = await self._match_crm_entities(email_data)
        if crm_matches:
            return EmailAnalysisResult(
                is_relevant=True,
                category=crm_matches['category'],
                confidence=crm_matches['confidence'],
                reason=crm_matches['reason'],
                matched_entities=crm_matches['entities'],
                auto_link=crm_matches['auto_link'],
                filter_stage="crm_match"
            )

        # Stage 3: AI analysis
        ai_analysis = await self._ai_relevance_analysis(email_data)
        return ai_analysis

    def _quick_spam_check(self, email: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 1: Quick spam detection"""
        from_email = email.get('from', '').lower()
        subject = email.get('subject', '').lower()
        body = email.get('body_preview', '').lower()

        for indicator in self.SPAM_INDICATORS:
            if indicator in from_email or indicator in subject or indicator in body:
                if not self._is_whitelisted(from_email):
                    return {'is_spam': True, 'reason': f'Spam indicator: {indicator}'}

        if self._is_blacklisted(from_email):
            return {'is_spam': True, 'reason': 'Sender blacklisted'}

        return {'is_spam': False}

    def _is_whitelisted(self, email: str) -> bool:
        """Check whitelist"""
        whitelist = self.db.query(EmailFilterWhitelist).filter(
            EmailFilterWhitelist.is_active == True
        ).all()

        for entry in whitelist:
            pattern = entry.email_pattern.replace('*', '.*')
            if re.match(pattern, email, re.IGNORECASE):
                return True
        return False

    def _is_blacklisted(self, email: str) -> bool:
        """Check blacklist"""
        blacklist = self.db.query(EmailFilterBlacklist).filter(
            EmailFilterBlacklist.is_active == True
        ).all()

        for entry in blacklist:
            pattern = entry.email_pattern.replace('*', '.*')
            if re.match(pattern, email, re.IGNORECASE):
                return True
        return False

    async def _match_crm_entities(self, email: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Stage 2: CRM matching using raw SQL to avoid circular imports"""
        from sqlalchemy import text

        from_email = email.get('from', '')
        subject = email.get('subject', '')
        body = email.get('body_preview', '')

        # Extract loan numbers
        loan_numbers = self._extract_loan_numbers(subject + ' ' + body)
        if loan_numbers:
            # Query loans by loan number
            placeholders = ', '.join([f':ln{i}' for i in range(len(loan_numbers))])
            params = {f'ln{i}': ln for i, ln in enumerate(loan_numbers)}

            result = self.db.execute(
                text(f"""
                    SELECT id, loan_number FROM loans
                    WHERE loan_number IN ({placeholders})
                    AND current_stage NOT IN ('Closed', 'Withdrawn')
                """),
                params
            ).fetchall()

            if result:
                return {
                    'category': 'LOAN_COMMUNICATION',
                    'confidence': 0.95,
                    'reason': f'Loan number(s) found',
                    'entities': [{'type': 'loan', 'id': r[0]} for r in result],
                    'auto_link': [{'type': 'loan', 'id': r[0]} for r in result]
                }

        # Match borrower email
        result = self.db.execute(
            text("""
                SELECT id FROM loans
                WHERE (borrower_email = :email OR co_borrower_email = :email)
                AND current_stage NOT IN ('Closed', 'Withdrawn')
                LIMIT 1
            """),
            {'email': from_email}
        ).fetchone()

        if result:
            return {
                'category': 'LOAN_COMMUNICATION',
                'confidence': 0.95,
                'reason': f'Email from borrower',
                'entities': [{'type': 'borrower', 'id': result[0]}],
                'auto_link': [{'type': 'loan', 'id': result[0]}]
            }

        # Match lead email
        result = self.db.execute(
            text("""
                SELECT id FROM leads
                WHERE email = :email
                AND lead_stage NOT IN ('Withdrawn', 'Does Not Qualify')
                LIMIT 1
            """),
            {'email': from_email}
        ).fetchone()

        if result:
            return {
                'category': 'LEAD_INQUIRY',
                'confidence': 0.90,
                'reason': f'Email from known lead',
                'entities': [{'type': 'lead', 'id': result[0]}],
                'auto_link': [{'type': 'lead', 'id': result[0]}]
            }

        # Match referral partner
        result = self.db.execute(
            text("""
                SELECT id, name FROM referral_partners
                WHERE email = :email AND is_active = true
                LIMIT 1
            """),
            {'email': from_email}
        ).fetchone()

        if result:
            return {
                'category': 'REFERRAL_PARTNER',
                'confidence': 0.85,
                'reason': f'Email from referral partner: {result[1]}',
                'entities': [{'type': 'referral_partner', 'id': result[0]}],
                'auto_link': [{'type': 'referral_partner', 'id': result[0]}]
            }

        return None

    def _extract_loan_numbers(self, text: str) -> List[str]:
        """Extract loan numbers from text"""
        loan_numbers = []

        matches = re.findall(r'loan\s*(?:#|number)?\s*:?\s*([0-9A-Z-]{6,20})', text, re.IGNORECASE)
        loan_numbers.extend(matches)

        matches = re.findall(r'file\s*(?:#|number)?\s*:?\s*([0-9A-Z-]{6,20})', text, re.IGNORECASE)
        loan_numbers.extend(matches)

        return list(set(loan_numbers))

    async def _ai_relevance_analysis(self, email: Dict[str, Any]) -> EmailAnalysisResult:
        """Stage 3: AI analysis"""

        prompt = f"""Analyze if this email is relevant to a mortgage business.

EMAIL:
From: {email.get('from')}
Subject: {email.get('subject')}
Body: {email.get('body_preview')}

RESPOND WITH ONLY VALID JSON:
{{
  "is_relevant": true/false,
  "category": "LOAN_COMMUNICATION|LEAD_INQUIRY|CLIENT_COMMUNICATION|REFERRAL_PARTNER|THIRD_PARTY_VENDOR|SPAM|IRRELEVANT",
  "confidence": 0.0-1.0,
  "reason": "Brief explanation"
}}

DO NOT OUTPUT ANYTHING OTHER THAN VALID JSON."""

        try:
            message = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text
            response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()

            analysis = json.loads(response_text)

            return EmailAnalysisResult(
                is_relevant=analysis.get('is_relevant', False),
                category=analysis.get('category', 'IRRELEVANT'),
                confidence=analysis.get('confidence', 0.0),
                reason=analysis.get('reason', ''),
                filter_stage="ai_analysis"
            )

        except Exception as e:
            return EmailAnalysisResult(
                is_relevant=False,
                category="IRRELEVANT",
                confidence=0.0,
                reason=f'AI failed: {str(e)}',
                filter_stage="ai_analysis"
            )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/stats", response_model=List[ProviderStatsResponse])
async def get_provider_stats(db: Session = Depends(get_db)):
    """Get stats by provider"""

    stats_query = db.query(
        EmailMonitorCaptured.email_provider,
        func.count(EmailMonitorCaptured.id).label('total_captured'),
        func.sum(
            case((EmailMonitorCaptured.processing_status == 'assigned', 1), else_=0)
        ).label('auto_linked_count'),
        func.sum(
            case((EmailMonitorCaptured.processing_status == 'manual_review', 1), else_=0)
        ).label('pending_review')
    ).group_by(EmailMonitorCaptured.email_provider).all()

    results = []
    for stat in stats_query:
        avg_conf = db.query(func.avg(EmailRelevanceAnalysis.confidence_score)).filter(
            EmailRelevanceAnalysis.email_provider == stat.email_provider,
            EmailRelevanceAnalysis.created_at >= datetime.now() - timedelta(days=30)
        ).scalar() or 0.0

        results.append(ProviderStatsResponse(
            email_provider=stat.email_provider,
            total_captured=stat.total_captured,
            auto_linked_count=stat.auto_linked_count or 0,
            pending_review=stat.pending_review or 0,
            avg_confidence=round(float(avg_conf), 3)
        ))

    return results


@router.get("/captured", response_model=List[CapturedEmailResponse])
async def get_captured_emails(
    provider: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get captured emails"""

    query = db.query(EmailMonitorCaptured)

    if provider:
        query = query.filter(EmailMonitorCaptured.email_provider == provider)

    if status:
        query = query.filter(EmailMonitorCaptured.processing_status == status)

    captured_emails = query.order_by(desc(EmailMonitorCaptured.received_date)).offset(offset).limit(limit).all()

    results = []
    for email in captured_emails:
        links = db.query(EmailCRMLink).filter(
            EmailCRMLink.captured_email_id == email.id
        ).all()

        linked_entities = [{'type': link.entity_type.value if hasattr(link.entity_type, 'value') else link.entity_type, 'id': link.entity_id} for link in links]

        analysis = db.query(EmailRelevanceAnalysis).filter(
            EmailRelevanceAnalysis.provider_message_id == email.provider_message_id,
            EmailRelevanceAnalysis.email_provider == email.email_provider
        ).first()

        results.append(CapturedEmailResponse(
            id=email.id,
            email_provider=email.email_provider.value if hasattr(email.email_provider, 'value') else email.email_provider,
            from_email=email.from_email or '',
            subject=email.subject or '',
            received_date=email.received_date,
            processing_status=email.processing_status.value if hasattr(email.processing_status, 'value') else email.processing_status,
            linked_entities=linked_entities,
            ai_confidence=float(analysis.confidence_score) if analysis and analysis.confidence_score else None,
            relevance_category=analysis.relevance_category if analysis else None
        ))

    return results


@router.get("/whitelist")
async def get_whitelist(db: Session = Depends(get_db)):
    """Get all whitelist entries"""
    entries = db.query(EmailFilterWhitelist).filter(
        EmailFilterWhitelist.is_active == True
    ).all()

    return [
        {
            'id': e.id,
            'email_pattern': e.email_pattern,
            'description': e.description,
            'whitelist_type': e.whitelist_type.value if hasattr(e.whitelist_type, 'value') else e.whitelist_type,
            'auto_assign_category': e.auto_assign_category,
            'created_at': e.created_at
        }
        for e in entries
    ]


@router.post("/whitelist")
async def add_to_whitelist(
    request: WhitelistRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Add email pattern to whitelist"""

    whitelist_entry = EmailFilterWhitelist(
        email_pattern=request.email_pattern,
        description=request.description,
        whitelist_type=request.whitelist_type,
        auto_assign_category=request.auto_assign_category,
        is_active=True,
        created_by=current_user.id
    )

    db.add(whitelist_entry)
    db.commit()
    db.refresh(whitelist_entry)

    return {"id": whitelist_entry.id, "message": "Added to whitelist"}


@router.delete("/whitelist/{entry_id}")
async def remove_from_whitelist(entry_id: int, db: Session = Depends(get_db)):
    """Remove from whitelist"""
    entry = db.query(EmailFilterWhitelist).filter(
        EmailFilterWhitelist.id == entry_id
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry.is_active = False
    db.commit()

    return {"message": "Removed from whitelist"}


@router.get("/blacklist")
async def get_blacklist(db: Session = Depends(get_db)):
    """Get all blacklist entries"""
    entries = db.query(EmailFilterBlacklist).filter(
        EmailFilterBlacklist.is_active == True
    ).all()

    return [
        {
            'id': e.id,
            'email_pattern': e.email_pattern,
            'description': e.description,
            'blacklist_type': e.blacklist_type.value if hasattr(e.blacklist_type, 'value') else e.blacklist_type,
            'reason': e.reason,
            'created_at': e.created_at
        }
        for e in entries
    ]


@router.post("/blacklist")
async def add_to_blacklist(
    request: BlacklistRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Add email pattern to blacklist"""

    blacklist_entry = EmailFilterBlacklist(
        email_pattern=request.email_pattern,
        description=request.description,
        blacklist_type=request.blacklist_type,
        reason=request.reason,
        is_active=True,
        created_by=current_user.id
    )

    db.add(blacklist_entry)
    db.commit()
    db.refresh(blacklist_entry)

    return {"id": blacklist_entry.id, "message": "Added to blacklist"}


@router.delete("/blacklist/{entry_id}")
async def remove_from_blacklist(entry_id: int, db: Session = Depends(get_db)):
    """Remove from blacklist"""
    entry = db.query(EmailFilterBlacklist).filter(
        EmailFilterBlacklist.id == entry_id
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry.is_active = False
    db.commit()

    return {"message": "Removed from blacklist"}


@router.post("/test-analysis")
async def test_email_analysis(
    request: TestAnalysisRequest,
    db: Session = Depends(get_db)
):
    """Test email analysis without capturing"""

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    filter_engine = EmailIntelligenceFilter(db, api_key)

    email_data = {
        'from': request.from_email,
        'subject': request.subject,
        'body_preview': request.body_preview
    }

    result = await filter_engine.analyze_email_relevance(email_data)
    return result


@router.get("/analysis-log")
async def get_analysis_log(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get recent email analysis results"""

    analyses = db.query(EmailRelevanceAnalysis).order_by(
        desc(EmailRelevanceAnalysis.created_at)
    ).offset(offset).limit(limit).all()

    return [
        {
            'id': a.id,
            'email_provider': a.email_provider.value if hasattr(a.email_provider, 'value') else a.email_provider,
            'from_email': a.from_email,
            'subject': a.subject,
            'is_relevant': a.is_relevant,
            'category': a.relevance_category,
            'confidence': float(a.confidence_score) if a.confidence_score else 0.0,
            'reason': a.analysis_reason,
            'filter_stage': a.filter_stage.value if hasattr(a.filter_stage, 'value') else a.filter_stage,
            'processing_time_ms': a.processing_time_ms,
            'was_captured': a.was_captured,
            'created_at': a.created_at
        }
        for a in analyses
    ]


@router.get("/rules")
async def get_rules(db: Session = Depends(get_db)):
    """Get all monitoring rules"""
    rules = db.query(EmailMonitorRule).filter(
        EmailMonitorRule.is_active == True
    ).order_by(desc(EmailMonitorRule.priority)).all()

    return [
        {
            'id': r.id,
            'rule_name': r.rule_name,
            'description': r.description,
            'use_ai_filter': r.use_ai_filter,
            'min_confidence_score': float(r.min_confidence_score) if r.min_confidence_score else 0.7,
            'allow_spam_check': r.allow_spam_check,
            'require_crm_match': r.require_crm_match,
            'enabled_providers': r.enabled_providers,
            'priority': r.priority
        }
        for r in rules
    ]


@router.get("/providers")
async def get_providers(db: Session = Depends(get_db)):
    """Get provider configurations"""
    providers = db.query(EmailProviderConfig).all()

    return [
        {
            'id': p.id,
            'provider_name': p.provider_name.value if hasattr(p.provider_name, 'value') else p.provider_name,
            'is_enabled': p.is_enabled,
            'display_name': p.display_name,
            'last_poll_time': p.last_poll_time,
            'total_emails_processed': p.total_emails_processed,
            'total_emails_captured': p.total_emails_captured
        }
        for p in providers
    ]


async def _poll_provider_emails(provider_id: int, provider_name: str):
    """Background task to poll emails from a specific provider"""
    from database import SessionLocal
    from services.email_processor import EmailProcessor

    db = SessionLocal()
    try:
        logger.info(f"Starting email poll for provider {provider_name} (ID: {provider_id})")

        # Get provider config
        provider_config = db.query(EmailProviderConfig).filter(
            EmailProviderConfig.id == provider_id
        ).first()

        if not provider_config or not provider_config.is_enabled:
            logger.warning(f"Provider {provider_id} not found or disabled")
            return

        # Initialize email processor
        processor = EmailProcessor()

        # Based on provider type, fetch and process emails
        if provider_name == "microsoft_graph":
            from integrations.google_gmail import GmailService  # Import actual service
            # Would integrate with Microsoft Graph API
            logger.info(f"Would poll Microsoft Graph emails for provider {provider_id}")

        elif provider_name == "gmail":
            from integrations.google_gmail import GmailService
            # Would integrate with Gmail API
            logger.info(f"Would poll Gmail emails for provider {provider_id}")

        # Update last poll time
        provider_config.last_poll_time = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Email poll completed for provider {provider_name}")

    except Exception as e:
        db.rollback()
        logger.error(f"Email polling failed for provider {provider_id}: {e}")
    finally:
        db.close()


@router.post("/poll-now")
async def poll_emails_now(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    provider: Optional[str] = None
):
    """Manually trigger email polling"""
    # Get all enabled providers or specific one
    query = db.query(EmailProviderConfig).filter(EmailProviderConfig.is_enabled == True)

    if provider:
        query = query.filter(EmailProviderConfig.provider_name == provider)

    providers = query.all()

    if not providers:
        return {"success": False, "message": "No enabled providers found"}

    # Start background tasks for each provider
    for p in providers:
        provider_name = p.provider_name.value if hasattr(p.provider_name, 'value') else p.provider_name
        background_tasks.add_task(_poll_provider_emails, p.id, provider_name)

    return {
        "success": True,
        "message": f"Email polling started for {len(providers)} provider(s)",
        "providers": [p.display_name or p.provider_name for p in providers]
    }
