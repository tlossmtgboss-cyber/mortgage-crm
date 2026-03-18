"""
DRE shared state: lazy model loading and module-level dependencies.

Other dre sub-modules import from here to access _openai_client, _SECRET_KEY,
and the _ensure_models() helper.
"""
import logging
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level references set by init_dre_helpers()
_openai_client = None
_SECRET_KEY: str = ""

# Lazy model imports (resolved on first use to avoid circular imports)
_models_loaded = False

# These will be populated by _ensure_models()
Loan = None
Lead = None
MUMClient = None
ReferralPartner = None
ExtractedData = None
Task = None
MicrosoftOAuthToken = None
IncomingDataEvent = None
IntegrationCredential = None
LoanStage = None
LeadStage = None


def _ensure_models():
    """Lazy-import all needed models/enums to avoid circular imports at module load."""
    global _models_loaded
    if _models_loaded:
        return
    global Loan, Lead, MUMClient, ReferralPartner, ExtractedData, Task
    global MicrosoftOAuthToken, IncomingDataEvent, IntegrationCredential
    global LoanStage, LeadStage
    from database.models import (
        Loan, Lead, MUMClient, ReferralPartner, ExtractedData, Task,
        MicrosoftOAuthToken, IncomingDataEvent, IntegrationCredential,
    )
    from database.enums import LoanStage, LeadStage
    _models_loaded = True


def init_dre_helpers(openai_client=None, secret_key: str = ""):
    """Initialize module-level dependencies. Call once at startup."""
    global _openai_client, _SECRET_KEY
    _openai_client = openai_client
    _SECRET_KEY = secret_key


def get_openai_client():
    """Return the module-level OpenAI client (set by init_dre_helpers)."""
    return _openai_client


def get_secret_key() -> str:
    """Return the module-level SECRET_KEY (set by init_dre_helpers)."""
    return _SECRET_KEY


# ============================================================================
# API KEY HELPER
# ============================================================================

def generate_api_key() -> str:
    """Generate a secure API key with prefix 'sk_'"""
    random_part = secrets.token_urlsafe(32)
    return f"sk_{random_part}"


# ============================================================================
# AI HELPER FUNCTIONS
# ============================================================================

def generate_ai_insights(loan) -> str:
    """Generate AI insights for a loan (simple rule-based for now)"""
    from datetime import datetime, timezone

    insights = []

    if loan.days_in_stage and loan.days_in_stage > 10:
        stage_name = loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage) if loan.stage else 'unknown'
        insights.append(f"⚠️ Loan has been in {stage_name} stage for {loan.days_in_stage} days")

    if loan.closing_date:
        try:
            if hasattr(loan.closing_date, 'tzinfo'):
                closing_dt = loan.closing_date if loan.closing_date.tzinfo else loan.closing_date.replace(tzinfo=timezone.utc)
            else:
                closing_dt = datetime.combine(loan.closing_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            if (closing_dt - datetime.now(timezone.utc)).days < 7:
                insights.append("🔥 Closing date approaching - prioritize tasks")
        except Exception as e:
            logger.exception(f"Failed to calculate closing date insight: {e}")

    if loan.rate and loan.rate > 7.0:
        insights.append("💰 Higher rate loan - consider rate lock strategies")

    if not insights:
        insights.append("✅ Loan progressing normally")

    return " | ".join(insights)


def calculate_lead_score(lead) -> int:
    """Calculate AI score for a lead"""
    score = 50

    if lead.credit_score:
        if lead.credit_score >= 740:
            score += 30
        elif lead.credit_score >= 680:
            score += 20
        elif lead.credit_score >= 620:
            score += 10
        else:
            score -= 10

    if lead.preapproval_amount and lead.preapproval_amount > 0:
        score += 15

    if lead.email:
        score += 5

    if lead.phone:
        score += 5

    if lead.debt_to_income:
        if lead.debt_to_income < 0.36:
            score += 10
        elif lead.debt_to_income > 0.50:
            score -= 15

    return min(max(score, 0), 100)
