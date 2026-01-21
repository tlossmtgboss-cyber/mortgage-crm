"""
Call End Orchestrator - Event-Driven Pipeline for AI Junior Loan Officer

Implements the complete workflow when a call ends:
1. AI-JrLO Final Pass - Validate & score completeness
2. Application Finalization - Generate MISMO 3.4 file
3. Portal Creation - Auto-provision borrower portal
4. Borrower Notification - SMS + Email with portal link
5. Internal Distribution - Email team, create tasks for Production Assistants

This orchestrator connects existing components into a seamless workflow.
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid
import json

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Configuration
PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "https://portal.perenniaai.com")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Perennia AI")
COMPLETENESS_THRESHOLD = float(os.getenv("COMPLETENESS_THRESHOLD", "0.60"))


# =============================================================================
# COMPLETENESS SCORING
# =============================================================================

# Core fields required for loan application (with weights)
CORE_FIELDS = {
    # Identity (weight: 20%)
    "borrower.first_name": {"weight": 5, "category": "identity", "required": True},
    "borrower.last_name": {"weight": 5, "category": "identity", "required": True},
    "borrower.email": {"weight": 5, "category": "identity", "required": True},
    "borrower.phone": {"weight": 3, "category": "identity", "required": True},
    "borrower.ssn": {"weight": 2, "category": "identity", "required": False},

    # Property (weight: 20%)
    "property.address": {"weight": 8, "category": "property", "required": True},
    "property.type": {"weight": 4, "category": "property", "required": False},
    "property.occupancy": {"weight": 4, "category": "property", "required": False},
    "property.value": {"weight": 4, "category": "property", "required": False},

    # Loan (weight: 20%)
    "loan.purpose": {"weight": 8, "category": "loan", "required": True},
    "loan.amount": {"weight": 8, "category": "loan", "required": True},
    "loan.type": {"weight": 4, "category": "loan", "required": False},

    # Employment (weight: 15%)
    "employment.employer_name": {"weight": 5, "category": "employment", "required": False},
    "employment.type": {"weight": 4, "category": "employment", "required": False},
    "employment.years": {"weight": 3, "category": "employment", "required": False},
    "employment.income": {"weight": 3, "category": "employment", "required": False},

    # Income (weight: 15%)
    "income.base": {"weight": 8, "category": "income", "required": False},
    "income.other": {"weight": 4, "category": "income", "required": False},
    "income.total": {"weight": 3, "category": "income", "required": False},

    # Assets (weight: 10%)
    "assets.checking": {"weight": 3, "category": "assets", "required": False},
    "assets.savings": {"weight": 3, "category": "assets", "required": False},
    "assets.down_payment": {"weight": 4, "category": "assets", "required": False},
}

# Total possible weight
TOTAL_WEIGHT = sum(f["weight"] for f in CORE_FIELDS.values())


@dataclass
class CompletenessScore:
    """Application completeness scoring result."""
    score: float  # 0.0 to 1.0
    fields_captured: int
    fields_total: int
    missing_required: List[str]
    missing_optional: List[str]
    category_scores: Dict[str, float]
    meets_threshold: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "percentage": round(self.score * 100, 1),
            "fields_captured": self.fields_captured,
            "fields_total": self.fields_total,
            "missing_required": self.missing_required,
            "missing_optional": self.missing_optional,
            "category_scores": {k: round(v, 2) for k, v in self.category_scores.items()},
            "meets_threshold": self.meets_threshold,
            "threshold": COMPLETENESS_THRESHOLD,
        }


def calculate_completeness(captured_fields: List[Dict[str, Any]]) -> CompletenessScore:
    """
    Calculate application completeness score based on captured fields.

    Args:
        captured_fields: List of intake field dicts with 'field_path' and 'value'

    Returns:
        CompletenessScore with detailed breakdown
    """
    # Build set of captured field paths
    captured_paths = set()
    for field in captured_fields:
        path = field.get('field_path') or field.get('field_name', '')
        if path and field.get('value') is not None:
            # Normalize path
            path = path.lower().replace('.', '_').replace('borrower_', 'borrower.')
            path = path.replace('property_', 'property.').replace('loan_', 'loan.')
            path = path.replace('employment_', 'employment.').replace('income_', 'income.')
            path = path.replace('assets_', 'assets.')
            captured_paths.add(path)

    # Calculate weighted score
    weighted_score = 0
    fields_captured = 0
    missing_required = []
    missing_optional = []
    category_weights = {cat: {"captured": 0, "total": 0} for cat in ["identity", "property", "loan", "employment", "income", "assets"]}

    for field_path, field_info in CORE_FIELDS.items():
        weight = field_info["weight"]
        category = field_info["category"]
        is_required = field_info["required"]

        category_weights[category]["total"] += weight

        # Check if this field was captured (fuzzy match)
        is_captured = False
        for captured in captured_paths:
            if field_path in captured or captured in field_path:
                is_captured = True
                break

        if is_captured:
            weighted_score += weight
            fields_captured += 1
            category_weights[category]["captured"] += weight
        else:
            if is_required:
                missing_required.append(field_path)
            else:
                missing_optional.append(field_path)

    # Calculate category scores
    category_scores = {}
    for category, weights in category_weights.items():
        if weights["total"] > 0:
            category_scores[category] = weights["captured"] / weights["total"]
        else:
            category_scores[category] = 0.0

    # Calculate overall score
    score = weighted_score / TOTAL_WEIGHT if TOTAL_WEIGHT > 0 else 0

    return CompletenessScore(
        score=score,
        fields_captured=fields_captured,
        fields_total=len(CORE_FIELDS),
        missing_required=missing_required,
        missing_optional=missing_optional[:10],  # Limit to top 10
        category_scores=category_scores,
        meets_threshold=score >= COMPLETENESS_THRESHOLD,
    )


# =============================================================================
# CALL END ORCHESTRATOR
# =============================================================================

class CallEndOrchestrator:
    """
    Orchestrates the complete workflow when a call ends.

    Flow:
    1. Run AI agents (Scribe, Jr. LO, Underwriter)
    2. Calculate completeness score
    3. Generate MISMO 3.4 file if complete enough
    4. Create/update borrower portal
    5. Send borrower notification (SMS + Email)
    6. Create tasks for Production Assistants
    7. Email LO and Ops team
    """

    def __init__(self, db: Session):
        self.db = db
        self._notification_service = None
        self._mismo_generator = None
        self._portal_service = None

    @property
    def notification_service(self):
        if self._notification_service is None:
            from services.notification_service import NotificationService
            self._notification_service = NotificationService()
        return self._notification_service

    @property
    def mismo_generator(self):
        if self._mismo_generator is None:
            from services.mismo_generator import MISMOGenerator
            self._mismo_generator = MISMOGenerator()
        return self._mismo_generator

    @property
    def portal_service(self):
        if self._portal_service is None:
            from services.portal_lifecycle_service import PortalLifecycleService
            self._portal_service = PortalLifecycleService(self.db)
        return self._portal_service

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    async def process_call_end(
        self,
        session_id: str,
        user_id: str,
        auto_approve: bool = True,
    ) -> Dict[str, Any]:
        """
        Process end of call event - main entry point.

        Args:
            session_id: Call session ID
            user_id: User who initiated the call (LO)
            auto_approve: Whether to auto-approve low-risk artifacts

        Returns:
            Complete processing result
        """
        logger.info(f"Processing call end for session {session_id}")

        result = {
            "session_id": session_id,
            "started_at": datetime.utcnow().isoformat(),
            "steps": {},
            "errors": [],
        }

        try:
            # Step 1: Get session and run agents
            session = await self._get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            # Run AI agents if not already done
            if session.get('status') not in ('review_pending', 'completed'):
                from .orchestrator_service import CallMonitoringOrchestrator
                orchestrator = CallMonitoringOrchestrator(self.db)
                agent_result = await orchestrator.run_agents(session_id)
                result["steps"]["agents"] = agent_result

            # Step 2: Get intake fields and calculate completeness
            intake_fields = await self._get_intake_fields(session_id)
            completeness = calculate_completeness(intake_fields)
            result["steps"]["completeness"] = completeness.to_dict()

            # Update session with completeness score
            await self._update_session_completeness(session_id, completeness)

            # Step 3: Get borrower info
            borrower = await self._get_or_create_borrower(session, intake_fields)
            result["steps"]["borrower"] = borrower

            # Step 4: Create/update loan application
            loan = await self._get_or_create_loan(session, borrower, intake_fields)
            result["steps"]["loan"] = {"loan_id": loan.get("id"), "loan_number": loan.get("loan_number")}

            # Step 5: Apply intake fields to loan (auto-approve if configured)
            if auto_approve and intake_fields:
                applied = await self._auto_apply_intake_fields(session_id, loan["id"], intake_fields, user_id)
                result["steps"]["fields_applied"] = applied

            # Step 6: Generate MISMO 3.4 if completeness meets threshold
            if completeness.meets_threshold:
                mismo_result = await self._generate_mismo_file(loan, borrower, intake_fields)
                result["steps"]["mismo_3_4"] = mismo_result
            else:
                result["steps"]["mismo_3_4"] = {"status": "skipped", "reason": "completeness below threshold"}

            # Step 7: Create borrower portal
            portal_result = await self._provision_borrower_portal(
                loan_id=loan["id"],
                borrower=borrower,
                document_requests=await self._get_document_requests(session_id),
            )
            result["steps"]["portal"] = portal_result

            # Step 8: Send borrower notifications
            if borrower.get("email") or borrower.get("phone"):
                notification_result = await self._send_borrower_notifications(
                    borrower=borrower,
                    portal_url=portal_result.get("portal_url"),
                    loan=loan,
                )
                result["steps"]["notifications"] = notification_result

            # Step 9: Create tasks for Production Assistant
            tasks_result = await self._create_production_tasks(
                session_id=session_id,
                loan_id=loan["id"],
                user_id=user_id,
            )
            result["steps"]["tasks"] = tasks_result

            # Step 10: Email LO and Ops team
            internal_result = await self._send_internal_notifications(
                session_id=session_id,
                loan=loan,
                borrower=borrower,
                completeness=completeness,
                user_id=user_id,
                mismo_file=result["steps"].get("mismo_3_4", {}).get("file_path"),
            )
            result["steps"]["internal_notifications"] = internal_result

            # Mark session as completed
            await self._update_session_status(session_id, "completed")

            result["status"] = "success"
            result["completed_at"] = datetime.utcnow().isoformat()

        except Exception as e:
            logger.exception(f"Error processing call end for session {session_id}")
            result["status"] = "error"
            result["errors"].append(str(e))
            await self._update_session_status(session_id, "error")

        return result

    # =========================================================================
    # STEP IMPLEMENTATIONS
    # =========================================================================

    async def _get_session(self, session_id: str) -> Optional[Dict]:
        """Get call session details."""
        result = self.db.execute(text("""
            SELECT id, capture_mode, recording_id, loan_id, lead_id, contact_id,
                   user_id, status, full_transcript, participants, metadata,
                   started_at, ended_at
            FROM call_sessions
            WHERE id = :id
        """), {"id": session_id}).fetchone()

        if not result:
            return None

        return {
            "id": str(result[0]),
            "capture_mode": result[1],
            "recording_id": str(result[2]) if result[2] else None,
            "loan_id": str(result[3]) if result[3] else None,
            "lead_id": str(result[4]) if result[4] else None,
            "contact_id": str(result[5]) if result[5] else None,
            "user_id": str(result[6]) if result[6] else None,
            "status": result[7],
            "transcript": result[8],
            "participants": result[9] if result[9] else [],
            "metadata": result[10] if result[10] else {},
            "started_at": result[11],
            "ended_at": result[12],
        }

    async def _get_intake_fields(self, session_id: str) -> List[Dict]:
        """Get all intake fields extracted by Jr. LO agent."""
        results = self.db.execute(text("""
            SELECT id, field_name, field_path, proposed_value, confidence, evidence_text
            FROM intake_field_updates
            WHERE session_id = :session_id
            ORDER BY confidence DESC
        """), {"session_id": session_id}).fetchall()

        fields = []
        for r in results:
            value = r[3]
            # Parse JSON if stored as JSON
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except:
                    pass

            fields.append({
                "id": str(r[0]),
                "field_name": r[1],
                "field_path": r[2],
                "value": value,
                "confidence": float(r[4]) if r[4] else 0,
                "evidence": r[5],
            })

        return fields

    async def _update_session_completeness(
        self,
        session_id: str,
        completeness: CompletenessScore,
    ):
        """Update session with completeness score."""
        self.db.execute(text("""
            UPDATE call_sessions
            SET metadata = COALESCE(metadata, '{}'::jsonb) || :completeness::jsonb,
                updated_at = NOW()
            WHERE id = :session_id
        """), {
            "session_id": session_id,
            "completeness": json.dumps({
                "completeness_score": completeness.score,
                "completeness_percentage": completeness.score * 100,
                "meets_threshold": completeness.meets_threshold,
            }),
        })
        self.db.commit()

    async def _get_or_create_borrower(
        self,
        session: Dict,
        intake_fields: List[Dict],
    ) -> Dict[str, Any]:
        """Get or create borrower from intake fields."""
        # Extract borrower info from intake fields
        borrower_data = {}
        field_map = {
            "borrower.first_name": "first_name",
            "borrower.last_name": "last_name",
            "borrower.email": "email",
            "borrower.phone": "phone",
            "borrower.phone_cell": "phone",
            "first_name": "first_name",
            "last_name": "last_name",
            "email": "email",
            "phone": "phone",
        }

        for field in intake_fields:
            path = field.get("field_path", "").lower()
            name = field.get("field_name", "").lower()

            for pattern, key in field_map.items():
                if pattern in path or pattern in name:
                    if field.get("value") and not borrower_data.get(key):
                        borrower_data[key] = field["value"]

        # Check if contact already exists
        contact_id = session.get("contact_id")
        if contact_id:
            contact = self.db.execute(text("""
                SELECT id, first_name, last_name, email, phone
                FROM contacts
                WHERE id = :id
            """), {"id": contact_id}).fetchone()

            if contact:
                return {
                    "id": str(contact[0]),
                    "first_name": contact[1],
                    "last_name": contact[2],
                    "email": contact[3],
                    "phone": contact[4],
                    "is_new": False,
                }

        # Try to find by email
        if borrower_data.get("email"):
            contact = self.db.execute(text("""
                SELECT id, first_name, last_name, email, phone
                FROM contacts
                WHERE LOWER(email) = LOWER(:email)
                LIMIT 1
            """), {"email": borrower_data["email"]}).fetchone()

            if contact:
                return {
                    "id": str(contact[0]),
                    "first_name": contact[1] or borrower_data.get("first_name"),
                    "last_name": contact[2] or borrower_data.get("last_name"),
                    "email": contact[3],
                    "phone": contact[4] or borrower_data.get("phone"),
                    "is_new": False,
                }

        # Create new contact
        if borrower_data.get("first_name") or borrower_data.get("email"):
            contact_id = str(uuid.uuid4())
            self.db.execute(text("""
                INSERT INTO contacts (id, first_name, last_name, email, phone, source, created_at)
                VALUES (:id, :first_name, :last_name, :email, :phone, 'call_monitoring', NOW())
            """), {
                "id": contact_id,
                "first_name": borrower_data.get("first_name"),
                "last_name": borrower_data.get("last_name"),
                "email": borrower_data.get("email"),
                "phone": borrower_data.get("phone"),
            })
            self.db.commit()

            return {
                "id": contact_id,
                "first_name": borrower_data.get("first_name"),
                "last_name": borrower_data.get("last_name"),
                "email": borrower_data.get("email"),
                "phone": borrower_data.get("phone"),
                "is_new": True,
            }

        return {"id": None, "first_name": None, "last_name": None, "email": None, "phone": None, "is_new": False}

    async def _get_or_create_loan(
        self,
        session: Dict,
        borrower: Dict,
        intake_fields: List[Dict],
    ) -> Dict[str, Any]:
        """Get or create loan application."""
        # Check if loan already exists
        loan_id = session.get("loan_id")
        if loan_id:
            loan = self.db.execute(text("""
                SELECT id, loan_number, loan_amount, loan_type, property_address, status
                FROM loans
                WHERE id = :id
            """), {"id": loan_id}).fetchone()

            if loan:
                return {
                    "id": str(loan[0]),
                    "loan_number": loan[1],
                    "loan_amount": float(loan[2]) if loan[2] else None,
                    "loan_type": loan[3],
                    "property_address": loan[4],
                    "status": loan[5],
                    "is_new": False,
                }

        # Extract loan info from intake fields
        loan_data = {
            "loan_amount": None,
            "loan_type": "conventional",
            "loan_purpose": "purchase",
            "property_address": None,
        }

        for field in intake_fields:
            path = (field.get("field_path") or field.get("field_name") or "").lower()
            value = field.get("value")

            if "loan_amount" in path or "loan.amount" in path:
                try:
                    loan_data["loan_amount"] = float(str(value).replace(",", "").replace("$", ""))
                except:
                    pass
            elif "loan_type" in path or "loan.type" in path or "product_type" in path:
                loan_data["loan_type"] = value
            elif "loan_purpose" in path or "loan.purpose" in path:
                loan_data["loan_purpose"] = value
            elif "property_address" in path or "property.address" in path:
                loan_data["property_address"] = value

        # Generate loan number
        loan_number = f"LN-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
        loan_id = str(uuid.uuid4())

        # Create loan
        borrower_name = f"{borrower.get('first_name', '')} {borrower.get('last_name', '')}".strip()

        self.db.execute(text("""
            INSERT INTO loans (
                id, loan_number, borrower_name, borrower_id, loan_amount,
                loan_type, loan_purpose, property_address, status,
                loan_officer_id, source, created_at
            ) VALUES (
                :id, :loan_number, :borrower_name, :borrower_id, :loan_amount,
                :loan_type, :loan_purpose, :property_address, 'lead',
                :lo_id, 'call_monitoring', NOW()
            )
        """), {
            "id": loan_id,
            "loan_number": loan_number,
            "borrower_name": borrower_name or None,
            "borrower_id": borrower.get("id"),
            "loan_amount": loan_data["loan_amount"],
            "loan_type": loan_data["loan_type"],
            "loan_purpose": loan_data["loan_purpose"],
            "property_address": loan_data["property_address"],
            "lo_id": session.get("user_id"),
        })

        # Update session with loan_id
        self.db.execute(text("""
            UPDATE call_sessions SET loan_id = :loan_id WHERE id = :session_id
        """), {"loan_id": loan_id, "session_id": session["id"]})

        self.db.commit()

        return {
            "id": loan_id,
            "loan_number": loan_number,
            "loan_amount": loan_data["loan_amount"],
            "loan_type": loan_data["loan_type"],
            "property_address": loan_data["property_address"],
            "status": "lead",
            "is_new": True,
        }

    async def _auto_apply_intake_fields(
        self,
        session_id: str,
        loan_id: str,
        intake_fields: List[Dict],
        user_id: str,
    ) -> Dict[str, Any]:
        """Auto-approve and apply high-confidence intake fields."""
        applied = 0
        skipped = 0

        # Field path to column mapping for loans table
        field_to_column = {
            "loan.amount": "loan_amount",
            "loan_amount": "loan_amount",
            "loan.type": "loan_type",
            "loan_type": "loan_type",
            "loan.purpose": "loan_purpose",
            "loan_purpose": "loan_purpose",
            "property.address": "property_address",
            "property_address": "property_address",
            "borrower.credit_score": "credit_score",
            "credit_score": "credit_score",
        }

        for field in intake_fields:
            confidence = field.get("confidence", 0)

            # Only auto-apply high-confidence fields
            if confidence < 0.80:
                skipped += 1
                continue

            path = (field.get("field_path") or "").lower()
            column = None

            for pattern, col in field_to_column.items():
                if pattern in path:
                    column = col
                    break

            if column and field.get("value"):
                try:
                    self.db.execute(text(f"""
                        UPDATE loans SET {column} = :value, updated_at = NOW()
                        WHERE id = :loan_id
                    """), {"value": field["value"], "loan_id": loan_id})
                    applied += 1
                except Exception as e:
                    logger.warning(f"Could not apply field {path}: {e}")
                    skipped += 1

        # Mark intake fields as applied
        self.db.execute(text("""
            UPDATE intake_field_updates
            SET status = 'auto_applied', applied_by = :user_id, applied_at = NOW()
            WHERE session_id = :session_id AND confidence >= 0.80
        """), {"session_id": session_id, "user_id": user_id})

        self.db.commit()

        return {"applied": applied, "skipped": skipped}

    async def _generate_mismo_file(
        self,
        loan: Dict,
        borrower: Dict,
        intake_fields: List[Dict],
    ) -> Dict[str, Any]:
        """Generate MISMO 3.4 XML file."""
        try:
            # Build application data from intake fields
            application_data = {
                "loan": {
                    "loan_number": loan.get("loan_number"),
                    "loan_amount": loan.get("loan_amount"),
                    "loan_purpose": loan.get("loan_purpose", "purchase"),
                    "loan_type": loan.get("loan_type", "conventional"),
                },
                "borrower": {
                    "first_name": borrower.get("first_name"),
                    "last_name": borrower.get("last_name"),
                    "email": borrower.get("email"),
                    "phone": borrower.get("phone"),
                },
                "property": {
                    "address": loan.get("property_address"),
                },
            }

            # Add intake fields
            for field in intake_fields:
                path = field.get("field_path", "").split(".")
                if len(path) >= 2:
                    section = path[0]
                    key = "_".join(path[1:])
                    if section not in application_data:
                        application_data[section] = {}
                    application_data[section][key] = field.get("value")

            # Generate MISMO XML
            mismo_xml = self.mismo_generator.generate(application_data)

            # Save to file (or S3 in production)
            filename = f"MISMO_3.4_{loan['loan_number']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
            file_path = f"/tmp/{filename}"

            with open(file_path, "w") as f:
                f.write(mismo_xml)

            # Store reference in database
            file_id = str(uuid.uuid4())
            self.db.execute(text("""
                INSERT INTO loan_documents (
                    id, loan_id, document_type, file_name, file_path,
                    status, source, created_at
                ) VALUES (
                    :id, :loan_id, 'mismo_3_4', :file_name, :file_path,
                    'generated', 'call_monitoring', NOW()
                )
            """), {
                "id": file_id,
                "loan_id": loan["id"],
                "file_name": filename,
                "file_path": file_path,
            })
            self.db.commit()

            return {
                "status": "success",
                "file_id": file_id,
                "file_name": filename,
                "file_path": file_path,
            }

        except Exception as e:
            logger.error(f"Failed to generate MISMO file: {e}")
            return {"status": "error", "error": str(e)}

    async def _get_document_requests(self, session_id: str) -> List[Dict]:
        """Get document requests from Jr. LO agent."""
        results = self.db.execute(text("""
            SELECT ca.id, ca.title, ca.content, ca.structured_data
            FROM call_artifacts ca
            WHERE ca.session_id = :session_id
              AND ca.artifact_type = 'document_request'
        """), {"session_id": session_id}).fetchall()

        return [
            {
                "id": str(r[0]),
                "document_type": r[1],
                "description": r[2],
                "data": r[3] if r[3] else {},
            }
            for r in results
        ]

    async def _provision_borrower_portal(
        self,
        loan_id: str,
        borrower: Dict,
        document_requests: List[Dict],
    ) -> Dict[str, Any]:
        """Create or update borrower portal."""
        try:
            # Create portal loan record
            portal_loan = self.portal_service.get_portal_loan(loan_id)

            if portal_loan:
                portal_id = portal_loan.id
            else:
                portal_id = loan_id

            # Generate magic link
            access_token = str(uuid.uuid4())
            expires_at = datetime.utcnow().replace(hour=0, minute=0, second=0)
            from datetime import timedelta
            expires_at = expires_at + timedelta(hours=72)

            # Store magic link
            self.db.execute(text("""
                INSERT INTO portal_access_tokens (
                    id, portal_loan_id, borrower_email, token, expires_at, created_at
                ) VALUES (
                    gen_random_uuid(), :portal_id, :email, :token, :expires_at, NOW()
                )
                ON CONFLICT (borrower_email) DO UPDATE SET
                    token = EXCLUDED.token,
                    expires_at = EXCLUDED.expires_at
            """), {
                "portal_id": portal_id,
                "email": borrower.get("email"),
                "token": access_token,
                "expires_at": expires_at,
            })

            # Add document requirements to portal
            for doc_req in document_requests:
                self.db.execute(text("""
                    INSERT INTO portal_document_requirements (
                        id, portal_loan_id, document_type, description,
                        status, priority, source, created_at
                    ) VALUES (
                        gen_random_uuid(), :portal_id, :doc_type, :description,
                        'pending', 'high', 'call_monitoring', NOW()
                    )
                    ON CONFLICT DO NOTHING
                """), {
                    "portal_id": portal_id,
                    "doc_type": doc_req.get("document_type"),
                    "description": doc_req.get("description"),
                })

            self.db.commit()

            # Build portal URL
            portal_url = f"{PORTAL_BASE_URL}/access/{access_token}"

            return {
                "status": "success",
                "portal_id": str(portal_id),
                "portal_url": portal_url,
                "access_token": access_token,
                "documents_added": len(document_requests),
            }

        except Exception as e:
            logger.error(f"Failed to provision portal: {e}")
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def _send_borrower_notifications(
        self,
        borrower: Dict,
        portal_url: str,
        loan: Dict,
    ) -> Dict[str, Any]:
        """Send SMS and email to borrower."""
        result = {"sms": None, "email": None}

        borrower_name = borrower.get("first_name") or "there"

        # Send SMS
        if borrower.get("phone"):
            sms_message = (
                f"Hi {borrower_name}, your home loan portal is ready! "
                f"Upload your documents securely here: {portal_url}"
            )

            try:
                sms_result = self.notification_service.send_sms(
                    to_phone=borrower["phone"],
                    message=sms_message,
                )
                result["sms"] = {"status": "sent", "result": sms_result}
            except Exception as e:
                logger.error(f"Failed to send SMS: {e}")
                result["sms"] = {"status": "error", "error": str(e)}

        # Send email
        if borrower.get("email"):
            email_subject = f"Your Loan Application Portal is Ready - {COMPANY_NAME}"
            email_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Welcome, {borrower_name}!</h2>

                <p>Thank you for starting your home loan application with us. Your secure portal is now ready.</p>

                <h3>What to Expect:</h3>
                <ul>
                    <li>Upload your documents securely</li>
                    <li>Track your application status in real-time</li>
                    <li>Communicate directly with your loan team</li>
                </ul>

                <p style="text-align: center; margin: 30px 0;">
                    <a href="{portal_url}"
                       style="background-color: #2563eb; color: white; padding: 12px 24px;
                              text-decoration: none; border-radius: 6px; font-weight: bold;">
                        Access Your Portal
                    </a>
                </p>

                <h3>Documents We'll Need:</h3>
                <ul>
                    <li>Recent pay stubs (last 30 days)</li>
                    <li>W-2s from the last 2 years</li>
                    <li>Bank statements (last 2 months)</li>
                    <li>Government-issued ID</li>
                </ul>

                <p>The sooner you upload your documents, the faster we can move forward!</p>

                <p>Questions? Reply to this email or call us anytime.</p>

                <p>Best regards,<br>
                Your {COMPANY_NAME} Team</p>
            </body>
            </html>
            """

            try:
                email_result = self.notification_service.send_email(
                    to_email=borrower["email"],
                    subject=email_subject,
                    html_content=email_html,
                )
                result["email"] = {"status": "sent", "result": email_result}
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
                result["email"] = {"status": "error", "error": str(e)}

        return result

    async def _create_production_tasks(
        self,
        session_id: str,
        loan_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Create tasks for Production Assistants from underwriter conditions."""
        # Get risk flags and conditions from underwriter
        risk_flags = self.db.execute(text("""
            SELECT crf.id, crf.title, crf.description, crf.severity,
                   crf.risk_category, crf.condition_type, crf.recommended_action
            FROM call_risk_flags crf
            WHERE crf.session_id = :session_id
        """), {"session_id": session_id}).fetchall()

        # Find Production Assistant user
        pa_user = self.db.execute(text("""
            SELECT id, name FROM users
            WHERE role IN ('production_assistant', 'processor', 'pa', 'PA')
               OR title ILIKE '%production assistant%'
               OR title ILIKE '%processor%'
            ORDER BY created_at ASC
            LIMIT 1
        """)).fetchone()

        pa_user_id = str(pa_user[0]) if pa_user else user_id

        tasks_created = 0
        conditions_created = 0

        for flag in risk_flags:
            # Create loan condition
            condition_id = str(uuid.uuid4())
            self.db.execute(text("""
                INSERT INTO loan_conditions (
                    id, loan_id, condition_type, category, description,
                    status, priority, created_by, source, source_id
                ) VALUES (
                    :id, :loan_id, :condition_type, :category, :description,
                    'open', :priority, :created_by, 'ai_underwriter', :source_id
                )
            """), {
                "id": condition_id,
                "loan_id": loan_id,
                "condition_type": flag[5] or "prior_to_docs",
                "category": flag[4],
                "description": f"{flag[1]}: {flag[2]}",
                "priority": "high" if flag[3] in ("high", "critical") else "medium",
                "created_by": user_id,
                "source_id": str(flag[0]),
            })
            conditions_created += 1

            # Create task for Production Assistant
            task_id = str(uuid.uuid4())
            self.db.execute(text("""
                INSERT INTO tasks (
                    id, title, description, loan_id, assigned_to,
                    created_by, status, priority, category, source, source_id
                ) VALUES (
                    :id, :title, :description, :loan_id, :assigned_to,
                    :created_by, 'open', :priority, 'condition', 'ai_underwriter', :source_id
                )
            """), {
                "id": task_id,
                "title": f"Clear Condition: {flag[1]}",
                "description": f"{flag[2]}\n\nRecommended Action: {flag[6] or 'Review and clear condition'}",
                "loan_id": loan_id,
                "assigned_to": pa_user_id,
                "created_by": user_id,
                "priority": "high" if flag[3] in ("high", "critical") else "medium",
                "source_id": condition_id,
            })
            tasks_created += 1

        self.db.commit()

        return {
            "tasks_created": tasks_created,
            "conditions_created": conditions_created,
            "assigned_to": pa_user_id,
            "assigned_to_name": pa_user[1] if pa_user else "Loan Officer",
        }

    async def _send_internal_notifications(
        self,
        session_id: str,
        loan: Dict,
        borrower: Dict,
        completeness: CompletenessScore,
        user_id: str,
        mismo_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send internal email to LO and Ops team."""
        # Get LO info
        lo = self.db.execute(text("""
            SELECT id, name, email FROM users WHERE id = :id
        """), {"id": user_id}).fetchone()

        lo_name = lo[1] if lo else "Loan Officer"
        lo_email = lo[2] if lo else None

        # Get ops email from settings
        ops_email = os.getenv("OPS_EMAIL", "ops@perenniaai.com")

        borrower_name = f"{borrower.get('first_name', '')} {borrower.get('last_name', '')}".strip() or "Unknown Borrower"

        subject = f"New Loan Application - {borrower_name} - Fannie Mae 3.4 {'Attached' if mismo_file else 'Pending'}"

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>New Loan Application from Call Recording</h2>

            <h3>Borrower Information</h3>
            <ul>
                <li><strong>Name:</strong> {borrower_name}</li>
                <li><strong>Email:</strong> {borrower.get('email') or 'Not provided'}</li>
                <li><strong>Phone:</strong> {borrower.get('phone') or 'Not provided'}</li>
            </ul>

            <h3>Loan Details</h3>
            <ul>
                <li><strong>Loan Number:</strong> {loan.get('loan_number')}</li>
                <li><strong>Loan Amount:</strong> ${loan.get('loan_amount', 0):,.0f}</li>
                <li><strong>Loan Type:</strong> {loan.get('loan_type', 'TBD')}</li>
                <li><strong>Property:</strong> {loan.get('property_address') or 'Not provided'}</li>
            </ul>

            <h3>Application Completeness</h3>
            <ul>
                <li><strong>Score:</strong> {completeness.score * 100:.1f}%</li>
                <li><strong>Fields Captured:</strong> {completeness.fields_captured} / {completeness.fields_total}</li>
                <li><strong>Status:</strong> {'Ready for Processing' if completeness.meets_threshold else 'Needs More Information'}</li>
            </ul>

            {f'<p><strong>Fannie Mae 3.4 file attached.</strong></p>' if mismo_file else '<p><em>MISMO file pending - completeness below threshold.</em></p>'}

            <h3>Missing Required Fields</h3>
            <ul>
                {''.join(f'<li>{f}</li>' for f in completeness.missing_required[:5]) or '<li>None - all required fields captured!</li>'}
            </ul>

            <p>View full details in the CRM: <a href="{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/loans/{loan.get('id')}">Open Loan</a></p>

            <p>Best regards,<br>
            AI Call Monitoring System</p>
        </body>
        </html>
        """

        results = {"lo_email": None, "ops_email": None}

        # Send to LO
        if lo_email:
            try:
                attachments = None
                if mismo_file:
                    with open(mismo_file, 'r') as f:
                        attachments = [{
                            'content': f.read(),
                            'filename': os.path.basename(mismo_file),
                            'type': 'application/xml',
                        }]

                result = self.notification_service.send_email(
                    to_email=lo_email,
                    subject=subject,
                    html_content=html_content,
                    attachments=attachments,
                )
                results["lo_email"] = {"status": "sent", "to": lo_email}
            except Exception as e:
                results["lo_email"] = {"status": "error", "error": str(e)}

        # Send to Ops
        if ops_email and ops_email != lo_email:
            try:
                result = self.notification_service.send_email(
                    to_email=ops_email,
                    subject=subject,
                    html_content=html_content,
                    cc=[lo_email] if lo_email else None,
                )
                results["ops_email"] = {"status": "sent", "to": ops_email}
            except Exception as e:
                results["ops_email"] = {"status": "error", "error": str(e)}

        return results

    async def _update_session_status(self, session_id: str, status: str):
        """Update session status."""
        self.db.execute(text("""
            UPDATE call_sessions
            SET status = :status, updated_at = NOW()
            WHERE id = :session_id
        """), {"session_id": session_id, "status": status})
        self.db.commit()
