"""
Application Slides Settings Routes

Allows users to customize the mortgage application flow by:
- Enabling/disabling stages
- Enabling/disabling individual questions within stages
- Reordering stages and questions
- Separate configurations for Purchase and Refinance applications
"""

import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["Application Slides Settings"])

# =============================================================================
# Dependency Injection Setup
# =============================================================================

_User = None
_get_current_user = None
_get_db = None
_Base = None

def set_dependencies(user_model, current_user_func, db_func, base_model=None):
    """Set dependencies for the routes"""
    global _User, _get_current_user, _get_db, _Base
    _User = user_model
    _get_current_user = current_user_func
    _get_db = db_func
    _Base = base_model

def get_current_user():
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Dependencies not configured")
    return Depends(_get_current_user)

def get_db():
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Dependencies not configured")
    return Depends(_get_db)


# =============================================================================
# Pydantic Models
# =============================================================================

class StageConfig(BaseModel):
    """Configuration for an application stage"""
    id: str
    label: str
    icon: str
    description: str
    hideFromProgress: bool = False
    required: bool = False
    enabled: bool = True


class QuestionOptionConfig(BaseModel):
    """Configuration for a question answer option"""
    value: str
    label: str


class QuestionShowIfConfig(BaseModel):
    """Conditional logic for showing a question"""
    field: str
    values: List[str] = []


class QuestionConfig(BaseModel):
    """Configuration for a declaration question"""
    id: str
    question: str
    category: str
    required: bool = False
    enabled: bool = True
    type: str = "choice"
    stageId: Optional[str] = None
    helpText: Optional[str] = None
    options: Optional[List[QuestionOptionConfig]] = None
    showIf: Optional[QuestionShowIfConfig] = None


class FieldConfig(BaseModel):
    """Configuration for a profile field"""
    id: str
    label: str
    required: bool = False
    enabled: bool = True


class ApplicationSlidesConfig(BaseModel):
    """Full application slides configuration"""
    stages: List[StageConfig] = []
    declarationQuestions: List[QuestionConfig] = []
    profileFields: List[FieldConfig] = []


# =============================================================================
# Default Configurations
# =============================================================================

DEFAULT_STAGES = [
    {"id": "account", "label": "Get Started", "icon": "user", "description": "Create your account", "hideFromProgress": True, "required": True, "enabled": True},
    {"id": "declarations", "label": "Your Story", "icon": "story", "description": "Quick questions to personalize", "required": True, "enabled": True},
    {"id": "planning", "label": "Your Goals", "icon": "goals", "description": "Mortgage preferences", "required": False, "enabled": True},
    {"id": "profile", "label": "About You", "icon": "profile", "description": "The basics about you", "required": True, "enabled": True},
    {"id": "income", "label": "Your Income", "icon": "income", "description": "How you earn", "required": True, "enabled": True},
    {"id": "assets", "label": "Your Assets", "icon": "assets", "description": "Down payment funds", "required": True, "enabled": True},
    {"id": "property", "label": "New Home", "icon": "home", "description": "Property details", "required": True, "enabled": True},
    {"id": "review", "label": "Review", "icon": "review", "description": "Review your info", "required": True, "enabled": True},
    {"id": "schedule", "label": "Schedule", "icon": "calendar", "description": "Book a call", "required": False, "enabled": True},
]

