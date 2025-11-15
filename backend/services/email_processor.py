"""
Email Processing Service
Comprehensive email processing with Claude parser integration
Supports toggling between OpenAI (legacy) and Claude (new)
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

# Import AI providers
from ai_providers.claude_parser import get_claude_parser

# Import models
from models.email_interaction import EmailInteraction
from models.lead_profile import LeadProfile
from models.active_loan_profile import ActiveLoanProfile
from models.mum_client_profile import MUMClientProfile
from models.team_member_profile import TeamMemberProfile
from models.data_conflict import DataConflict

logger = logging.getLogger(__name__)


class EmailProcessor:
    """
    Comprehensive email processor with AI parsing
    Supports both Claude (new) and OpenAI (legacy) parsers
    """

    def __init__(self):
        self.ai_provider = os.getenv("AI_PROVIDER", "openai").lower()
        logger.info(f"EmailProcessor initialized with AI provider: {self.ai_provider}")

        if self.ai_provider == "claude":
            self.parser = get_claude_parser()
        else:
            # Legacy OpenAI parser (from main.py functions)
            self.parser = None
            logger.info("Using legacy OpenAI parser")

    async def process_email(
        self,
        email_data: Dict[str, Any],
        user_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Complete email processing pipeline

        1. Classify email → determine profile type
        2. Parse email with AI → extract fields
        3. Match to existing profile or create new
        4. Store EmailInteraction
        5. Apply updates or flag conflicts

        Args:
            email_data: Email dict with subject, body, from, etc.
            user_id: User ID who owns this email
            db: Database session

        Returns:
            Processing result dict with status, profile info, etc.
        """

        start_time = datetime.utcnow()
        email_id = email_data.get('id', email_data.get('email_id', email_data.get('message_id')))

        try:
            logger.info(f"Processing email {email_id} with {self.ai_provider} parser")

            # Step 1: Classify email to determine profile type
            if self.ai_provider == "claude":
                profile_type = self.parser.classify_email(email_data)
            else:
                # Legacy classification
                profile_type = self._legacy_classify(email_data)

            logger.info(f"Email classified as: {profile_type}")

            # Step 2: Parse email with AI
            if self.ai_provider == "claude":
                parsed_result = await self.parser.parse_email(
                    email_data,
                    profile_type,
                    current_profile=None  # TODO: Load current profile after matching
                )
            else:
                # Legacy OpenAI parsing
                parsed_result = self._legacy_parse(email_data, profile_type)

            logger.info(f"Parsed {parsed_result.get('field_count', 0)} fields with {parsed_result.get('overall_confidence', 0)}% confidence")

            # Step 3: Match to existing profile
            match_result = await self._match_profile(
                parsed_result['extracted_fields'],
                profile_type,
                db,
                user_id
            )

            logger.info(f"Profile match: {match_result['match_type']} (confidence: {match_result.get('confidence', 0)}%)")

            # Step 4: Create EmailInteraction record
            email_interaction = EmailInteraction(
                email_id=email_id,
                profile_type=profile_type,
                thread_id=email_data.get('thread_id'),
                conversation_id=email_data.get('conversation_id'),
                subject=email_data.get('subject'),
                from_email=email_data.get('from_email', email_data.get('sender')),
                to_emails=email_data.get('to_emails', []),
                cc_emails=email_data.get('cc_emails', []),
                sent_date=email_data.get('sent_date', email_data.get('received_at')),
                received_date=email_data.get('received_date', email_data.get('received_at')),
                body_text=email_data.get('body_text', email_data.get('raw_text')),
                body_html=email_data.get('body_html', email_data.get('raw_html')),
                attachments=email_data.get('attachments'),
                parsed_data=parsed_result,
                extracted_fields=parsed_result.get('extracted_fields'),
                confidence_scores=parsed_result.get('confidence_scores'),
                milestone_triggers=parsed_result.get('milestone_triggers'),
                field_updates=parsed_result.get('field_updates'),
                conflicts=parsed_result.get('conflicts'),
                email_summary=parsed_result.get('email_summary'),
                sentiment=parsed_result.get('sentiment'),
                urgency_score=parsed_result.get('urgency_score'),
                suggested_actions=parsed_result.get('suggested_actions'),
                next_best_action=parsed_result.get('next_best_action'),
                parser_version=parsed_result.get('extraction_metadata', {}).get('parser_version'),
                parser_model=parsed_result.get('extraction_metadata', {}).get('model'),
                processing_time_ms=parsed_result.get('extraction_metadata', {}).get('processing_time_ms'),
                overall_confidence=parsed_result.get('overall_confidence'),
                field_count=parsed_result.get('field_count'),
                user_id=user_id,
                sync_status='pending'
            )

            # Link to profile if matched
            if match_result['profile_id']:
                if profile_type == 'lead':
                    email_interaction.lead_profile_id = match_result['profile_id']
                elif profile_type == 'active_loan':
                    email_interaction.active_loan_id = match_result['profile_id']
                elif profile_type == 'mum_client':
                    email_interaction.mum_client_id = match_result['profile_id']
                elif profile_type == 'team_member':
                    email_interaction.team_member_id = match_result['profile_id']

            db.add(email_interaction)
            db.commit()
            db.refresh(email_interaction)

            logger.info(f"Created EmailInteraction {email_interaction.id}")

            # Step 5: Apply updates or create profile
            if match_result['match_type'] == 'new':
                # Create new profile
                new_profile = await self._create_profile(
                    parsed_result['extracted_fields'],
                    profile_type,
                    email_interaction.id,
                    user_id,
                    db
                )
                email_interaction.sync_status = 'applied'
                result_action = 'created_profile'
                result_profile_id = new_profile.id
            else:
                # Update existing profile
                update_result = await self._apply_updates(
                    match_result['profile_id'],
                    profile_type,
                    parsed_result,
                    email_interaction.id,
                    db
                )
                email_interaction.sync_status = update_result['status']
                result_action = update_result['action']
                result_profile_id = match_result['profile_id']

            db.commit()

            total_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return {
                'status': 'success',
                'email_interaction_id': str(email_interaction.id),
                'profile_type': profile_type,
                'profile_id': str(result_profile_id),
                'match_result': match_result,
                'action': result_action,
                'field_count': parsed_result.get('field_count', 0),
                'overall_confidence': parsed_result.get('overall_confidence', 0),
                'conflicts_count': len(parsed_result.get('conflicts', [])),
                'processing_time_ms': total_time_ms,
                'ai_provider': self.ai_provider
            }

        except Exception as e:
            logger.error(f"Error processing email {email_id}: {e}")
            import traceback
            traceback.print_exc()

            return {
                'status': 'error',
                'error': str(e),
                'email_id': email_id
            }

    async def _match_profile(
        self,
        extracted_fields: Dict[str, Any],
        profile_type: str,
        db: Session,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Match extracted fields to existing profile
        Simple matching for Phase 1 (exact email/phone/loan_number match)
        Phase 2 will add advanced fuzzy matching
        """

        # Get appropriate model
        if profile_type == 'lead':
            model = LeadProfile
        elif profile_type == 'active_loan':
            model = ActiveLoanProfile
        elif profile_type == 'mum_client':
            model = MUMClientProfile
        elif profile_type == 'team_member':
            model = TeamMemberProfile
        else:
            return {'match_type': 'new', 'profile_id': None, 'confidence': 0}

        # Try email match (highest confidence)
        if email := extracted_fields.get('email'):
            profile = db.query(model).filter_by(email=email).first()
            if profile:
                return {
                    'match_type': 'email',
                    'profile_id': profile.id,
                    'confidence': 100,
                    'reasoning': f'Exact email match: {email}'
                }

        # Try phone match
        if phone := extracted_fields.get('phone'):
            profile = db.query(model).filter_by(phone=phone).first()
            if profile:
                return {
                    'match_type': 'phone',
                    'profile_id': profile.id,
                    'confidence': 95,
                    'reasoning': f'Exact phone match: {phone}'
                }

        # Try loan number match (for active_loan)
        if profile_type == 'active_loan' and (loan_num := extracted_fields.get('loan_number')):
            profile = db.query(ActiveLoanProfile).filter_by(loan_number=loan_num).first()
            if profile:
                return {
                    'match_type': 'loan_number',
                    'profile_id': profile.id,
                    'confidence': 100,
                    'reasoning': f'Exact loan number match: {loan_num}'
                }

        # No match found - new profile
        return {
            'match_type': 'new',
            'profile_id': None,
            'confidence': 100,
            'reasoning': 'No existing profile found'
        }

    async def _create_profile(
        self,
        extracted_fields: Dict[str, Any],
        profile_type: str,
        email_interaction_id: str,
        user_id: int,
        db: Session
    ):
        """Create new profile from extracted fields"""

        logger.info(f"Creating new {profile_type} profile")

        if profile_type == 'lead':
            profile = LeadProfile(
                first_name=extracted_fields.get('first_name'),
                last_name=extracted_fields.get('last_name'),
                email=extracted_fields.get('email'),
                phone=extracted_fields.get('phone'),
                employment_status=extracted_fields.get('employment_status'),
                employer_name=extracted_fields.get('employer_name'),
                job_title=extracted_fields.get('job_title'),
                annual_income=extracted_fields.get('annual_income'),
                property_value=extracted_fields.get('property_value'),
                loan_amount=extracted_fields.get('loan_amount'),
                credit_score=extracted_fields.get('credit_score'),
                address=extracted_fields.get('address'),
                city=extracted_fields.get('city'),
                state=extracted_fields.get('state'),
                zip_code=extracted_fields.get('zip_code'),
                loan_type=extracted_fields.get('loan_type'),
                data_sources=['email_inbound']
            )

        elif profile_type == 'active_loan':
            profile = ActiveLoanProfile(
                loan_number=extracted_fields.get('loan_number', f'LOAN-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'),
                amount=extracted_fields.get('amount'),
                rate=extracted_fields.get('rate'),
                property_address=extracted_fields.get('property_address'),
                property_city=extracted_fields.get('property_city'),
                property_state=extracted_fields.get('property_state'),
                loan_officer_name=extracted_fields.get('loan_officer_name'),
                processor=extracted_fields.get('processor'),
                data_sources=['email_inbound']
            )

        elif profile_type == 'mum_client':
            profile = MUMClientProfile(
                name=extracted_fields.get('name'),
                email=extracted_fields.get('email'),
                phone=extracted_fields.get('phone'),
                loan_number=extracted_fields.get('loan_number'),
                loan_balance=extracted_fields.get('loan_balance'),
                data_sources=['email_inbound']
            )

        elif profile_type == 'team_member':
            profile = TeamMemberProfile(
                name=extracted_fields.get('name'),
                email=extracted_fields.get('email'),
                phone=extracted_fields.get('phone'),
                employee_id=extracted_fields.get('employee_id'),
                department=extracted_fields.get('department'),
                data_sources=['email_inbound']
            )

        db.add(profile)
        db.commit()
        db.refresh(profile)

        logger.info(f"Created new {profile_type} profile with ID: {profile.id}")
        return profile

    async def _apply_updates(
        self,
        profile_id: str,
        profile_type: str,
        parsed_result: Dict[str, Any],
        email_interaction_id: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Apply updates to existing profile
        For Phase 1: Simple updates with high confidence
        Phase 3 will add full conflict resolution
        """

        extracted_fields = parsed_result['extracted_fields']
        confidence_scores = parsed_result['confidence_scores']
        conflicts = parsed_result.get('conflicts', [])

        # Get profile
        if profile_type == 'lead':
            profile = db.query(LeadProfile).filter_by(id=profile_id).first()
        elif profile_type == 'active_loan':
            profile = db.query(ActiveLoanProfile).filter_by(id=profile_id).first()
        elif profile_type == 'mum_client':
            profile = db.query(MUMClientProfile).filter_by(id=profile_id).first()
        elif profile_type == 'team_member':
            profile = db.query(TeamMemberProfile).filter_by(id=profile_id).first()

        if not profile:
            return {'status': 'error', 'action': 'profile_not_found'}

        updated_fields = []
        conflicts_created = []

        # Apply high-confidence updates only
        for field, value in extracted_fields.items():
            if value is None:
                continue

            confidence = confidence_scores.get(field, 0)
            current_value = getattr(profile, field, None)

            # Only update if high confidence and field is empty or value changed
            if confidence >= 80:
                if current_value is None or current_value == '':
                    setattr(profile, field, value)
                    updated_fields.append(field)
                    logger.info(f"Updated {profile_type}.{field} = {value} (conf: {confidence}%)")
                elif current_value != value:
                    # Value differs - create conflict for review
                    conflict = DataConflict(
                        profile_id=profile_id,
                        profile_type=profile_type,
                        email_interaction_id=email_interaction_id,
                        field_name=field,
                        current_value=str(current_value),
                        proposed_value=str(value),
                        conflict_reason=f'Email suggests different value (confidence: {confidence}%)',
                        confidence=confidence,
                        suggested_resolution='manual_review',
                        status='pending'
                    )
                    db.add(conflict)
                    conflicts_created.append(field)
                    logger.info(f"Created conflict for {profile_type}.{field}: {current_value} vs {value}")

        db.commit()

        if updated_fields:
            return {
                'status': 'applied',
                'action': 'updated',
                'updated_fields': updated_fields,
                'conflicts': conflicts_created
            }
        elif conflicts_created:
            return {
                'status': 'conflict',
                'action': 'conflict_review_needed',
                'conflicts': conflicts_created
            }
        else:
            return {
                'status': 'skipped',
                'action': 'no_updates',
                'reason': 'No high-confidence fields to update'
            }

    def _legacy_classify(self, email_data: Dict[str, Any]) -> str:
        """Legacy classification (basic keyword matching)"""
        subject = email_data.get('subject', '').lower()
        body = email_data.get('body_text', email_data.get('raw_text', '')).lower()

        if any(kw in subject or kw in body for kw in ['loan #', 'loan number', 'appraisal', 'clear to close']):
            return 'active_loan'
        elif any(kw in subject or kw in body for kw in ['refinance', 'rate drop', 'portfolio']):
            return 'mum_client'
        elif any(kw in subject or kw in body for kw in ['team member', 'employee', 'performance']):
            return 'team_member'
        else:
            return 'lead'

    def _legacy_parse(self, email_data: Dict[str, Any], profile_type: str) -> Dict[str, Any]:
        """Legacy OpenAI parsing (fallback)"""
        # This would call the existing OpenAI parsing functions from main.py
        # For Phase 1, we'll just return minimal structure
        return {
            'extracted_fields': {},
            'confidence_scores': {},
            'calculated_fields': {},
            'milestone_triggers': [],
            'field_updates': [],
            'conflicts': [],
            'suggested_actions': [],
            'email_summary': email_data.get('subject', 'Email'),
            'sentiment': 'neutral',
            'urgency_score': 50,
            'next_best_action': '',
            'overall_confidence': 0,
            'field_count': 0
        }


# Singleton instance
_email_processor = None

def get_email_processor() -> EmailProcessor:
    """Get or create email processor singleton"""
    global _email_processor
    if _email_processor is None:
        _email_processor = EmailProcessor()
    return _email_processor
