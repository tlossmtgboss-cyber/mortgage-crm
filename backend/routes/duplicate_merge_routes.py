"""
Duplicate Merge & AI Learning Routes

Handles duplicate lead detection, AI-powered merge suggestions, and learning from user decisions.
Features:
- Find potential duplicate leads based on name, email, phone similarity
- Generate AI suggestions for field merging with confidence scores
- Train AI model based on user merge decisions
- Track accuracy and unlock autopilot mode after 100 consecutive correct predictions
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import logging
import difflib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/merge", tags=["duplicate-merge"])

# Dependency injection placeholders - set by main.py
User = None
Lead = None
DuplicatePair = None
MergeTrainingEvent = None
MergeAIModel = None
_get_current_user = None
_get_db = None


def set_dependencies(
    user_model,
    lead_model,
    duplicate_pair_model,
    merge_training_event_model,
    merge_ai_model,
    current_user_func,
    db_func
):
    """Set dependencies for this router."""
    global User, Lead, DuplicatePair, MergeTrainingEvent, MergeAIModel
    global _get_current_user, _get_db
    User = user_model
    Lead = lead_model
    DuplicatePair = duplicate_pair_model
    MergeTrainingEvent = merge_training_event_model
    MergeAIModel = merge_ai_model
    _get_current_user = current_user_func
    _get_db = db_func


def get_db():
    """Get database session - wrapper that works at request time."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


from auth.dependencies import get_current_user  # dedup: was local wrapper
# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def find_duplicate_leads(user_id: int, db: Session, threshold: float = 0.75):
    """
    Find potential duplicate leads based on name, email, phone similarity
    """
    leads = db.query(Lead).filter(Lead.owner_id == user_id).all()
    duplicates = []

    processed_pairs = set()

    for i, lead1 in enumerate(leads):
        for lead2 in leads[i+1:]:
            # Skip if already processed
            pair_id = tuple(sorted([lead1.id, lead2.id]))
            if pair_id in processed_pairs:
                continue

            # Calculate similarity
            similarity_scores = []

            # Name similarity
            if lead1.name and lead2.name:
                name_sim = difflib.SequenceMatcher(None, lead1.name.lower(), lead2.name.lower()).ratio()
                similarity_scores.append(name_sim * 0.4)  # 40% weight

            # Email similarity
            if lead1.email and lead2.email:
                email_sim = 1.0 if lead1.email.lower() == lead2.email.lower() else 0.0
                similarity_scores.append(email_sim * 0.3)  # 30% weight

            # Phone similarity
            if lead1.phone and lead2.phone:
                phone1 = ''.join(filter(str.isdigit, lead1.phone))
                phone2 = ''.join(filter(str.isdigit, lead2.phone))
                phone_sim = 1.0 if phone1 == phone2 else 0.0
                similarity_scores.append(phone_sim * 0.3)  # 30% weight

            if similarity_scores:
                total_similarity = sum(similarity_scores) / len(similarity_scores) * len(similarity_scores)

                if total_similarity >= threshold:
                    duplicates.append({
                        'lead1': lead1,
                        'lead2': lead2,
                        'similarity': total_similarity
                    })
                    processed_pairs.add(pair_id)

    return duplicates