DEFAULT_DECLARATION_QUESTIONS = [
    {"id": "borrower_count", "question": "How many people will be on this loan?", "category": "Basic Info", "required": True, "enabled": True},
    {"id": "co_borrower_relationship", "question": "Relationship to other borrower(s)?", "category": "Basic Info", "required": False, "enabled": True},
    {"id": "citizenship_status", "question": "Citizenship status?", "category": "Basic Info", "required": True, "enabled": True},
    {"id": "first_time_buyer", "question": "First home purchase?", "category": "Home History", "required": True, "enabled": True},
    {"id": "desired_state", "question": "State looking to buy in?", "category": "Location", "required": True, "enabled": True},
    {"id": "desired_city", "question": "City or area?", "category": "Location", "required": False, "enabled": True},
    {"id": "previous_home_status", "question": "Previous home status?", "category": "Home History", "required": False, "enabled": True},
    {"id": "previous_home_mortgage", "question": "Previous home mortgage?", "category": "Home History", "required": False, "enabled": True},
    {"id": "marital_status", "question": "Marital status?", "category": "Personal", "required": True, "enabled": True},
    {"id": "spouse_on_loan", "question": "Spouse on loan?", "category": "Personal", "required": False, "enabled": True},
    {"id": "divorce_finalized", "question": "Divorce finalized?", "category": "Personal", "required": False, "enabled": True},
    {"id": "child_support_alimony", "question": "Child support/alimony?", "category": "Financial", "required": False, "enabled": True},
    {"id": "military_status", "question": "Military service?", "category": "Military", "required": True, "enabled": True},
    {"id": "va_funding_fee", "question": "VA funding fee exempt?", "category": "Military", "required": False, "enabled": True},
    {"id": "self_employed", "question": "Self-employed?", "category": "Employment", "required": True, "enabled": True},
    {"id": "employer_name", "question": "Employer name?", "category": "Employment", "required": True, "enabled": True},
    {"id": "credit_score_range", "question": "Credit score range?", "category": "Credit", "required": True, "enabled": True},
    {"id": "bankruptcy_history", "question": "Bankruptcy history?", "category": "Credit", "required": True, "enabled": True},
    {"id": "gift_funds", "question": "Gift funds for down payment?", "category": "Assets", "required": False, "enabled": True},
    {"id": "retirement_funds", "question": "Using retirement funds?", "category": "Assets", "required": False, "enabled": True},
]

DEFAULT_PROFILE_FIELDS = [
    {"id": "firstName", "label": "First Name", "required": True, "enabled": True},
    {"id": "lastName", "label": "Last Name", "required": True, "enabled": True},
    {"id": "email", "label": "Email", "required": True, "enabled": True},
    {"id": "phone", "label": "Phone", "required": True, "enabled": True},
    {"id": "dateOfBirth", "label": "Date of Birth", "required": True, "enabled": True},
    {"id": "ssn", "label": "Social Security Number", "required": True, "enabled": True},
    {"id": "currentAddress", "label": "Current Address", "required": True, "enabled": True},
    {"id": "yearsAtAddress", "label": "Years at Address", "required": False, "enabled": True},
    {"id": "housingStatus", "label": "Housing Status (Rent/Own)", "required": True, "enabled": True},
    {"id": "monthlyPayment", "label": "Monthly Housing Payment", "required": True, "enabled": True},
]


# =============================================================================
# Refinance-specific Default Configurations
# =============================================================================

DEFAULT_REFINANCE_STAGES = [
    {"id": "account", "label": "Get Started", "icon": "user", "description": "Create your account", "hideFromProgress": True, "required": True, "enabled": True},
    {"id": "declarations", "label": "Your Story", "icon": "story", "description": "Quick questions to personalize", "required": True, "enabled": True},
    {"id": "goals", "label": "Refinance Goals", "icon": "goals", "description": "Why you're refinancing", "required": True, "enabled": True},
    {"id": "profile", "label": "About You", "icon": "profile", "description": "The basics about you", "required": True, "enabled": True},
    {"id": "income", "label": "Your Income", "icon": "income", "description": "How you earn", "required": True, "enabled": True},
    {"id": "assets", "label": "Your Assets", "icon": "assets", "description": "Your financial resources", "required": True, "enabled": True},
    {"id": "property", "label": "Current Home", "icon": "home", "description": "Your current property", "required": True, "enabled": True},
    {"id": "review", "label": "Review", "icon": "review", "description": "Review your info", "required": True, "enabled": True},
    {"id": "schedule", "label": "Schedule", "icon": "calendar", "description": "Book a call", "required": False, "enabled": True},
]

