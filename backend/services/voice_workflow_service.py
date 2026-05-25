"""
Voice Workflow Service - Core State Machine & Orchestration

Manages voice-driven workflow sessions for task completion through
natural two-way conversations. Uses a state machine pattern with
Claude AI for slot extraction and natural language understanding.
"""
import os
import json
import logging
from uuid import uuid4, UUID
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from models.voice_workflow_models import (
    WorkflowType,
    PreApprovalWorkflowState,
    UserIntent,
    VoiceWorkflowSession,
    ConversationTurn,
    SlotExtractionResult,
    PreApprovalLetterSlots,
    WorkflowExecutionResult,
    ApplicantVoiceContext,
    RealtorVoiceContext,
)
from services.voice_slot_extractor import get_slot_extractor
from services.voice_response_generator import get_response_generator
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class VoiceWorkflowService:
    """
    Orchestrates voice-driven workflows using a state machine pattern.

    Each workflow type has defined states and transitions. User voice input
    is processed by Claude to extract intent and slot values, then the
    state machine advances based on the extraction results.
    """

    def __init__(self, db: Session):
        self.db = db
        self.slot_extractor = get_slot_extractor()
        self.response_generator = get_response_generator()

    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================

    async def create_session(
        self,
        user_id: int,
        workflow_type: WorkflowType,
        initial_transcript: Optional[str] = None,
    ) -> Tuple[VoiceWorkflowSession, Dict[str, Any]]:
        """
        Create a new voice workflow session.

        Args:
            user_id: The loan officer's user ID
            workflow_type: Type of workflow to start
            initial_transcript: Optional initial voice command

        Returns:
            Tuple of (session, response_data with text and audio)
        """
        session_id = uuid4()

        # Determine initial state based on workflow type
        if workflow_type == WorkflowType.PRE_APPROVAL_LETTER:
            initial_state = PreApprovalWorkflowState.INTENT_DETECTED.value
        else:
            initial_state = "started"

        # Create session in database
        self.db.execute(text("""
            INSERT INTO voice_workflow_sessions (
                id, user_id, workflow_type, current_state, slots,
                conversation_history, started_at, is_active
            ) VALUES (
                :id, :user_id, :workflow_type, :current_state, :slots,
                :history, CURRENT_TIMESTAMP, TRUE
            )
        """), {
            "id": str(session_id),
            "user_id": user_id,
            "workflow_type": workflow_type.value,
            "current_state": initial_state,
            "slots": "{}",
            "history": "[]",
        })
        self.db.commit()

        # Create session object
        session = VoiceWorkflowSession(
            id=session_id,
            user_id=user_id,
            workflow_type=workflow_type,
            current_state=initial_state,
            slots={},
            conversation_history=[],
            is_active=True,
        )

        # Load initial context (applicants, realtors, etc.)
        if workflow_type == WorkflowType.PRE_APPROVAL_LETTER:
            await self._load_pre_approval_context(session, user_id)

        # Generate initial response
        response = await self._process_state_entry(session)

        return session, response

    async def get_session(self, session_id: UUID) -> Optional[VoiceWorkflowSession]:
        """Get an active workflow session by ID."""
        result = self.db.execute(text("""
            SELECT id, user_id, workflow_type, current_state, slots,
                   conversation_history, started_at, updated_at, is_active
            FROM voice_workflow_sessions
            WHERE id = :id AND is_active = TRUE
        """), {"id": str(session_id)}).fetchone()

        if not result:
            return None

        return VoiceWorkflowSession(
            id=UUID(result[0]),
            user_id=result[1],
            workflow_type=WorkflowType(result[2]),
            current_state=result[3],
            slots=result[4] if isinstance(result[4], dict) else json.loads(result[4] or "{}"),
            conversation_history=[
                ConversationTurn(**t) for t in
                (result[5] if isinstance(result[5], list) else json.loads(result[5] or "[]"))
            ],
            started_at=result[6],
            updated_at=result[7],
            is_active=result[8],
        )

    async def get_active_session(self, user_id: int) -> Optional[VoiceWorkflowSession]:
        """Get the user's active workflow session if any."""
        result = self.db.execute(text("""
            SELECT id FROM voice_workflow_sessions
            WHERE user_id = :user_id AND is_active = TRUE
            ORDER BY started_at DESC
            LIMIT 1
        """), {"user_id": user_id}).fetchone()

        if result:
            return await self.get_session(UUID(result[0]))
        return None

    async def cancel_session(self, session_id: UUID) -> None:
        """Cancel a workflow session."""
        self.db.execute(text("""
            UPDATE voice_workflow_sessions
            SET is_active = FALSE,
                current_state = 'cancelled',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": str(session_id)})
        self.db.commit()

    def _save_session(self, session: VoiceWorkflowSession) -> None:
        """Save session state to database."""
        history_json = json.dumps([
            {
                "role": t.role,
                "content": t.content,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "intent": t.intent.value if t.intent else None,
                "slots_extracted": t.slots_extracted,
            }
            for t in session.conversation_history
        ])

        self.db.execute(text("""
            UPDATE voice_workflow_sessions
            SET current_state = :state,
                slots = :slots,
                conversation_history = :history,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {
            "id": str(session.id),
            "state": session.current_state,
            "slots": json.dumps(session.slots),
            "history": history_json,
        })
        self.db.commit()

    # =========================================================================
    # WORKFLOW PROCESSING
    # =========================================================================

    async def process_user_input(
        self,
        session: VoiceWorkflowSession,
        transcript: str,
        audio_duration_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process user voice input and advance the workflow.

        Args:
            session: The active workflow session
            transcript: Transcribed user speech
            audio_duration_ms: Duration of audio in milliseconds

        Returns:
            Response dict with text, audio, state changes, etc.
        """
        # Record user turn
        user_turn = ConversationTurn(
            role="user",
            content=transcript,
            audio_duration_ms=audio_duration_ms,
        )
        session.conversation_history.append(user_turn)

        # Get available options for current state
        options = await self._get_current_state_options(session)

        # Extract slots and intent using Claude
        extraction = await self.slot_extractor.extract_slots(
            transcript=transcript,
            workflow_type=session.workflow_type,
            current_state=session.current_state,
            current_slots=session.slots,
            available_options=options,
        )

        # Update user turn with extraction results
        user_turn.intent = extraction.intent
        user_turn.slots_extracted = extraction.extracted_slots

        # Process based on intent
        if extraction.intent == UserIntent.CANCEL:
            return await self._handle_cancel(session)

        if extraction.intent == UserIntent.HELP:
            return await self._handle_help(session)

        if extraction.intent == UserIntent.GO_BACK:
            return await self._handle_go_back(session)

        # Process state-specific logic
        if session.workflow_type == WorkflowType.PRE_APPROVAL_LETTER:
            response = await self._process_pre_approval_input(session, extraction, options)
        else:
            response = {"text": "This workflow type is not yet supported.", "audio_base64": None}

        # Save session state
        self._save_session(session)

        return response

    # =========================================================================
    # PRE-APPROVAL LETTER WORKFLOW
    # =========================================================================

    async def _process_pre_approval_input(
        self,
        session: VoiceWorkflowSession,
        extraction: SlotExtractionResult,
        options: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Process input for pre-approval letter workflow."""

        state = PreApprovalWorkflowState(session.current_state)

        # Handle state-specific processing
        if state == PreApprovalWorkflowState.SELECT_APPLICANT:
            return await self._handle_select_applicant(session, extraction, options)

        elif state == PreApprovalWorkflowState.REVIEW_TERMS:
            return await self._handle_review_terms(session, extraction)

        elif state == PreApprovalWorkflowState.ADD_PROPERTY:
            return await self._handle_add_property(session, extraction)

        elif state == PreApprovalWorkflowState.SELECT_REALTOR:
            return await self._handle_select_realtor(session, extraction, options)

        elif state == PreApprovalWorkflowState.FINAL_CONFIRMATION:
            return await self._handle_final_confirmation(session, extraction)

        else:
            return await self._generate_state_response(session)

    async def _handle_select_applicant(
        self,
        session: VoiceWorkflowSession,
        extraction: SlotExtractionResult,
        options: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Handle applicant selection state."""

        if extraction.intent == UserIntent.CONFIRM and len(options or []) == 1:
            # Single applicant confirmed
            applicant = options[0]
            session.slots.update({
                "applicant_id": applicant["id"],
                "applicant_name": applicant["name"],
                "loan_type": applicant.get("loan_type"),
                "pre_approved_amount": applicant.get("loan_amount"),
                "interest_rate": applicant.get("interest_rate"),
                "loan_term": applicant.get("loan_term", 30),
            })
            session.current_state = PreApprovalWorkflowState.REVIEW_TERMS.value
            return await self._generate_state_response(session)

        if extraction.matched_option_index is not None and options:
            # User selected by name/number
            if 0 <= extraction.matched_option_index < len(options):
                applicant = options[extraction.matched_option_index]
                session.slots.update({
                    "applicant_id": applicant["id"],
                    "applicant_name": applicant["name"],
                    "loan_type": applicant.get("loan_type"),
                    "pre_approved_amount": applicant.get("loan_amount"),
                    "interest_rate": applicant.get("interest_rate"),
                    "loan_term": applicant.get("loan_term", 30),
                })
                session.current_state = PreApprovalWorkflowState.REVIEW_TERMS.value
                return await self._generate_state_response(session)

        # Need clarification
        if extraction.needs_clarification:
            response = await self.response_generator.generate_response_with_audio(
                workflow_type=session.workflow_type,
                current_state=session.current_state,
                slots=session.slots,
                available_options=options,
                error_message=extraction.clarification_question,
            )
        else:
            response = await self.response_generator.generate_response_with_audio(
                workflow_type=session.workflow_type,
                current_state=session.current_state,
                slots=session.slots,
                available_options=options,
            )

        self._add_assistant_turn(session, response["text"])
        return response

    async def _handle_review_terms(
        self,
        session: VoiceWorkflowSession,
        extraction: SlotExtractionResult,
    ) -> Dict[str, Any]:
        """Handle loan terms review state."""

        if extraction.intent == UserIntent.CONFIRM:
            # User confirmed terms, move to property step
            session.current_state = PreApprovalWorkflowState.ADD_PROPERTY.value
            return await self._generate_state_response(session)

        if extraction.intent == UserIntent.MODIFY:
            # Check for amount modification
            if "pre_approved_amount" in extraction.extracted_slots:
                new_amount = extraction.extracted_slots["pre_approved_amount"]
                session.slots["pre_approved_amount"] = new_amount
                # Confirm the change and stay in review
                response = await self.response_generator.generate_response_with_audio(
                    workflow_type=session.workflow_type,
                    current_state=session.current_state,
                    slots=session.slots,
                )
                self._add_assistant_turn(session, response["text"])
                return response

        # Default: repeat the terms
        return await self._generate_state_response(session)

    async def _handle_add_property(
        self,
        session: VoiceWorkflowSession,
        extraction: SlotExtractionResult,
    ) -> Dict[str, Any]:
        """Handle property address step."""

        if extraction.intent in [UserIntent.SKIP, UserIntent.CONFIRM]:
            # Check if user provided "no" type response
            if extraction.intent == UserIntent.SKIP:
                session.current_state = PreApprovalWorkflowState.SELECT_REALTOR.value
                await self._load_realtor_options(session)
                return await self._generate_state_response(session)

        # Check for address in extracted slots
        if "property_address" in extraction.extracted_slots:
            session.slots["property_address"] = extraction.extracted_slots["property_address"]
            session.current_state = PreApprovalWorkflowState.SELECT_REALTOR.value
            await self._load_realtor_options(session)
            return await self._generate_state_response(session)

        # Check if user said yes (wants to add address)
        if extraction.intent == UserIntent.CONFIRM:
            # Stay in same state, prompt for address
            text = "What's the property address?"
            audio = await self.response_generator.text_to_speech(text)
            response = {"text": text, "audio_base64": None}
            if audio:
                import base64
                response["audio_base64"] = base64.b64encode(audio).decode()
            self._add_assistant_turn(session, text)
            return response

        # Default: ask again
        return await self._generate_state_response(session)

    async def _handle_select_realtor(
        self,
        session: VoiceWorkflowSession,
        extraction: SlotExtractionResult,
        options: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Handle realtor selection state."""

        if extraction.matched_option_index is not None and options:
            if 0 <= extraction.matched_option_index < len(options):
                realtor = options[extraction.matched_option_index]
                session.slots.update({
                    "realtor_id": realtor.get("id"),
                    "realtor_name": realtor.get("name"),
                    "realtor_email": realtor.get("email"),
                    "realtor_company": realtor.get("company"),
                })
                session.current_state = PreApprovalWorkflowState.FINAL_CONFIRMATION.value
                return await self._generate_state_response(session)

        # Check for new realtor info in extracted slots
        if extraction.extracted_slots.get("realtor_name"):
            session.slots["realtor_name"] = extraction.extracted_slots["realtor_name"]
            if extraction.extracted_slots.get("realtor_email"):
                session.slots["realtor_email"] = extraction.extracted_slots["realtor_email"]
            session.current_state = PreApprovalWorkflowState.FINAL_CONFIRMATION.value
            return await self._generate_state_response(session)

        # Need more info
        return await self._generate_state_response(session)

    async def _handle_final_confirmation(
        self,
        session: VoiceWorkflowSession,
        extraction: SlotExtractionResult,
    ) -> Dict[str, Any]:
        """Handle final confirmation before sending."""

        if extraction.intent == UserIntent.CONFIRM:
            # Execute the workflow!
            session.current_state = PreApprovalWorkflowState.EXECUTING.value
            result = await self._execute_pre_approval_letter(session)

            if result.success:
                session.current_state = PreApprovalWorkflowState.COMPLETED.value
                session.is_active = False
            else:
                # Return to confirmation with error
                session.current_state = PreApprovalWorkflowState.FINAL_CONFIRMATION.value
                return await self.response_generator.generate_response_with_audio(
                    workflow_type=session.workflow_type,
                    current_state=session.current_state,
                    slots=session.slots,
                    error_message=result.error,
                )

            # Save execution result
            self.db.execute(text("""
                UPDATE voice_workflow_sessions
                SET completed_at = CURRENT_TIMESTAMP,
                    execution_result = :result,
                    is_active = FALSE
                WHERE id = :id
            """), {
                "id": str(session.id),
                "result": json.dumps(result.result_data) if result.result_data else None,
            })
            self.db.commit()

            return await self._generate_state_response(session)

        if extraction.intent == UserIntent.CANCEL:
            return await self._handle_cancel(session)

        # Go back to modify something
        if extraction.intent == UserIntent.MODIFY:
            # Determine what they want to modify and go to that state
            if "amount" in str(extraction.extracted_slots).lower():
                session.current_state = PreApprovalWorkflowState.REVIEW_TERMS.value
            return await self._generate_state_response(session)

        # Repeat confirmation
        return await self._generate_state_response(session)

    async def _execute_pre_approval_letter(
        self,
        session: VoiceWorkflowSession,
    ) -> WorkflowExecutionResult:
        """Execute the pre-approval letter generation and sending."""
        try:
            from services.realtor_letter_service import LetterGenerationService

            # Get user's organization
            user_result = self.db.execute(text("""
                SELECT organization_id FROM users WHERE id = :user_id
            """), {"user_id": session.user_id}).fetchone()

            if not user_result:
                return WorkflowExecutionResult(
                    success=False,
                    workflow_type=session.workflow_type,
                    error="User organization not found",
                )

            org_id = user_result[0] or 1  # Default to 1 if null

            # Get loan ID from applicant
            applicant_id = session.slots.get("applicant_id")
            loan_result = self.db.execute(text("""
                SELECT l.id FROM loans l
                JOIN applicants a ON a.loan_id = l.id
                WHERE a.id = :applicant_id
                LIMIT 1
            """), {"applicant_id": applicant_id}).fetchone()

            if not loan_result:
                # Try to get loan directly if applicant table doesn't exist
                loan_result = self.db.execute(text("""
                    SELECT id FROM loans WHERE id = :applicant_id LIMIT 1
                """), {"applicant_id": applicant_id}).fetchone()

            if not loan_result:
                return WorkflowExecutionResult(
                    success=False,
                    workflow_type=session.workflow_type,
                    error="Loan not found for applicant",
                )

            loan_id = loan_result[0]

            # Generate the letter
            letter_service = LetterGenerationService(self.db)

            variables = {
                "borrower_name": session.slots.get("applicant_name"),
                "prequal_amount": f"{session.slots.get('pre_approved_amount', 0):,.0f}",
                "loan_type": session.slots.get("loan_type", "conventional"),
                "interest_rate": session.slots.get("interest_rate"),
            }

            result = letter_service.generate_letter(
                organization_id=org_id,
                loan_id=loan_id,
                letter_type="preapproval",
                variables=variables,
                generated_by_user=session.user_id,
                property_address=session.slots.get("property_address"),
            )

            if not result.get("success"):
                return WorkflowExecutionResult(
                    success=False,
                    workflow_type=session.workflow_type,
                    error=result.get("error", "Letter generation failed"),
                )

            # Send email to realtor
            realtor_email = session.slots.get("realtor_email")
            email_sent = False

            if realtor_email:
                try:
                    from services.notification_service import NotificationService
                    notif_service = NotificationService()

                    await notif_service.send_email(
                        to_email=realtor_email,
                        subject=f"Pre-Approval Letter for {session.slots.get('applicant_name')}",
                        body=f"""
Please find attached the pre-approval letter for {session.slots.get('applicant_name')}.

Pre-approved Amount: ${session.slots.get('pre_approved_amount', 0):,.0f}
Loan Type: {session.slots.get('loan_type', 'Conventional').title()}

View the letter here: {result.get('share_url')}
                        """.strip(),
                    )
                    email_sent = True
                except SQLAlchemyError as e:
                    logger.warning(f"Failed to send email: {e}")

            return WorkflowExecutionResult(
                success=True,
                workflow_type=session.workflow_type,
                result_data={
                    "letter_id": result.get("letter_id"),
                    "share_url": result.get("share_url"),
                    "email_sent": email_sent,
                    "sent_to": realtor_email,
                },
            )

        except SQLAlchemyError as e:
            logger.error(f"Pre-approval letter execution error: {e}")
            return WorkflowExecutionResult(
                success=False,
                workflow_type=session.workflow_type,
                error=str(e),
            )

    # =========================================================================
    # STATE HELPERS
    # =========================================================================

    async def _process_state_entry(
        self,
        session: VoiceWorkflowSession,
    ) -> Dict[str, Any]:
        """Generate response when entering a new state."""
        # For pre-approval, move from intent_detected to select_applicant
        if (session.workflow_type == WorkflowType.PRE_APPROVAL_LETTER and
                session.current_state == PreApprovalWorkflowState.INTENT_DETECTED.value):
            session.current_state = PreApprovalWorkflowState.SELECT_APPLICANT.value
            self._save_session(session)

        return await self._generate_state_response(session)

    async def _generate_state_response(
        self,
        session: VoiceWorkflowSession,
    ) -> Dict[str, Any]:
        """Generate response for current state."""
        options = await self._get_current_state_options(session)

        response = await self.response_generator.generate_response_with_audio(
            workflow_type=session.workflow_type,
            current_state=session.current_state,
            slots=session.slots,
            available_options=options,
        )

        self._add_assistant_turn(session, response["text"])
        self._save_session(session)

        return {
            **response,
            "current_state": session.current_state,
            "slots": session.slots,
            "options": options,
        }

    async def _get_current_state_options(
        self,
        session: VoiceWorkflowSession,
    ) -> Optional[List[Dict[str, Any]]]:
        """Get available options for the current state."""
        if session.workflow_type == WorkflowType.PRE_APPROVAL_LETTER:
            state = session.current_state

            if state == PreApprovalWorkflowState.SELECT_APPLICANT.value:
                return session.available_applicants

            if state == PreApprovalWorkflowState.SELECT_REALTOR.value:
                return session.available_realtors

        return None

    async def _load_pre_approval_context(
        self,
        session: VoiceWorkflowSession,
        user_id: int,
    ) -> None:
        """Load applicants for the loan officer."""
        # Get active loans/applicants for this LO
        # Note: loans table uses 'amount', 'program', 'rate', 'stage' columns
        # LoanStage enum values are capitalized (e.g., 'Funded', 'Closing')
        results = self.db.execute(text("""
            SELECT
                l.id,
                l.borrower_name,
                l.amount,
                l.program,
                l.rate,
                l.stage
            FROM loans l
            WHERE l.loan_officer_id = :user_id
                AND l.stage NOT IN ('Funded')
            ORDER BY l.updated_at DESC
            LIMIT 10
        """), {"user_id": user_id}).fetchall()

        session.available_applicants = [
            {
                "id": r[0],
                "name": r[1],
                "loan_amount": float(r[2]) if r[2] else 0,
                "loan_type": r[3] or "conventional",
                "interest_rate": float(r[4]) if r[4] else None,
                "status": r[5],
                "voice_description": f"{r[1]} with a ${float(r[2] or 0):,.0f} {r[3] or 'loan'}",
            }
            for r in results
        ]

    async def _load_realtor_options(
        self,
        session: VoiceWorkflowSession,
    ) -> None:
        """Load realtor contacts for selection."""
        # Get realtors the LO works with
        results = self.db.execute(text("""
            SELECT DISTINCT
                rp.id,
                rp.first_name || ' ' || COALESCE(rp.last_name, '') as name,
                rp.email,
                rp.company_name
            FROM referral_partners rp
            WHERE rp.partner_type = 'realtor'
                AND rp.is_active = TRUE
            ORDER BY rp.first_name
            LIMIT 10
        """)).fetchall()

        session.available_realtors = [
            {
                "id": r[0],
                "name": r[1].strip(),
                "email": r[2],
                "company": r[3],
                "voice_description": f"{r[1].strip()}" + (f" at {r[3]}" if r[3] else ""),
            }
            for r in results
        ]

    def _add_assistant_turn(self, session: VoiceWorkflowSession, text: str) -> None:
        """Add assistant response to conversation history."""
        session.conversation_history.append(ConversationTurn(
            role="assistant",
            content=text,
        ))

    async def _handle_cancel(self, session: VoiceWorkflowSession) -> Dict[str, Any]:
        """Handle workflow cancellation."""
        session.current_state = PreApprovalWorkflowState.CANCELLED.value
        session.is_active = False
        await self.cancel_session(session.id)

        response = await self.response_generator.generate_response_with_audio(
            workflow_type=session.workflow_type,
            current_state=session.current_state,
            slots=session.slots,
        )
        return response

    async def _handle_help(self, session: VoiceWorkflowSession) -> Dict[str, Any]:
        """Handle help request."""
        # Generate contextual help based on current state
        help_text = self._get_help_text(session)

        audio = await self.response_generator.text_to_speech(help_text)
        response = {"text": help_text, "audio_base64": None}
        if audio:
            import base64
            response["audio_base64"] = base64.b64encode(audio).decode()

        self._add_assistant_turn(session, help_text)
        return response

    async def _handle_go_back(self, session: VoiceWorkflowSession) -> Dict[str, Any]:
        """Handle go back request."""
        if session.workflow_type == WorkflowType.PRE_APPROVAL_LETTER:
            state = PreApprovalWorkflowState(session.current_state)

            # Define state order
            state_order = [
                PreApprovalWorkflowState.SELECT_APPLICANT,
                PreApprovalWorkflowState.REVIEW_TERMS,
                PreApprovalWorkflowState.ADD_PROPERTY,
                PreApprovalWorkflowState.SELECT_REALTOR,
                PreApprovalWorkflowState.FINAL_CONFIRMATION,
            ]

            # Find current and go to previous
            try:
                current_idx = state_order.index(state)
                if current_idx > 0:
                    session.current_state = state_order[current_idx - 1].value
            except ValueError:
                pass

        return await self._generate_state_response(session)

    def _get_help_text(self, session: VoiceWorkflowSession) -> str:
        """Get contextual help text for current state."""
        if session.workflow_type == WorkflowType.PRE_APPROVAL_LETTER:
            state = session.current_state

            if state == PreApprovalWorkflowState.SELECT_APPLICANT.value:
                return "I'm showing you your active applicants. Say the name of the person who needs the pre-approval letter, or say 'cancel' to stop."

            if state == PreApprovalWorkflowState.REVIEW_TERMS.value:
                return "I'm reviewing the loan terms. You can say 'confirm' to accept them, or tell me what you'd like to change. For example, 'change the amount to 500 thousand'."

            if state == PreApprovalWorkflowState.ADD_PROPERTY.value:
                return "Would you like to include a property address on the letter? Say 'yes' and then the address, or 'skip' to continue without one."

            if state == PreApprovalWorkflowState.SELECT_REALTOR.value:
                return "Tell me which realtor should receive this letter. You can say their name, or give me their email address."

            if state == PreApprovalWorkflowState.FINAL_CONFIRMATION.value:
                return "I've summarized the letter details. Say 'yes' or 'send it' to send the letter, or 'cancel' to stop."

        return "I'm here to help you complete this task. Tell me what you'd like to do, or say 'cancel' to stop."


    # =========================================================================
    # STALE SESSION REAPER  (CQ-006)
    # =========================================================================

    def reap_stale_sessions(self, max_age_hours: int = 2) -> int:
        """
        Find active voice_workflow_sessions older than *max_age_hours* and
        mark them as expired.  Returns the count of reaped sessions.

        This is the safety net for sessions that survived a WebSocket
        disconnect without proper cleanup (e.g. server crash, network
        partition, or OOM kill).
        """
        result = self.db.execute(text("""
            UPDATE voice_workflow_sessions
            SET is_active = FALSE,
                current_state = 'expired',
                updated_at = CURRENT_TIMESTAMP
            WHERE is_active = TRUE
              AND started_at < CURRENT_TIMESTAMP - MAKE_INTERVAL(hours => :max_age_hours)
            RETURNING id, user_id, current_state
        """), {"max_age_hours": max_age_hours})

        reaped_rows = result.fetchall()
        self.db.commit()

        for row in reaped_rows:
            logger.info(
                "CQ-006 stale session reaped: session_id=%s user_id=%s prior_state=%s max_age_hours=%d",
                row[0], row[1], row[2], max_age_hours,
            )

        return len(reaped_rows)

    def reap_stale_queue_entries(self, max_age_minutes: int = 30) -> int:
        """
        Find queue_entries stuck in 'waiting' status longer than
        *max_age_minutes* and mark them as abandoned.  Returns count.
        """
        result = self.db.execute(text("""
            UPDATE queue_entries
            SET status = 'abandoned',
                actual_wait_seconds = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - entered_at))::int,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'waiting'
              AND entered_at < CURRENT_TIMESTAMP - MAKE_INTERVAL(mins => :max_age_minutes)
            RETURNING id, queue_id, call_sid
        """), {"max_age_minutes": max_age_minutes})

        reaped_rows = result.fetchall()
        self.db.commit()

        for row in reaped_rows:
            logger.info(
                "CQ-006 stale queue entry reaped: entry_id=%s queue_id=%s call_sid=%s max_age_minutes=%d",
                row[0], row[1], row[2], max_age_minutes,
            )

        return len(reaped_rows)


# Singleton instance
_workflow_service: Optional[VoiceWorkflowService] = None


def get_workflow_service(db: Session) -> VoiceWorkflowService:
    """Get or create the workflow service."""
    return VoiceWorkflowService(db)