def generate_ai_merge_suggestion(lead1, lead2, training_history: list, db: Session):
    """
    Generate AI suggestion for which fields to keep when merging
    Uses past training history to make smarter predictions
    """
    suggestions = {}

    # Define all lead fields to compare
    fields_to_compare = [
        'name', 'email', 'phone', 'co_applicant_name', 'co_applicant_email', 'co_applicant_phone',
        'source', 'stage', 'loan_type', 'preapproval_amount', 'credit_score', 'debt_to_income',
        'address', 'city', 'state', 'zip_code', 'property_type', 'property_value', 'down_payment',
        'loan_number', 'notes', 'employment_status', 'annual_income', 'monthly_debts',
        'first_time_buyer', 'loan_amount', 'interest_rate', 'loan_term', 'last_contact'
    ]

    for field in fields_to_compare:
        val1 = getattr(lead1, field, None)
        val2 = getattr(lead2, field, None)

        # Skip if both are None
        if val1 is None and val2 is None:
            continue

        # If only one has value, choose that one
        if val1 is None:
            # Convert datetime to ISO string for JSON serialization
            val2_serializable = val2.isoformat() if isinstance(val2, datetime) else val2
            suggestions[field] = {'record': 2, 'value': val2_serializable, 'confidence': 0.95}
        elif val2 is None:
            # Convert datetime to ISO string for JSON serialization
            val1_serializable = val1.isoformat() if isinstance(val1, datetime) else val1
            suggestions[field] = {'record': 1, 'value': val1_serializable, 'confidence': 0.95}
        else:
            # Both have values - use AI logic
            confidence = 0.6  # Default moderate confidence
            chosen_record = 1

            # Apply training-based logic
            if training_history:
                # Check if this user has history with this field
                field_history = [t for t in training_history if t.field_name == field]
                if field_history:
                    # Calculate user's preference pattern
                    record_1_choices = sum(1 for t in field_history if t.user_chosen_record == 1)
                    record_2_choices = sum(1 for t in field_history if t.user_chosen_record == 2)

                    if record_1_choices > record_2_choices:
                        chosen_record = 1
                        confidence = min(0.85, 0.6 + (record_1_choices / len(field_history)) * 0.3)
                    else:
                        chosen_record = 2
                        confidence = min(0.85, 0.6 + (record_2_choices / len(field_history)) * 0.3)

            # Heuristics for specific fields
            if field == 'email' and '@' in str(val1) and '@' in str(val2):
                # Prefer newer email (more likely to be current)
                chosen_record = 2 if lead2.created_at > lead1.created_at else 1
                confidence = 0.7
            elif field == 'phone':
                # Prefer longer phone number (more complete)
                len1 = len(''.join(filter(str.isdigit, str(val1))))
                len2 = len(''.join(filter(str.isdigit, str(val2))))
                chosen_record = 1 if len1 >= len2 else 2
                confidence = 0.75
            elif field in ['loan_amount', 'preapproval_amount', 'annual_income']:
                # Prefer higher value (more recent/accurate)
                chosen_record = 1 if val1 >= val2 else 2
                confidence = 0.65
            elif field == 'last_contact':
                # Prefer more recent contact
                chosen_record = 1 if val1 > val2 else 2
                confidence = 0.9
            elif field == 'stage':
                # Prefer further along in pipeline
                stages_order = ['New', 'Attempted Contact', 'Prospect', 'Application Started', 'Application Complete', 'Pre-Approved']
                idx1 = stages_order.index(str(val1)) if str(val1) in stages_order else -1
                idx2 = stages_order.index(str(val2)) if str(val2) in stages_order else -1
                chosen_record = 1 if idx1 >= idx2 else 2
                confidence = 0.8

            chosen_val = val1 if chosen_record == 1 else val2
            # Convert datetime objects to ISO string for JSON serialization
            if isinstance(chosen_val, datetime):
                chosen_val = chosen_val.isoformat()
            suggestions[field] = {'record': chosen_record, 'value': chosen_val, 'confidence': confidence}

    return suggestions


# =============================================================================
# ROUTES
# =============================================================================

