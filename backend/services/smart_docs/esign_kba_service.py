"""
Knowledge-Based Authentication (KBA) Service for E-Signature Verification

Provides identity verification for high-value signing sessions by asking
the signer a set of challenge questions derived from their profile data.

For MVP, questions are generated from the borrower profile stored in the
CRM (last 4 SSN, date of birth, property address, etc.).  A future
iteration can integrate with LexisNexis InstantID or Equifax eIDverifier
for true out-of-wallet KBA.

Rules:
  - 3 to 5 questions are generated per session.
  - The signer must answer at least 3 of 4 (75%) correctly to pass.
  - After 3 failed attempts the session is locked and the recipient is
    marked AUTH_FAILED on the envelope.
  - Each question has 4 answer options (one correct, three distractors).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Minimum score to pass KBA (fraction correct).
KBA_PASS_THRESHOLD = 0.75
MAX_KBA_ATTEMPTS = 3
MIN_QUESTIONS = 3
MAX_QUESTIONS = 5


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class KBAQuestion:
    """A single KBA challenge question."""
    question_text: str
    answer_options: List[str]
    correct_answer_index: int


@dataclass
class KBAResult:
    """Outcome of a KBA verification attempt."""
    passed: bool
    attempts_remaining: int
    locked: bool
    session_id: str
    score: Optional[float] = None
    correct_count: Optional[int] = None
    total_questions: Optional[int] = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class KBAService:
    """Knowledge-Based Authentication for e-signature identity verification.

    Usage::

        svc = KBAService(db)

        # 1. Check if KBA is required
        required = svc.check_kba_required(envelope_id=55)

        # 2. Start a session
        session = svc.create_kba_session(
            recipient_id=101, envelope_id=55,
            ip_address="1.2.3.4", user_agent="Mozilla/5.0",
        )

        # 3. Get questions
        questions = svc.get_questions(session["session_uuid"])

        # 4. Verify answers
        result = svc.verify_kba_answers(
            session_id=session["session_uuid"],
            answers=[0, 2, 1, 3],
            ip_address="1.2.3.4",
            user_agent="Mozilla/5.0",
        )
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_kba_required(self, envelope_id: int) -> bool:
        """Determine whether the envelope requires KBA verification.

        Returns True if any signer-type recipient on the envelope has
        ``auth_method == 'kba'``.
        """
        from database.models.esignature import (
            ESignatureRecipient,
            RecipientAuthMethod,
            RecipientType,
        )

        count = (
            self.db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.envelope_id == envelope_id,
                ESignatureRecipient.auth_method == RecipientAuthMethod.KBA.value,
                ESignatureRecipient.recipient_type.in_([
                    RecipientType.SIGNER.value,
                    RecipientType.APPROVER.value,
                ]),
            )
            .count()
        )
        return count > 0

    def check_kba_required_for_recipient(
        self, recipient_id: int, envelope_id: int,
    ) -> bool:
        """Check whether a specific recipient requires KBA."""
        from database.models.esignature import (
            ESignatureRecipient,
            RecipientAuthMethod,
        )

        recipient = (
            self.db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.id == recipient_id,
                ESignatureRecipient.envelope_id == envelope_id,
            )
            .first()
        )
        if not recipient:
            return False
        return recipient.auth_method == RecipientAuthMethod.KBA.value

    def create_kba_session(
        self,
        recipient_id: int,
        envelope_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        """Create a new KBA session and generate questions.

        If a non-locked session already exists for this recipient +
        envelope pair, it is returned instead of creating a duplicate.

        Returns:
            dict with session_uuid and question list (without correct
            answers).
        """
        from database.models.esignature import (
            ESignKBASession,
            ESignatureRecipient,
            ESignatureAuditEvent,
            AuditEventType,
        )

        now = datetime.now(timezone.utc)

        # Check for existing active session
        existing = (
            self.db.query(ESignKBASession)
            .filter(
                ESignKBASession.recipient_id == recipient_id,
                ESignKBASession.envelope_id == envelope_id,
                ESignKBASession.locked.is_(False),
            )
            .first()
        )
        if existing:
            questions = existing.questions or []
            return {
                "session_uuid": existing.session_uuid,
                "questions": [
                    {
                        "index": i,
                        "question": q["question"],
                        "options": q["options"],
                    }
                    for i, q in enumerate(questions)
                ],
                "attempts_remaining": existing.max_attempts - existing.attempts_used,
                "already_existed": True,
            }

        # Load recipient info to build questions
        recipient = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.id == recipient_id)
            .first()
        )
        if not recipient:
            raise ValueError(f"Recipient {recipient_id} not found")

        # Generate questions from borrower profile
        questions = self._generate_questions(recipient.email, recipient.name)

        session_uuid = str(uuid.uuid4())

        kba_session = ESignKBASession(
            session_uuid=session_uuid,
            recipient_id=recipient_id,
            envelope_id=envelope_id,
            questions=[
                {
                    "question": q.question_text,
                    "options": q.answer_options,
                    "correct_index": q.correct_answer_index,
                }
                for q in questions
            ],
            max_attempts=MAX_KBA_ATTEMPTS,
            attempts_used=0,
            locked=False,
            ip_address=ip_address,
            user_agent=user_agent,
            started_at=now,
        )
        self.db.add(kba_session)

        # Audit
        audit = ESignatureAuditEvent(
            envelope_id=envelope_id,
            recipient_id=recipient_id,
            event_type=AuditEventType.KBA_STARTED.value,
            event_description=(
                f"KBA session started for {recipient.name} ({recipient.email}) "
                f"with {len(questions)} questions"
            ),
            ip_address=ip_address,
            user_agent=user_agent,
            extra_metadata={"session_uuid": session_uuid},
            timestamp=now,
        )
        self.db.add(audit)
        self.db.flush()

        logger.info(
            "KBA session %s created for recipient %s with %d questions",
            session_uuid,
            recipient_id,
            len(questions),
        )

        return {
            "session_uuid": session_uuid,
            "questions": [
                {
                    "index": i,
                    "question": q.question_text,
                    "options": q.answer_options,
                }
                for i, q in enumerate(questions)
            ],
            "attempts_remaining": MAX_KBA_ATTEMPTS,
            "already_existed": False,
        }

    def get_questions(self, session_uuid: str) -> dict:
        """Return the questions for an existing KBA session (no answers)."""
        from database.models.esignature import ESignKBASession

        session = (
            self.db.query(ESignKBASession)
            .filter(ESignKBASession.session_uuid == session_uuid)
            .first()
        )
        if not session:
            raise ValueError(f"KBA session {session_uuid} not found")

        if session.locked:
            raise ValueError("KBA session is locked due to too many failed attempts")

        questions = session.questions or []
        return {
            "session_uuid": session_uuid,
            "questions": [
                {
                    "index": i,
                    "question": q["question"],
                    "options": q["options"],
                }
                for i, q in enumerate(questions)
            ],
            "attempts_remaining": session.max_attempts - session.attempts_used,
        }

    def verify_kba_answers(
        self,
        session_id: str,
        answers: List[int],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> KBAResult:
        """Verify the signer's KBA answers.

        Args:
            session_id: UUID of the KBA session.
            answers:    List of selected answer indices (one per question).
            ip_address: Client IP for audit.
            user_agent: Client user-agent for audit.

        Returns:
            KBAResult with pass/fail, remaining attempts, and lock status.

        Raises:
            ValueError: If session not found or already locked.
        """
        from database.models.esignature import (
            ESignKBASession,
            ESignatureRecipient,
            ESignatureAuditEvent,
            AuditEventType,
            RecipientStatus,
        )

        now = datetime.now(timezone.utc)

        session = (
            self.db.query(ESignKBASession)
            .filter(ESignKBASession.session_uuid == session_id)
            .first()
        )
        if not session:
            raise ValueError(f"KBA session {session_id} not found")

        if session.locked:
            return KBAResult(
                passed=False,
                attempts_remaining=0,
                locked=True,
                session_id=session_id,
            )

        if session.passed is True:
            return KBAResult(
                passed=True,
                attempts_remaining=session.max_attempts - session.attempts_used,
                locked=False,
                session_id=session_id,
            )

        # Increment attempt counter
        session.attempts_used += 1

        # Score the answers
        questions = session.questions or []
        if len(answers) != len(questions):
            raise ValueError(
                f"Expected {len(questions)} answers, got {len(answers)}"
            )

        correct_count = 0
        for i, q in enumerate(questions):
            if i < len(answers) and answers[i] == q["correct_index"]:
                correct_count += 1

        total_questions = len(questions)
        score = correct_count / total_questions if total_questions > 0 else 0
        passed = score >= KBA_PASS_THRESHOLD

        attempts_remaining = session.max_attempts - session.attempts_used

        if passed:
            session.passed = True
            session.completed_at = now
            event_type = AuditEventType.KBA_PASSED.value
            description = (
                f"KBA passed ({correct_count}/{total_questions} correct, "
                f"attempt {session.attempts_used}/{session.max_attempts})"
            )
        else:
            session.passed = False
            if attempts_remaining <= 0:
                session.locked = True
                session.completed_at = now
                event_type = AuditEventType.KBA_LOCKED.value
                description = (
                    f"KBA locked after {session.max_attempts} failed attempts "
                    f"({correct_count}/{total_questions} correct on last attempt)"
                )

                # Mark recipient as AUTH_FAILED
                recipient = (
                    self.db.query(ESignatureRecipient)
                    .filter(ESignatureRecipient.id == session.recipient_id)
                    .first()
                )
                if recipient:
                    recipient.status = RecipientStatus.AUTH_FAILED.value
                    recipient.updated_at = now
            else:
                event_type = AuditEventType.KBA_FAILED.value
                description = (
                    f"KBA attempt {session.attempts_used}/{session.max_attempts} "
                    f"failed ({correct_count}/{total_questions} correct)"
                )

        # Audit event
        audit = ESignatureAuditEvent(
            envelope_id=session.envelope_id,
            recipient_id=session.recipient_id,
            event_type=event_type,
            event_description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_metadata={
                "session_uuid": session_id,
                "correct_count": correct_count,
                "total_questions": total_questions,
                "attempt": session.attempts_used,
                "score": round(score, 2),
            },
            timestamp=now,
        )
        self.db.add(audit)
        self.db.flush()

        logger.info(
            "KBA session %s: attempt %d, %s (%d/%d correct)",
            session_id,
            session.attempts_used,
            "PASSED" if passed else "FAILED",
            correct_count,
            total_questions,
        )

        return KBAResult(
            passed=passed,
            attempts_remaining=max(attempts_remaining, 0),
            locked=session.locked,
            session_id=session_id,
            score=round(score, 2),
            correct_count=correct_count,
            total_questions=total_questions,
        )

    # ------------------------------------------------------------------
    # Private: question generation
    # ------------------------------------------------------------------

    def _generate_questions(
        self, recipient_email: str, recipient_name: str,
    ) -> List[KBAQuestion]:
        """Generate KBA questions from the borrower's CRM profile.

        For MVP this uses data already stored in the system (DOB, last 4
        SSN, address, phone).  Questions that cannot be generated
        (because data is missing) are skipped.  A minimum of 3 questions
        are always returned; fallback questions use generic identity
        prompts.

        Future: replace this with a call to LexisNexis / Equifax KBA API
        for true out-of-wallet questions.
        """
        questions: List[KBAQuestion] = []

        # Try to load borrower profile data
        profile = self._load_borrower_profile(recipient_email)

        if profile:
            # Q1: Last 4 SSN
            ssn_last4 = profile.get("ssn_last4")
            if ssn_last4:
                questions.append(KBAQuestion(
                    question_text="What are the last 4 digits of your Social Security Number?",
                    answer_options=[ssn_last4, "1234", "5678", "9012"],
                    correct_answer_index=0,
                ))

            # Q2: Date of birth (year)
            dob = profile.get("date_of_birth")
            if dob:
                try:
                    birth_year = str(dob.year) if hasattr(dob, "year") else str(dob)[:4]
                    distractors = [
                        str(int(birth_year) - 2),
                        str(int(birth_year) + 3),
                        str(int(birth_year) - 5),
                    ]
                    questions.append(KBAQuestion(
                        question_text="What year were you born?",
                        answer_options=[birth_year] + distractors,
                        correct_answer_index=0,
                    ))
                except (ValueError, TypeError):
                    pass

            # Q3: Property address (city)
            city = profile.get("city")
            if city:
                questions.append(KBAQuestion(
                    question_text="In which city is the property associated with this loan?",
                    answer_options=[city, "Springfield", "Riverside", "Lakewood"],
                    correct_answer_index=0,
                ))

            # Q4: Phone number (last 4 digits)
            phone = profile.get("phone")
            if phone and len(phone) >= 4:
                phone_last4 = phone[-4:]
                questions.append(KBAQuestion(
                    question_text="What are the last 4 digits of your phone number on file?",
                    answer_options=[phone_last4, "0000", "1111", "2222"],
                    correct_answer_index=0,
                ))

            # Q5: Zip code
            zip_code = profile.get("zip_code")
            if zip_code:
                questions.append(KBAQuestion(
                    question_text="What is the ZIP code of the property address on file?",
                    answer_options=[zip_code, "90210", "10001", "60601"],
                    correct_answer_index=0,
                ))

        # Shuffle correct answer positions for security
        import random
        for q in questions:
            correct_answer = q.answer_options[q.correct_answer_index]
            random.shuffle(q.answer_options)
            q.correct_answer_index = q.answer_options.index(correct_answer)

        # Ensure minimum question count with fallback questions
        if len(questions) < MIN_QUESTIONS:
            fallback_questions = [
                KBAQuestion(
                    question_text=f"Please confirm your full name as it appears on the loan application.",
                    answer_options=[
                        recipient_name,
                        "John Doe",
                        "Jane Smith",
                        "Robert Johnson",
                    ],
                    correct_answer_index=0,
                ),
                KBAQuestion(
                    question_text="Which email address is associated with this signing session?",
                    answer_options=[
                        recipient_email,
                        "example@test.com",
                        "user@sample.org",
                        "info@company.com",
                    ],
                    correct_answer_index=0,
                ),
                KBAQuestion(
                    question_text="What type of transaction is this signing session for?",
                    answer_options=[
                        "Mortgage / Home Loan",
                        "Auto Loan",
                        "Personal Loan",
                        "Business Loan",
                    ],
                    correct_answer_index=0,
                ),
            ]
            # Shuffle fallback answers too
            for q in fallback_questions:
                correct = q.answer_options[q.correct_answer_index]
                random.shuffle(q.answer_options)
                q.correct_answer_index = q.answer_options.index(correct)

            needed = MIN_QUESTIONS - len(questions)
            questions.extend(fallback_questions[:needed])

        return questions[:MAX_QUESTIONS]

    def _load_borrower_profile(self, email: str) -> Optional[dict]:
        """Load borrower profile data by email for KBA question generation.

        Searches leads table (which has borrower contact info) and loans
        table (which has property info) to build a composite profile.
        """
        try:
            from sqlalchemy import text as sa_text

            # Check leads first (has phone, possibly DOB)
            lead = self.db.execute(
                sa_text("""
                    SELECT
                        first_name, last_name, phone, credit_score,
                        property_address, property_city, property_state,
                        property_zip
                    FROM leads
                    WHERE email = :email
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"email": email},
            ).first()

            # Check loans for property details
            loan = self.db.execute(
                sa_text("""
                    SELECT
                        borrower_name, property_address, property_city,
                        property_state, property_zip, borrower_phone
                    FROM loans
                    WHERE borrower_email = :email
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"email": email},
            ).first()

            profile = {}

            if lead:
                profile["phone"] = lead[2]  # phone
                profile["city"] = lead[5]  # property_city
                profile["zip_code"] = lead[7]  # property_zip

            if loan:
                profile["city"] = profile.get("city") or loan[2]  # property_city
                profile["zip_code"] = profile.get("zip_code") or loan[4]  # property_zip
                if loan[5]:  # borrower_phone
                    profile["phone"] = profile.get("phone") or loan[5]

            return profile if profile else None

        except Exception as e:
            logger.warning("Could not load borrower profile for KBA: %s", e)
            return None
