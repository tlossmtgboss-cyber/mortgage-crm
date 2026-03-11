"""
Surveying & Feedback Routes
API endpoints for customer satisfaction surveys and feedback collection.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_
from typing import Optional, List
from datetime import datetime, timedelta
import secrets
import uuid
import logging

from database import get_db

# Handle import of get_current_user (avoid circular import issues)
try:
    from auth.dependencies import get_current_user
except ImportError:
    from fastapi import HTTPException as _HTTPException
    async def get_current_user():
        raise _HTTPException(status_code=503, detail="Authentication service not initialized")

logger = logging.getLogger(__name__)

from models.surveying_models import (
    SurveyTemplate, SurveyQuestion, SurveyResponse, SurveyAnswer,
    SurveyAnalytics, SavingsValidation,
    SurveyType, SurveyStatus, QuestionType, ResponseStatus, TriggerType, SentimentLevel,
    SurveyTemplateCreate, SurveyTemplateUpdate, QuestionCreate,
    SendSurveyRequest, SurveyResponseSubmit, SubmitAnswerRequest, AnalyticsFilter
)

router = APIRouter(prefix="/api/surveys", tags=["Surveys"])


# =============================================================================
# Helper Functions
# =============================================================================

def get_org_filter(current_user, model_class):
    """Get organization filter for multi-tenant queries."""
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    if is_platform_admin:
        return True  # No filter for platform admins
    elif org_id:
        return model_class.organization_id == org_id
    else:
        return model_class.organization_id == -1  # No access


def generate_access_token():
    """Generate a secure access token for survey links."""
    return secrets.token_urlsafe(32)


def calculate_nps_category(score: int) -> str:
    """Categorize NPS score."""
    if score >= 9:
        return "promoter"
    elif score >= 7:
        return "passive"
    else:
        return "detractor"


def calculate_sentiment(score: float) -> SentimentLevel:
    """Calculate sentiment level from numeric score."""
    if score >= 0.6:
        return SentimentLevel.VERY_POSITIVE
    elif score >= 0.2:
        return SentimentLevel.POSITIVE
    elif score >= -0.2:
        return SentimentLevel.NEUTRAL
    elif score >= -0.6:
        return SentimentLevel.NEGATIVE
    else:
        return SentimentLevel.VERY_NEGATIVE


# =============================================================================
# Survey Template Endpoints
# =============================================================================

@router.get("/templates")
async def list_survey_templates(
    status: Optional[SurveyStatus] = None,
    survey_type: Optional[SurveyType] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List survey templates for the organization."""
    org_filter = get_org_filter(current_user, SurveyTemplate)

    query = db.query(SurveyTemplate).filter(org_filter)

    if status:
        query = query.filter(SurveyTemplate.status == status)
    if survey_type:
        query = query.filter(SurveyTemplate.survey_type == survey_type)

    total = query.count()
    templates = query.order_by(SurveyTemplate.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "survey_type": t.survey_type.value if t.survey_type else None,
                "status": t.status.value if t.status else None,
                "trigger_type": t.trigger_type.value if t.trigger_type else None,
                "question_count": len(t.questions) if t.questions else 0,
                "response_count": len(t.responses) if t.responses else 0,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in templates
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/templates/{template_id}")
async def get_survey_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get a survey template with questions."""
    org_filter = get_org_filter(current_user, SurveyTemplate)

    template = db.query(SurveyTemplate).options(
        joinedload(SurveyTemplate.questions)
    ).filter(
        and_(SurveyTemplate.id == template_id, org_filter)
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Survey template not found")

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "survey_type": template.survey_type.value if template.survey_type else None,
        "status": template.status.value if template.status else None,
        "trigger_type": template.trigger_type.value if template.trigger_type else None,
        "trigger_config": template.trigger_config,
        "is_anonymous": template.is_anonymous,
        "expires_days": template.expires_days,
        "reminder_enabled": template.reminder_enabled,
        "reminder_days": template.reminder_days,
        "max_reminders": template.max_reminders,
        "intro_message": template.intro_message,
        "thank_you_message": template.thank_you_message,
        "logo_url": template.logo_url,
        "primary_color": template.primary_color,
        "questions": [
            {
                "id": q.id,
                "question_text": q.question_text,
                "question_type": q.question_type.value if q.question_type else None,
                "help_text": q.help_text,
                "options": q.options,
                "is_required": q.is_required,
                "min_value": q.min_value,
                "max_value": q.max_value,
                "order": q.order,
                "weight": q.weight,
                "conditional_logic": q.conditional_logic,
            }
            for q in sorted(template.questions, key=lambda x: x.order)
        ],
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


@router.post("/templates")
async def create_survey_template(
    data: SurveyTemplateCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new survey template."""
    org_id = getattr(current_user, 'organization_id', 1)
    user_id = getattr(current_user, 'id', None)

    template = SurveyTemplate(
        organization_id=org_id,
        name=data.name,
        description=data.description,
        survey_type=data.survey_type,
        status=SurveyStatus.DRAFT,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config or {},
        is_anonymous=data.is_anonymous,
        expires_days=data.expires_days,
        reminder_enabled=data.reminder_enabled,
        reminder_days=data.reminder_days,
        max_reminders=data.max_reminders,
        intro_message=data.intro_message,
        thank_you_message=data.thank_you_message,
        created_by=user_id,
    )

    db.add(template)
    db.flush()  # Get template ID

    # Add questions
    for idx, q_data in enumerate(data.questions):
        question = SurveyQuestion(
            template_id=template.id,
            question_text=q_data.question_text,
            question_type=q_data.question_type,
            help_text=q_data.help_text,
            options=q_data.options or [],
            is_required=q_data.is_required,
            min_value=q_data.min_value,
            max_value=q_data.max_value,
            order=q_data.order if q_data.order else idx,
            weight=q_data.weight,
            conditional_logic=q_data.conditional_logic,
        )
        db.add(question)

    db.commit()
    db.refresh(template)

    return {
        "id": template.id,
        "name": template.name,
        "status": template.status.value,
        "question_count": len(data.questions),
        "message": "Survey template created successfully",
    }


@router.put("/templates/{template_id}")
async def update_survey_template(
    template_id: int,
    data: SurveyTemplateUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a survey template."""
    org_filter = get_org_filter(current_user, SurveyTemplate)

    template = db.query(SurveyTemplate).filter(
        and_(SurveyTemplate.id == template_id, org_filter)
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Survey template not found")

    # Update fields if provided
    update_fields = data.dict(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for field, value in update_fields.items():
        if value is not None and field not in _protected:
            setattr(template, field, value)

    db.commit()
    db.refresh(template)

    return {
        "id": template.id,
        "name": template.name,
        "status": template.status.value if template.status else None,
        "message": "Survey template updated successfully",
    }


@router.delete("/templates/{template_id}")
async def delete_survey_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a survey template (archive it)."""
    org_filter = get_org_filter(current_user, SurveyTemplate)

    template = db.query(SurveyTemplate).filter(
        and_(SurveyTemplate.id == template_id, org_filter)
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Survey template not found")

    # Check for responses
    if template.responses:
        # Archive instead of delete
        template.status = SurveyStatus.ARCHIVED
        db.commit()
        return {"message": "Survey template archived (has responses)"}

    db.delete(template)
    db.commit()

    return {"message": "Survey template deleted successfully"}


# =============================================================================
# Question Management
# =============================================================================

@router.post("/templates/{template_id}/questions")
async def add_question(
    template_id: int,
    data: QuestionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add a question to a survey template."""
    org_filter = get_org_filter(current_user, SurveyTemplate)

    template = db.query(SurveyTemplate).filter(
        and_(SurveyTemplate.id == template_id, org_filter)
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Survey template not found")

    # Get max order
    max_order = db.query(func.max(SurveyQuestion.order)).filter(
        SurveyQuestion.template_id == template_id
    ).scalar() or 0

    question = SurveyQuestion(
        template_id=template_id,
        question_text=data.question_text,
        question_type=data.question_type,
        help_text=data.help_text,
        options=data.options or [],
        is_required=data.is_required,
        min_value=data.min_value,
        max_value=data.max_value,
        order=data.order if data.order else max_order + 1,
        weight=data.weight,
        conditional_logic=data.conditional_logic,
    )

    db.add(question)
    db.commit()
    db.refresh(question)

    return {
        "id": question.id,
        "question_text": question.question_text,
        "question_type": question.question_type.value,
        "order": question.order,
        "message": "Question added successfully",
    }


@router.put("/templates/{template_id}/questions/{question_id}")
async def update_question(
    template_id: int,
    question_id: int,
    data: QuestionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update a survey question."""
    org_filter = get_org_filter(current_user, SurveyTemplate)

    template = db.query(SurveyTemplate).filter(
        and_(SurveyTemplate.id == template_id, org_filter)
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Survey template not found")

    question = db.query(SurveyQuestion).filter(
        and_(SurveyQuestion.id == question_id, SurveyQuestion.template_id == template_id)
    ).first()

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    question.question_text = data.question_text
    question.question_type = data.question_type
    question.help_text = data.help_text
    question.options = data.options or []
    question.is_required = data.is_required
    question.min_value = data.min_value
    question.max_value = data.max_value
    question.order = data.order
    question.weight = data.weight
    question.conditional_logic = data.conditional_logic

    db.commit()

    return {"message": "Question updated successfully"}


@router.delete("/templates/{template_id}/questions/{question_id}")
async def delete_question(
    template_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a survey question."""
    org_filter = get_org_filter(current_user, SurveyTemplate)

    template = db.query(SurveyTemplate).filter(
        and_(SurveyTemplate.id == template_id, org_filter)
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Survey template not found")

    question = db.query(SurveyQuestion).filter(
        and_(SurveyQuestion.id == question_id, SurveyQuestion.template_id == template_id)
    ).first()

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Check for answers
    if question.answers:
        raise HTTPException(status_code=400, detail="Cannot delete question with existing answers")

    db.delete(question)
    db.commit()

    return {"message": "Question deleted successfully"}


# =============================================================================
# Survey Distribution
# =============================================================================

@router.post("/send")
async def send_survey(
    data: SendSurveyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Send a survey to a recipient."""
    org_id = getattr(current_user, 'organization_id', 1)
    org_filter = get_org_filter(current_user, SurveyTemplate)

    # Verify template exists and is active
    template = db.query(SurveyTemplate).filter(
        and_(SurveyTemplate.id == data.template_id, org_filter)
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Survey template not found")

    if template.status != SurveyStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Survey template is not active")

    # Create survey response record
    access_token = generate_access_token()
    expires_at = datetime.utcnow() + timedelta(days=template.expires_days)

    response = SurveyResponse(
        organization_id=org_id,
        template_id=template.id,
        borrower_id=data.borrower_id,
        loan_id=data.loan_id,
        email=data.email,
        access_token=access_token,
        status=ResponseStatus.PENDING,
        sent_at=datetime.utcnow(),
        expires_at=expires_at,
        trigger_event=data.trigger_event,
        loan_officer_id=data.loan_officer_id,
    )

    db.add(response)
    db.commit()
    db.refresh(response)

    # Queue email sending (background task)
    survey_url = f"/survey/{access_token}"
    background_tasks.add_task(
        send_survey_email,
        email=data.email,
        template_name=template.name,
        survey_url=survey_url,
        intro_message=template.intro_message,
    )

    return {
        "response_id": response.id,
        "access_token": access_token,
        "survey_url": survey_url,
        "expires_at": expires_at.isoformat(),
        "message": "Survey sent successfully",
    }


@router.post("/send-bulk")
async def send_bulk_surveys(
    template_id: int,
    recipients: List[SendSurveyRequest],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Send surveys to multiple recipients."""
    org_id = getattr(current_user, 'organization_id', 1)
    org_filter = get_org_filter(current_user, SurveyTemplate)

    template = db.query(SurveyTemplate).filter(
        and_(SurveyTemplate.id == template_id, org_filter)
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Survey template not found")

    if template.status != SurveyStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Survey template is not active")

    sent_count = 0
    errors = []

    for recipient in recipients:
        try:
            access_token = generate_access_token()
            expires_at = datetime.utcnow() + timedelta(days=template.expires_days)

            response = SurveyResponse(
                organization_id=org_id,
                template_id=template.id,
                borrower_id=recipient.borrower_id,
                loan_id=recipient.loan_id,
                email=recipient.email,
                access_token=access_token,
                status=ResponseStatus.PENDING,
                sent_at=datetime.utcnow(),
                expires_at=expires_at,
                trigger_event=recipient.trigger_event,
                loan_officer_id=recipient.loan_officer_id,
            )
            db.add(response)
            sent_count += 1

            # Queue email
            background_tasks.add_task(
                send_survey_email,
                email=recipient.email,
                template_name=template.name,
                survey_url=f"/survey/{access_token}",
                intro_message=template.intro_message,
            )
        except Exception as e:
            errors.append({"email": recipient.email, "error": "Internal server error"})

    db.commit()

    return {
        "sent_count": sent_count,
        "error_count": len(errors),
        "errors": errors,
        "message": f"Sent {sent_count} surveys",
    }


# =============================================================================
# Survey Response Collection (Public Endpoints)
# =============================================================================

@router.get("/respond/{access_token}")
async def get_survey_for_response(
    access_token: str,
    db: Session = Depends(get_db)
):
    """Get survey for respondent (public endpoint)."""
    response = db.query(SurveyResponse).options(
        joinedload(SurveyResponse.template).joinedload(SurveyTemplate.questions)
    ).filter(
        SurveyResponse.access_token == access_token
    ).first()

    if not response:
        raise HTTPException(status_code=404, detail="Survey not found")

    if response.status == ResponseStatus.COMPLETED:
        return {
            "status": "completed",
            "message": "This survey has already been completed. Thank you for your feedback!",
            "thank_you_message": response.template.thank_you_message,
        }

    if response.expires_at and response.expires_at < datetime.utcnow():
        response.status = ResponseStatus.EXPIRED
        db.commit()
        return {
            "status": "expired",
            "message": "This survey has expired.",
        }

    # Mark as in progress if first access
    if response.status == ResponseStatus.PENDING:
        response.status = ResponseStatus.IN_PROGRESS
        response.started_at = datetime.utcnow()
        db.commit()

    template = response.template

    return {
        "status": "active",
        "survey_name": template.name,
        "intro_message": template.intro_message,
        "logo_url": template.logo_url,
        "primary_color": template.primary_color,
        "is_anonymous": template.is_anonymous,
        "questions": [
            {
                "id": q.id,
                "question_text": q.question_text,
                "question_type": q.question_type.value,
                "help_text": q.help_text,
                "options": q.options,
                "is_required": q.is_required,
                "min_value": q.min_value,
                "max_value": q.max_value,
                "order": q.order,
                "conditional_logic": q.conditional_logic,
            }
            for q in sorted(template.questions, key=lambda x: x.order)
        ],
    }


@router.post("/respond/{access_token}")
async def submit_survey_response(
    access_token: str,
    data: SurveyResponseSubmit,
    request: Request,
    db: Session = Depends(get_db)
):
    """Submit survey response (public endpoint)."""
    response = db.query(SurveyResponse).options(
        joinedload(SurveyResponse.template).joinedload(SurveyTemplate.questions)
    ).filter(
        SurveyResponse.access_token == access_token
    ).first()

    if not response:
        raise HTTPException(status_code=404, detail="Survey not found")

    if response.status == ResponseStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Survey already completed")

    if response.expires_at and response.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Survey has expired")

    # Validate required questions
    template = response.template
    required_ids = {q.id for q in template.questions if q.is_required}
    answered_ids = {a.question_id for a in data.answers}

    missing = required_ids - answered_ids
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required questions: {list(missing)}"
        )

    # Save answers
    nps_score = None
    total_score = 0
    score_count = 0

    for answer_data in data.answers:
        question = next((q for q in template.questions if q.id == answer_data.question_id), None)
        if not question:
            continue

        answer = SurveyAnswer(
            response_id=response.id,
            question_id=answer_data.question_id,
            answer_text=answer_data.answer_text,
            answer_numeric=answer_data.answer_numeric,
            answer_json=answer_data.answer_json,
        )

        # Track NPS score
        if question.question_type == QuestionType.NPS_SCALE and answer_data.answer_numeric is not None:
            nps_score = int(answer_data.answer_numeric)

        # Track for CSAT calculation
        if answer_data.answer_numeric is not None:
            total_score += answer_data.answer_numeric * question.weight
            score_count += question.weight

        # Analyze sentiment for text responses
        if answer_data.answer_text and len(answer_data.answer_text) > 10:
            sentiment_score = analyze_sentiment(answer_data.answer_text)
            answer.sentiment_score = sentiment_score
            answer.sentiment = calculate_sentiment(sentiment_score)
            answer.key_phrases = extract_key_phrases(answer_data.answer_text)

        db.add(answer)

    # Update response record
    response.status = ResponseStatus.COMPLETED
    response.completed_at = datetime.utcnow()
    response.nps_score = nps_score

    if score_count > 0:
        response.csat_score = total_score / score_count
        response.overall_score = response.csat_score

    # Calculate overall sentiment
    if nps_score is not None:
        if nps_score >= 9:
            response.sentiment = SentimentLevel.VERY_POSITIVE
        elif nps_score >= 7:
            response.sentiment = SentimentLevel.POSITIVE
        elif nps_score >= 5:
            response.sentiment = SentimentLevel.NEUTRAL
        elif nps_score >= 3:
            response.sentiment = SentimentLevel.NEGATIVE
        else:
            response.sentiment = SentimentLevel.VERY_NEGATIVE

    # Track completion time
    if response.started_at:
        response.completion_time_seconds = int(
            (datetime.utcnow() - response.started_at).total_seconds()
        )

    # Track IP and user agent
    response.ip_address = request.client.host if request.client else None
    response.user_agent = request.headers.get("user-agent", "")[:500]

    db.commit()

    return {
        "status": "success",
        "message": "Thank you for your feedback!",
        "thank_you_message": template.thank_you_message,
    }


# =============================================================================
# Survey Response Management
# =============================================================================

@router.get("/responses")
async def list_survey_responses(
    template_id: Optional[int] = None,
    status: Optional[ResponseStatus] = None,
    loan_officer_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List survey responses."""
    org_filter = get_org_filter(current_user, SurveyResponse)

    query = db.query(SurveyResponse).options(
        joinedload(SurveyResponse.template)
    ).filter(org_filter)

    if template_id:
        query = query.filter(SurveyResponse.template_id == template_id)
    if status:
        query = query.filter(SurveyResponse.status == status)
    if loan_officer_id:
        query = query.filter(SurveyResponse.loan_officer_id == loan_officer_id)
    if start_date:
        query = query.filter(SurveyResponse.sent_at >= start_date)
    if end_date:
        query = query.filter(SurveyResponse.sent_at <= end_date)

    total = query.count()
    responses = query.order_by(SurveyResponse.sent_at.desc()).offset(offset).limit(limit).all()

    return {
        "responses": [
            {
                "id": r.id,
                "template_name": r.template.name if r.template else None,
                "email": r.email,
                "status": r.status.value if r.status else None,
                "nps_score": r.nps_score,
                "csat_score": r.csat_score,
                "sentiment": r.sentiment.value if r.sentiment else None,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "loan_id": r.loan_id,
            }
            for r in responses
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/responses/{response_id}")
async def get_survey_response(
    response_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get detailed survey response with answers."""
    org_filter = get_org_filter(current_user, SurveyResponse)

    response = db.query(SurveyResponse).options(
        joinedload(SurveyResponse.template),
        joinedload(SurveyResponse.answers).joinedload(SurveyAnswer.question)
    ).filter(
        and_(SurveyResponse.id == response_id, org_filter)
    ).first()

    if not response:
        raise HTTPException(status_code=404, detail="Survey response not found")

    return {
        "id": response.id,
        "template": {
            "id": response.template.id,
            "name": response.template.name,
            "survey_type": response.template.survey_type.value if response.template.survey_type else None,
        },
        "email": response.email,
        "loan_id": response.loan_id,
        "status": response.status.value if response.status else None,
        "scores": {
            "nps": response.nps_score,
            "csat": response.csat_score,
            "overall": response.overall_score,
        },
        "sentiment": response.sentiment.value if response.sentiment else None,
        "timing": {
            "sent_at": response.sent_at.isoformat() if response.sent_at else None,
            "started_at": response.started_at.isoformat() if response.started_at else None,
            "completed_at": response.completed_at.isoformat() if response.completed_at else None,
            "completion_time_seconds": response.completion_time_seconds,
        },
        "answers": [
            {
                "question_id": a.question_id,
                "question_text": a.question.question_text if a.question else None,
                "question_type": a.question.question_type.value if a.question and a.question.question_type else None,
                "answer_text": a.answer_text,
                "answer_numeric": a.answer_numeric,
                "answer_json": a.answer_json,
                "sentiment": a.sentiment.value if a.sentiment else None,
                "key_phrases": a.key_phrases,
            }
            for a in response.answers
        ],
    }


# =============================================================================
# Analytics Endpoints
# =============================================================================

@router.get("/analytics/summary")
async def get_analytics_summary(
    template_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    loan_officer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get survey analytics summary."""
    org_filter = get_org_filter(current_user, SurveyResponse)

    query = db.query(SurveyResponse).filter(org_filter)

    if template_id:
        query = query.filter(SurveyResponse.template_id == template_id)
    if start_date:
        query = query.filter(SurveyResponse.sent_at >= start_date)
    if end_date:
        query = query.filter(SurveyResponse.sent_at <= end_date)
    if loan_officer_id:
        query = query.filter(SurveyResponse.loan_officer_id == loan_officer_id)

    # Volume metrics
    total_sent = query.count()
    completed = query.filter(SurveyResponse.status == ResponseStatus.COMPLETED).count()
    in_progress = query.filter(SurveyResponse.status == ResponseStatus.IN_PROGRESS).count()

    # Response rate
    response_rate = (completed / total_sent * 100) if total_sent > 0 else 0

    # Score metrics
    completed_responses = query.filter(
        SurveyResponse.status == ResponseStatus.COMPLETED
    ).all()

    nps_scores = [r.nps_score for r in completed_responses if r.nps_score is not None]
    csat_scores = [r.csat_score for r in completed_responses if r.csat_score is not None]

    # NPS calculation
    promoters = len([s for s in nps_scores if s >= 9])
    passives = len([s for s in nps_scores if 7 <= s <= 8])
    detractors = len([s for s in nps_scores if s <= 6])
    nps_total = promoters + passives + detractors
    nps_score = ((promoters - detractors) / nps_total * 100) if nps_total > 0 else None

    # Sentiment breakdown
    sentiment_counts = {
        "very_positive": 0,
        "positive": 0,
        "neutral": 0,
        "negative": 0,
        "very_negative": 0,
    }
    for r in completed_responses:
        if r.sentiment:
            sentiment_counts[r.sentiment.value] = sentiment_counts.get(r.sentiment.value, 0) + 1

    return {
        "volume": {
            "total_sent": total_sent,
            "completed": completed,
            "in_progress": in_progress,
            "response_rate": round(response_rate, 1),
        },
        "nps": {
            "score": round(nps_score, 1) if nps_score is not None else None,
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "total_responses": nps_total,
        },
        "csat": {
            "average": round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None,
            "total_responses": len(csat_scores),
        },
        "sentiment": sentiment_counts,
        "avg_completion_time_seconds": round(
            sum(r.completion_time_seconds or 0 for r in completed_responses) / len(completed_responses)
        ) if completed_responses else None,
    }


@router.get("/analytics/trends")
async def get_analytics_trends(
    template_id: Optional[int] = None,
    period: str = "30d",  # 7d, 30d, 90d, 1y
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get survey analytics trends over time."""
    org_filter = get_org_filter(current_user, SurveyResponse)

    # Calculate date range
    period_days = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(period, 30)
    start_date = datetime.utcnow() - timedelta(days=period_days)

    query = db.query(SurveyResponse).filter(
        and_(org_filter, SurveyResponse.sent_at >= start_date)
    )

    if template_id:
        query = query.filter(SurveyResponse.template_id == template_id)

    responses = query.all()

    # Group by date
    daily_data = {}
    for r in responses:
        if r.sent_at:
            date_key = r.sent_at.strftime("%Y-%m-%d")
            if date_key not in daily_data:
                daily_data[date_key] = {
                    "date": date_key,
                    "sent": 0,
                    "completed": 0,
                    "nps_scores": [],
                }
            daily_data[date_key]["sent"] += 1
            if r.status == ResponseStatus.COMPLETED:
                daily_data[date_key]["completed"] += 1
                if r.nps_score is not None:
                    daily_data[date_key]["nps_scores"].append(r.nps_score)

    # Calculate NPS for each day
    trends = []
    for date_key in sorted(daily_data.keys()):
        data = daily_data[date_key]
        nps_scores = data["nps_scores"]

        nps = None
        if nps_scores:
            promoters = len([s for s in nps_scores if s >= 9])
            detractors = len([s for s in nps_scores if s <= 6])
            total = len(nps_scores)
            nps = round((promoters - detractors) / total * 100, 1)

        trends.append({
            "date": data["date"],
            "sent": data["sent"],
            "completed": data["completed"],
            "response_rate": round(data["completed"] / data["sent"] * 100, 1) if data["sent"] > 0 else 0,
            "nps": nps,
        })

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "trends": trends,
    }


@router.get("/analytics/by-loan-officer")
async def get_analytics_by_lo(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get survey analytics grouped by loan officer."""
    org_filter = get_org_filter(current_user, SurveyResponse)

    query = db.query(SurveyResponse).filter(
        and_(org_filter, SurveyResponse.status == ResponseStatus.COMPLETED)
    )

    if start_date:
        query = query.filter(SurveyResponse.sent_at >= start_date)
    if end_date:
        query = query.filter(SurveyResponse.sent_at <= end_date)

    responses = query.all()

    # Group by LO
    lo_data = {}
    for r in responses:
        lo_id = r.loan_officer_id or 0
        if lo_id not in lo_data:
            lo_data[lo_id] = {
                "loan_officer_id": lo_id,
                "total_responses": 0,
                "nps_scores": [],
                "csat_scores": [],
            }
        lo_data[lo_id]["total_responses"] += 1
        if r.nps_score is not None:
            lo_data[lo_id]["nps_scores"].append(r.nps_score)
        if r.csat_score is not None:
            lo_data[lo_id]["csat_scores"].append(r.csat_score)

    # Calculate metrics
    results = []
    for lo_id, data in lo_data.items():
        nps_scores = data["nps_scores"]
        nps = None
        if nps_scores:
            promoters = len([s for s in nps_scores if s >= 9])
            detractors = len([s for s in nps_scores if s <= 6])
            total = len(nps_scores)
            nps = round((promoters - detractors) / total * 100, 1)

        results.append({
            "loan_officer_id": lo_id,
            "total_responses": data["total_responses"],
            "nps_score": nps,
            "avg_csat": round(sum(data["csat_scores"]) / len(data["csat_scores"]), 2) if data["csat_scores"] else None,
        })

    # Sort by NPS
    results.sort(key=lambda x: x["nps_score"] or -999, reverse=True)

    return {
        "by_loan_officer": results,
    }


# =============================================================================
# Savings Validation
# =============================================================================

@router.post("/savings-validation")
async def create_savings_validation(
    loan_id: int,
    promised_monthly_savings: float,
    promised_total_savings: Optional[float] = None,
    promised_rate_reduction: Optional[float] = None,
    savings_source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a savings validation record to track promised vs actual."""
    org_id = getattr(current_user, 'organization_id', 1)

    validation = SavingsValidation(
        organization_id=org_id,
        loan_id=loan_id,
        promised_monthly_savings=promised_monthly_savings,
        promised_total_savings=promised_total_savings,
        promised_rate_reduction=promised_rate_reduction,
        savings_source=savings_source,
    )

    db.add(validation)
    db.commit()
    db.refresh(validation)

    return {
        "id": validation.id,
        "loan_id": loan_id,
        "promised_monthly_savings": promised_monthly_savings,
        "message": "Savings validation record created",
    }


@router.get("/savings-validation/{loan_id}")
async def get_savings_validation(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get savings validation for a loan."""
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    query = db.query(SavingsValidation).filter(SavingsValidation.loan_id == loan_id)

    if not is_platform_admin and org_id:
        query = query.filter(SavingsValidation.organization_id == org_id)

    validation = query.first()

    if not validation:
        raise HTTPException(status_code=404, detail="Savings validation not found")

    return {
        "id": validation.id,
        "loan_id": validation.loan_id,
        "promised": {
            "monthly_savings": validation.promised_monthly_savings,
            "total_savings": validation.promised_total_savings,
            "rate_reduction": validation.promised_rate_reduction,
        },
        "reported": {
            "monthly_savings": validation.reported_monthly_savings,
            "satisfied": validation.reported_satisfied,
        },
        "discrepancy_amount": validation.discrepancy_amount,
        "follow_up_required": validation.follow_up_required,
        "resolved_at": validation.resolved_at.isoformat() if validation.resolved_at else None,
    }


# =============================================================================
# Helper Functions (Background Tasks)
# =============================================================================

async def send_survey_email(
    email: str,
    template_name: str,
    survey_url: str,
    intro_message: Optional[str] = None
):
    """Send survey invitation email (placeholder for actual email service)."""
    # TODO: Integrate with email service (SendGrid, AWS SES, etc.)
    logger.info(f"Sending survey email to {email}")
    logger.info(f"Template: {template_name}")
    logger.info(f"URL: {survey_url}")
    logger.info(f"Message: {intro_message}")


def analyze_sentiment(text: str) -> float:
    """Analyze text sentiment (placeholder for actual NLP service)."""
    # TODO: Integrate with sentiment analysis service (AWS Comprehend, etc.)
    # For now, return a simple heuristic
    positive_words = ["great", "excellent", "amazing", "wonderful", "fantastic", "love", "best", "helpful"]
    negative_words = ["bad", "terrible", "awful", "worst", "hate", "poor", "slow", "frustrated"]

    text_lower = text.lower()
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)

    if positive_count + negative_count == 0:
        return 0.0

    return (positive_count - negative_count) / (positive_count + negative_count)


def extract_key_phrases(text: str) -> List[str]:
    """Extract key phrases from text (placeholder for actual NLP service)."""
    # TODO: Integrate with key phrase extraction service
    # For now, return simple word extraction
    words = text.split()
    # Return words longer than 5 characters as "key phrases"
    return list(set(word.strip(".,!?").lower() for word in words if len(word) > 5))[:5]