DEFAULT_REFINANCE_QUESTIONS = [
    {"id": "borrower_count", "question": "How many people will be on this loan?", "category": "Basic Info", "required": True, "enabled": True},
    {"id": "co_borrower_relationship", "question": "Relationship to other borrower(s)?", "category": "Basic Info", "required": False, "enabled": True},
    {"id": "citizenship_status", "question": "Citizenship status?", "category": "Basic Info", "required": True, "enabled": True},
    {"id": "refinance_reason", "question": "Main reason for refinancing?", "category": "Refinance Goals", "required": True, "enabled": True},
    {"id": "current_mortgage_payment", "question": "Current monthly mortgage payment?", "category": "Current Loan", "required": True, "enabled": True},
    {"id": "current_loan_balance", "question": "Approximate remaining loan balance?", "category": "Current Loan", "required": True, "enabled": True},
    {"id": "current_interest_rate", "question": "Current interest rate?", "category": "Current Loan", "required": False, "enabled": True},
    {"id": "home_value_estimate", "question": "Estimated current home value?", "category": "Property", "required": True, "enabled": True},
    {"id": "marital_status", "question": "Marital status?", "category": "Personal", "required": True, "enabled": True},
    {"id": "military_status", "question": "Military service?", "category": "Military", "required": True, "enabled": True},
    {"id": "va_funding_fee", "question": "VA funding fee exempt?", "category": "Military", "required": False, "enabled": True},
    {"id": "self_employed", "question": "Self-employed?", "category": "Employment", "required": True, "enabled": True},
    {"id": "credit_score_range", "question": "Credit score range?", "category": "Credit", "required": True, "enabled": True},
    {"id": "bankruptcy_history", "question": "Bankruptcy history?", "category": "Credit", "required": True, "enabled": True},
    {"id": "cash_out_needed", "question": "Do you need cash out?", "category": "Refinance Goals", "required": False, "enabled": True},
]


# =============================================================================
# Routes
# =============================================================================

def get_defaults_for_app_type(app_type: str):
    """Get default configuration based on application type."""
    if app_type == "refinance":
        return {
            "stages": DEFAULT_REFINANCE_STAGES,
            "declarationQuestions": DEFAULT_REFINANCE_QUESTIONS,
            "profileFields": DEFAULT_PROFILE_FIELDS
        }
    # Default to purchase
    return {
        "stages": DEFAULT_STAGES,
        "declarationQuestions": DEFAULT_DECLARATION_QUESTIONS,
        "profileFields": DEFAULT_PROFILE_FIELDS
    }


@router.get("/application-slides")
async def get_application_slides_config(
    app_type: str = Query("purchase", description="Application type: 'purchase' or 'refinance'"),
    current_user = Depends(_get_current_user),
    db: Session = Depends(_get_db)
):
    """
    Get the current application slides configuration for the user's organization.
    Returns default configuration if none exists.
    Supports separate configurations for 'purchase' and 'refinance' application types.
    """
    try:
        # Try to get existing configuration from database
        from sqlalchemy import text

        user_id = current_user.id if hasattr(current_user, 'id') else 1
        org_id = current_user.company_id if hasattr(current_user, 'company_id') else 1

        # Validate app_type
        if app_type not in ["purchase", "refinance"]:
            app_type = "purchase"

        # Try to find existing config for this app type
        result = db.execute(
            text("""
                SELECT config_data FROM application_slides_config
                WHERE organization_id = :org_id AND app_type = :app_type
                ORDER BY updated_at DESC LIMIT 1
            """),
            {"org_id": org_id, "app_type": app_type}
        ).fetchone()

        defaults = get_defaults_for_app_type(app_type)

        if result and result[0]:
            import json
            config = json.loads(result[0]) if isinstance(result[0], str) else result[0]
            return {
                "stages": config.get("stages", defaults["stages"]),
                "declarationQuestions": config.get("declarationQuestions", defaults["declarationQuestions"]),
                "profileFields": config.get("profileFields", defaults["profileFields"])
            }

        # Return defaults if no config found
        return defaults

    except Exception as e:
        logger.warning(f"Error fetching application slides config: {e}")
        # Return defaults on error (table might not exist yet)
        return get_defaults_for_app_type(app_type)


