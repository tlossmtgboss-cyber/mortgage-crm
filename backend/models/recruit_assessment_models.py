"""
Recruiting Assessment Models

Models for:
- Quiz templates
- Quiz responses
- Assessment scores
- Calculator configuration
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


# =============================================================================
# Quiz Template Models
# =============================================================================

class QuizTemplateBase(BaseModel):
    """Base model for quiz template."""
    disposition: str
    question_text: str
    question_type: str = "likert"  # likert, yes_no, text, numeric
    category: str  # production, disc, character, skills, culture_fit
    weight: float = 1.0
    display_order: int = 0
    is_active: bool = True


class QuizTemplate(QuizTemplateBase):
    """Quiz template with ID."""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QuizTemplateCreate(QuizTemplateBase):
    """Model for creating a quiz template."""
    pass


# =============================================================================
# Quiz Response Models
# =============================================================================

class QuizResponseBase(BaseModel):
    """Base model for quiz response."""
    template_id: int
    response_value: str
    numeric_score: Optional[float] = None


class QuizResponse(QuizResponseBase):
    """Quiz response with metadata."""
    id: int
    candidate_id: int
    disposition: str
    responded_by: Optional[int] = None
    responded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QuizResponseCreate(BaseModel):
    """Model for creating a quiz response."""
    template_id: int
    response_value: str
    numeric_score: float


class QuizSubmission(BaseModel):
    """Model for submitting quiz responses."""
    disposition: str
    responses: List[QuizResponseCreate]


# =============================================================================
# Assessment Score Models
# =============================================================================

class AssessmentScores(BaseModel):
    """Assessment scores for a candidate."""
    id: Optional[int] = None
    candidate_id: int
    production_score: Optional[float] = None
    disc_score: Optional[float] = None
    character_score: Optional[float] = None
    skills_score: Optional[float] = None
    culture_fit_score: Optional[float] = None
    overall_score: Optional[float] = None
    last_quiz_disposition: Optional[str] = None
    quiz_count: int = 0
    last_updated: Optional[datetime] = None

    class Config:
        from_attributes = True


class AssessmentScoreBreakdown(BaseModel):
    """Detailed breakdown of assessment scores."""
    candidate_id: int
    candidate_name: Optional[str] = None
    scores: AssessmentScores
    category_details: dict = {}
    quiz_history: List[dict] = []
    recommendations: List[str] = []


# =============================================================================
# Calculator Configuration Models
# =============================================================================

class CalculatorConfig(BaseModel):
    """Production calculator configuration."""
    id: Optional[int] = None
    organization_id: Optional[int] = None
    lead_conversion_lift: float = 1.25
    avg_deal_size_lift: float = 1.15
    closing_speed_factor: float = 0.85
    tech_efficiency_gain: float = 1.20
    marketing_lead_boost: float = 1.30
    comp_percentage: float = 0.0125

    class Config:
        from_attributes = True


class CalculatorInput(BaseModel):
    """Input for production calculator."""
    current_volume: float = Field(..., description="Current annual loan volume ($)")
    current_units: int = Field(..., description="Current annual units closed")
    avg_loan_amount: Optional[float] = Field(None, description="Average loan amount (auto-calculated if not provided)")


class CalculatorResult(BaseModel):
    """Result from production calculator."""
    current_volume: float
    current_units: int
    projected_volume: float
    projected_units: int
    volume_increase: float
    volume_increase_pct: float
    unit_increase: int
    unit_increase_pct: float
    potential_earnings: float
    current_earnings: float
    earnings_increase: float
    earnings_increase_pct: float


# =============================================================================
# Quiz Display Models
# =============================================================================

class QuizQuestion(BaseModel):
    """Question displayed to user."""
    id: int
    question_text: str
    question_type: str
    category: str
    weight: float
    display_order: int
    options: Optional[List[dict]] = None  # For likert scale options


class QuizForDisposition(BaseModel):
    """Complete quiz for a disposition stage."""
    disposition: str
    disposition_label: str
    questions: List[QuizQuestion]
    total_questions: int
    categories: List[str]


# =============================================================================
# Score Calculation Constants
# =============================================================================

# Weights for overall score calculation (from candidate_grading_service.py)
WEIGHT_PRODUCTION = 0.45
WEIGHT_DISC = 0.20
WEIGHT_CHARACTER = 0.15
WEIGHT_SKILLS = 0.10
WEIGHT_CULTURE_FIT = 0.10

# Likert scale options
LIKERT_OPTIONS = [
    {"value": "1", "label": "Poor", "score": 2.0},
    {"value": "2", "label": "Below Average", "score": 4.0},
    {"value": "3", "label": "Average", "score": 6.0},
    {"value": "4", "label": "Above Average", "score": 8.0},
    {"value": "5", "label": "Excellent", "score": 10.0},
]

YES_NO_OPTIONS = [
    {"value": "yes", "label": "Yes", "score": 10.0},
    {"value": "no", "label": "No", "score": 0.0},
]

# Disposition labels
DISPOSITION_LABELS = {
    "new": "New Candidate",
    "screening": "Screening",
    "phone_screen": "Phone Screen",
    "interview": "Interview",
    "assessment": "Assessment",
    "offer": "Offer",
    "hired": "Hired",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}