@router.get("/duplicates")
async def get_duplicate_leads(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Find and return potential duplicate leads that need merging
    """
    try:
        # Find duplicates
        duplicates = find_duplicate_leads(current_user.id, db)

        # Check for existing duplicate pairs in database
        existing_pairs = db.query(DuplicatePair).filter(
            DuplicatePair.user_id == current_user.id,
            DuplicatePair.status == 'pending'
        ).all()

        existing_pair_ids = {(p.lead_id_1, p.lead_id_2) for p in existing_pairs}

        # Create new duplicate pairs for newly found duplicates
        for dup in duplicates:
            pair_id = tuple(sorted([dup['lead1'].id, dup['lead2'].id]))
            if pair_id not in existing_pair_ids:
                # Get training history for AI suggestions
                training_history = db.query(MergeTrainingEvent).filter(
                    MergeTrainingEvent.user_id == current_user.id
                ).all()

                # Generate AI suggestion
                ai_suggestion = generate_ai_merge_suggestion(
                    dup['lead1'], dup['lead2'], training_history, db
                )

                new_pair = DuplicatePair(
                    lead_id_1=dup['lead1'].id,
                    lead_id_2=dup['lead2'].id,
                    similarity_score=dup['similarity'],
                    ai_suggestion=ai_suggestion,
                    user_id=current_user.id,
                    status='pending'
                )
                db.add(new_pair)

        db.commit()

        # Get all pending pairs with lead details
        pending_pairs = db.query(DuplicatePair).filter(
            DuplicatePair.user_id == current_user.id,
            DuplicatePair.status == 'pending'
        ).all()

        # OPTIMIZED: Batch load all leads at once instead of N+1 queries
        lead_ids = set()
        for pair in pending_pairs:
            lead_ids.add(pair.lead_id_1)
            lead_ids.add(pair.lead_id_2)

        leads_map = {}
        if lead_ids:
            leads = db.query(Lead).filter(Lead.id.in_(lead_ids)).all()
            leads_map = {lead.id: lead for lead in leads}

        result = []
        for pair in pending_pairs:
            lead1 = leads_map.get(pair.lead_id_1)
            lead2 = leads_map.get(pair.lead_id_2)

            if lead1 and lead2:
                result.append({
                    'id': pair.id,
                    'similarity_score': pair.similarity_score,
                    'ai_suggestion': pair.ai_suggestion,
                    'lead1': {
                        'id': lead1.id,
                        'name': lead1.name,
                        'email': lead1.email,
                        'phone': lead1.phone,
                        'source': lead1.source,
                        'stage': lead1.stage.value if lead1.stage else None,
                        'loan_type': lead1.loan_type,
                        'preapproval_amount': lead1.preapproval_amount,
                        'address': lead1.address,
                        'city': lead1.city,
                        'state': lead1.state,
                        'zip_code': lead1.zip_code,
                        'created_at': lead1.created_at.isoformat() if lead1.created_at else None,
                        'last_contact': lead1.last_contact.isoformat() if lead1.last_contact else None
                    },
                    'lead2': {
                        'id': lead2.id,
                        'name': lead2.name,
                        'email': lead2.email,
                        'phone': lead2.phone,
                        'source': lead2.source,
                        'stage': lead2.stage.value if lead2.stage else None,
                        'loan_type': lead2.loan_type,
                        'preapproval_amount': lead2.preapproval_amount,
                        'address': lead2.address,
                        'city': lead2.city,
                        'state': lead2.state,
                        'zip_code': lead2.zip_code,
                        'created_at': lead2.created_at.isoformat() if lead2.created_at else None,
                        'last_contact': lead2.last_contact.isoformat() if lead2.last_contact else None
                    }
                })

        # Get AI training status
        ai_model = db.query(MergeAIModel).filter(
            MergeAIModel.user_id == current_user.id
        ).first()

        if not ai_model:
            ai_model = MergeAIModel(user_id=current_user.id)
            db.add(ai_model)
            db.commit()

        return {
            'pending_pairs': result,
            'total_count': len(result),
            'ai_training_status': {
                'total_predictions': ai_model.total_predictions,
                'correct_predictions': ai_model.correct_predictions,
                'consecutive_correct': ai_model.consecutive_correct,
                'accuracy': ai_model.accuracy,
                'autopilot_enabled': ai_model.autopilot_enabled,
                'progress_to_autopilot': f"{ai_model.consecutive_correct}/100"
            }
        }

    except Exception as e:
        logger.error(f"Error finding duplicates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/execute")
async def execute_merge(
    merge_data: dict,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Execute the merge based on user's choices
    Train the AI from user's decisions
    """
    try:
        pair_id = merge_data.get('pair_id')
        user_choices = merge_data.get('choices')  # {field_name: record_number}
        principal_record = merge_data.get('principal_record')  # 1 or 2

        # Get duplicate pair
        pair = db.query(DuplicatePair).filter(
            DuplicatePair.id == pair_id,
            DuplicatePair.user_id == current_user.id
        ).first()

        if not pair:
            raise HTTPException(status_code=404, detail="Duplicate pair not found")

        # Get leads
        lead1 = db.query(Lead).filter(Lead.id == pair.lead_id_1).first()
        lead2 = db.query(Lead).filter(Lead.id == pair.lead_id_2).first()

        if not lead1 or not lead2:
            raise HTTPException(status_code=404, detail="Leads not found")

        # Determine principal and secondary
        principal_lead = lead1 if principal_record == 1 else lead2
        secondary_lead = lead2 if principal_record == 1 else lead1

        # Track AI accuracy
        ai_model = db.query(MergeAIModel).filter(
            MergeAIModel.user_id == current_user.id
        ).first()

        if not ai_model:
            ai_model = MergeAIModel(user_id=current_user.id)
            db.add(ai_model)

        all_correct = True
        training_events = []

        # Apply user choices and train AI
        for field_name, chosen_record in user_choices.items():
            ai_suggestion = pair.ai_suggestion.get(field_name, {})
            ai_suggested_record = ai_suggestion.get('record')

            # Get values
            val1 = getattr(lead1, field_name, None)
            val2 = getattr(lead2, field_name, None)
            chosen_value = val1 if chosen_record == 1 else val2

            # Update principal lead with chosen value
            _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
            if chosen_value is not None and field_name not in _protected:
                setattr(principal_lead, field_name, chosen_value)

            # Track if AI was correct
            was_correct = (ai_suggested_record == chosen_record) if ai_suggested_record else False
            if not was_correct:
                all_correct = False

            # Create training event
            training_event = MergeTrainingEvent(
                duplicate_pair_id=pair.id,
                field_name=field_name,
                ai_suggested_value=str(ai_suggestion.get('value')) if ai_suggestion else None,
                ai_suggested_record=ai_suggested_record,
                user_chosen_value=str(chosen_value),
                user_chosen_record=chosen_record,
                was_correct=was_correct,
                user_id=current_user.id
            )
            db.add(training_event)
            training_events.append(training_event)

        # Update AI model statistics
        ai_model.total_predictions += len(user_choices)
        correct_count = sum(1 for t in training_events if t.was_correct)
        ai_model.correct_predictions += correct_count

        if all_correct and len(training_events) > 0:
            ai_model.consecutive_correct += 1
        else:
            ai_model.consecutive_correct = 0  # Reset streak

        ai_model.accuracy = (ai_model.correct_predictions / ai_model.total_predictions) if ai_model.total_predictions > 0 else 0
        ai_model.last_prediction_at = datetime.now(timezone.utc)

        # Check if autopilot should be enabled
        if ai_model.consecutive_correct >= 100 and not ai_model.autopilot_enabled:
            ai_model.autopilot_enabled = True
            ai_model.autopilot_enabled_at = datetime.now(timezone.utc)
            logger.info(f"Autopilot enabled for user {current_user.id} after 100 consecutive correct predictions!")

        # Delete secondary lead
        db.delete(secondary_lead)

        # Update duplicate pair
        pair.status = 'merged'
        pair.principal_record_id = principal_lead.id
        pair.user_decision = user_choices
        pair.merged_at = datetime.now(timezone.utc)
        pair.merged_by = current_user.id

        db.commit()

        return {
            'success': True,
            'message': 'Leads merged successfully',
            'principal_lead_id': principal_lead.id,
            'ai_training': {
                'fields_tracked': len(training_events),
                'ai_correct': correct_count,
                'accuracy': f"{(correct_count / len(training_events) * 100):.1f}%" if training_events else "0%",
                'consecutive_correct': ai_model.consecutive_correct,
                'autopilot_enabled': ai_model.autopilot_enabled,
                'autopilot_unlocked': ai_model.consecutive_correct >= 100
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing merge: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/dismiss")
async def dismiss_duplicate(
    dismiss_data: dict,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Dismiss a duplicate pair (not actually duplicates)
    """
    try:
        pair_id = dismiss_data.get('pair_id')

        pair = db.query(DuplicatePair).filter(
            DuplicatePair.id == pair_id,
            DuplicatePair.user_id == current_user.id
        ).first()

        if not pair:
            raise HTTPException(status_code=404, detail="Duplicate pair not found")

        pair.status = 'dismissed'
        db.commit()

        return {'success': True, 'message': 'Duplicate dismissed'}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dismissing duplicate: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/completed")
async def get_completed_merges(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of completed merges for review and feedback
    """
    try:
        # Query completed merges
        completed_pairs = db.query(DuplicatePair).filter(
            DuplicatePair.user_id == current_user.id,
            DuplicatePair.status.in_(['merged', 'auto_merged'])
        ).order_by(DuplicatePair.merged_at.desc()).limit(50).all()

        # OPTIMIZED: Batch load all leads at once instead of N+1 queries
        lead_ids = set()
        for pair in completed_pairs:
            lead_ids.add(pair.lead_id_1)
            lead_ids.add(pair.lead_id_2)
            if pair.principal_record_id:
                lead_ids.add(pair.principal_record_id)

        leads_map = {}
        if lead_ids:
            leads = db.query(Lead).filter(Lead.id.in_(lead_ids)).all()
            leads_map = {lead.id: lead for lead in leads}

        completed_tasks = []
        for pair in completed_pairs:
            # Get the lead details from batch-loaded map
            lead1 = leads_map.get(pair.lead_id_1)
            lead2 = leads_map.get(pair.lead_id_2)
            principal = leads_map.get(pair.principal_record_id)

            # Calculate AI accuracy for this merge
            training_events = db.query(MergeTrainingEvent).filter(
                MergeTrainingEvent.duplicate_pair_id == pair.id
            ).all()

            fields_merged = len(training_events)
            ai_correct = sum(1 for event in training_events if event.was_correct)
            ai_accuracy = (ai_correct / fields_merged) if fields_merged > 0 else 0
            user_overrides = fields_merged - ai_correct

            completed_tasks.append({
                'id': pair.id,
                'completed_at': pair.merged_at.isoformat() if pair.merged_at else None,
                'lead1_name': lead1.name if lead1 else 'Unknown',
                'lead2_name': lead2.name if lead2 else 'Unknown',
                'principal_name': principal.name if principal else 'Unknown',
                'principal_id': pair.principal_record_id,
                'fields_merged': fields_merged,
                'ai_accuracy': ai_accuracy,
                'user_overrides': user_overrides,
                'similarity_score': pair.similarity_score or 0,
                'status': pair.status
            })

        return {
            'success': True,
            'completed_tasks': completed_tasks,
            'total_count': len(completed_tasks)
        }

    except Exception as e:
        logger.error(f"Error fetching completed merges: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/feedback")
async def submit_merge_feedback(
    feedback_data: dict,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit feedback on a completed merge to improve AI accuracy
    """
    try:
        task_id = feedback_data.get('task_id')
        feedback = feedback_data.get('feedback', '').strip()

        if not feedback:
            raise HTTPException(status_code=400, detail="Feedback cannot be empty")

        # Get the duplicate pair
        pair = db.query(DuplicatePair).filter(
            DuplicatePair.id == task_id,
            DuplicatePair.user_id == current_user.id
        ).first()

        if not pair:
            raise HTTPException(status_code=404, detail="Merge task not found")

        # Store feedback in user_decision JSON field
        if pair.user_decision is None:
            pair.user_decision = {}

        if not isinstance(pair.user_decision, dict):
            pair.user_decision = {}

        pair.user_decision['feedback'] = feedback
        pair.user_decision['feedback_at'] = datetime.now(timezone.utc).isoformat()

        db.commit()

        logger.info(f"Feedback submitted for merge {task_id} by user {current_user.id}")

        return {
            'success': True,
            'message': 'Feedback submitted successfully. This will help improve AI accuracy.'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