@router.post("/application-slides")
async def save_application_slides_config(
    config: ApplicationSlidesConfig,
    app_type: str = Query("purchase", description="Application type: 'purchase' or 'refinance'"),
    current_user = Depends(_get_current_user),
    db: Session = Depends(_get_db)
):
    """
    Save application slides configuration for the user's organization.
    Supports separate configurations for 'purchase' and 'refinance' application types.
    """
    try:
        import json
        from sqlalchemy import text

        user_id = current_user.id if hasattr(current_user, 'id') else 1
        org_id = current_user.company_id if hasattr(current_user, 'company_id') else 1

        # Validate app_type
        if app_type not in ["purchase", "refinance"]:
            app_type = "purchase"

        # Use model_dump() for Pydantic v2 compatibility
        try:
            config_data = json.dumps({
                "stages": [s.model_dump() for s in config.stages],
                "declarationQuestions": [q.model_dump() for q in config.declarationQuestions],
                "profileFields": [f.model_dump() for f in config.profileFields]
            })
        except AttributeError:
            # Fall back to dict() for Pydantic v1
            config_data = json.dumps({
                "stages": [s.dict() for s in config.stages],
                "declarationQuestions": [q.dict() for q in config.declarationQuestions],
                "profileFields": [f.dict() for f in config.profileFields]
            })

        # Ensure table exists with app_type column
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS application_slides_config (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                app_type VARCHAR(20) DEFAULT 'purchase',
                config_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Try to add app_type column if it doesn't exist (for existing tables)
        try:
            db.execute(text("""
                ALTER TABLE application_slides_config
                ADD COLUMN IF NOT EXISTS app_type VARCHAR(20) DEFAULT 'purchase'
            """))
        except Exception as e:
            logger.error(f"Error adding app_type column: {e}")
            pass  # Column might already exist

        # Check if config exists for this org and app type
        existing = db.execute(
            text("SELECT id FROM application_slides_config WHERE organization_id = :org_id AND app_type = :app_type"),
            {"org_id": org_id, "app_type": app_type}
        ).fetchone()

        if existing:
            # Update existing
            db.execute(
                text("""
                    UPDATE application_slides_config
                    SET config_data = :config_data,
                        user_id = :user_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE organization_id = :org_id AND app_type = :app_type
                """),
                {"config_data": config_data, "user_id": user_id, "org_id": org_id, "app_type": app_type}
            )
        else:
            # Insert new
            db.execute(
                text("""
                    INSERT INTO application_slides_config (organization_id, user_id, app_type, config_data)
                    VALUES (:org_id, :user_id, :app_type, :config_data)
                """),
                {"org_id": org_id, "user_id": user_id, "app_type": app_type, "config_data": config_data}
            )

        db.commit()

        return {
            "success": True,
            "message": f"Configuration saved successfully for {app_type} application",
            "app_type": app_type,
            "timestamp": datetime.utcnow().isoformat()
        }

    except SQLAlchemyError as e:
        import traceback
        logger.error(f"Error saving application slides config: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save configuration")


@router.post("/application-slides/reset")
async def reset_application_slides_config(
    app_type: str = Query("purchase", description="Application type: 'purchase' or 'refinance'"),
    current_user = Depends(_get_current_user),
    db: Session = Depends(_get_db)
):
    """
    Reset application slides configuration to defaults.
    Supports separate configurations for 'purchase' and 'refinance' application types.
    """
    try:
        from sqlalchemy import text

        org_id = current_user.company_id if hasattr(current_user, 'company_id') else 1

        # Validate app_type
        if app_type not in ["purchase", "refinance"]:
            app_type = "purchase"

        # Delete existing config for this app type
        db.execute(
            text("DELETE FROM application_slides_config WHERE organization_id = :org_id AND app_type = :app_type"),
            {"org_id": org_id, "app_type": app_type}
        )
        db.commit()

        defaults = get_defaults_for_app_type(app_type)

        return {
            "success": True,
            "message": f"Configuration reset to defaults for {app_type} application",
            "app_type": app_type,
            "stages": defaults["stages"],
            "declarationQuestions": defaults["declarationQuestions"],
            "profileFields": defaults["profileFields"]
        }

    except SQLAlchemyError as e:
        logger.error(f"Error resetting application slides config: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to reset configuration")
