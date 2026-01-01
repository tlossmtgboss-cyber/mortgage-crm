"""
Recruiting Workflow Service
Multi-year relationship development for Loan Officers and Realtors.

Features:
- Person management with relationship tracking
- Signal detection and timing score calculation
- Cadence execution and enrollment
- Playbook trigger evaluation and execution
- Contact preference learning
- Next best action recommendations
"""

from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from dataclasses import dataclass, field
import logging
import uuid
import json

from models.recruiting_workflow_models import (
    PersonType, RelationshipStage, CommChannel, EventType,
    ObjectionCategory, SignalType, EdgeType, TaskPriority, TaskStatus,
    PersonCreate, PersonUpdate, Person, PersonSummary,
    SignalCreate, Signal, ObjectionCreate, Objection,
    CadenceEnrollmentCreate, CadenceEnrollment, CadenceDueItem,
    PlaybookRunCreate, PlaybookRun,
    TaskCreate, Task, NoteCreate, Note,
    MeetingCreate, Meeting, CommOutcomeCreate, CommOutcome,
    NextBestActionResponse, TimingIntelligence, WorkflowStats,
    MutualConnection, TopConnection,
    SIGNAL_WEIGHTS, DEFAULT_SIGNAL_WEIGHT,
    TIMING_THRESHOLD_HOT, TIMING_THRESHOLD_WARM, TIMING_THRESHOLD_COOL,
    OBJECTION_REVISIT_DAYS
)

logger = logging.getLogger(__name__)


class RecruitingWorkflowService:
    """
    Service for managing the recruiting workflow CRM.
    Handles multi-year relationship development with LOs and Realtors.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # PERSON MANAGEMENT
    # =========================================================================

    async def create_person(
        self,
        data: PersonCreate,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new person (LO or Realtor)."""
        person_id = str(uuid.uuid4())

        query = text("""
            INSERT INTO rw_person (
                id, organization_id, person_type, first_name, last_name,
                primary_email, secondary_email, primary_phone, secondary_phone,
                linkedin_url, instagram_handle, facebook_url, twitter_handle,
                location_city, location_state, location_zip, timezone,
                current_org_id, title, nmls_id, license_state, years_experience,
                annual_volume, annual_units, avg_loan_size,
                relationship_stage, owner_user_id,
                source, source_campaign, referrer_person_id,
                tags, custom_fields
            ) VALUES (
                :id, :organization_id, :person_type, :first_name, :last_name,
                :primary_email, :secondary_email, :primary_phone, :secondary_phone,
                :linkedin_url, :instagram_handle, :facebook_url, :twitter_handle,
                :location_city, :location_state, :location_zip, :timezone,
                :current_org_id, :title, :nmls_id, :license_state, :years_experience,
                :annual_volume, :annual_units, :avg_loan_size,
                'DISCOVERED', :owner_user_id,
                :source, :source_campaign, :referrer_person_id,
                :tags, :custom_fields
            )
            RETURNING id, display_name, relationship_stage, created_at
        """)

        result = self.db.execute(query, {
            "id": person_id,
            "organization_id": data.organization_id,
            "person_type": data.person_type.value,
            "first_name": data.first_name,
            "last_name": data.last_name,
            "primary_email": data.primary_email,
            "secondary_email": data.secondary_email,
            "primary_phone": data.primary_phone,
            "secondary_phone": data.secondary_phone,
            "linkedin_url": data.linkedin_url,
            "instagram_handle": data.instagram_handle,
            "facebook_url": data.facebook_url,
            "twitter_handle": data.twitter_handle,
            "location_city": data.location_city,
            "location_state": data.location_state,
            "location_zip": data.location_zip,
            "timezone": data.timezone,
            "current_org_id": data.current_org_id,
            "title": data.title,
            "nmls_id": data.nmls_id,
            "license_state": data.license_state,
            "years_experience": data.years_experience,
            "annual_volume": data.annual_volume,
            "annual_units": data.annual_units,
            "avg_loan_size": data.avg_loan_size,
            "owner_user_id": data.owner_user_id or user_id,
            "source": data.source,
            "source_campaign": data.source_campaign,
            "referrer_person_id": data.referrer_person_id,
            "tags": data.tags,
            "custom_fields": json.dumps(data.custom_fields) if data.custom_fields else None,
        }).fetchone()

        # Create relationship intel record
        intel_query = text("""
            INSERT INTO rw_relationship_intel (person_id)
            VALUES (:person_id)
        """)
        self.db.execute(intel_query, {"person_id": person_id})

        # Create contact preference record
        pref_query = text("""
            INSERT INTO rw_contact_preference (person_id)
            VALUES (:person_id)
        """)
        self.db.execute(pref_query, {"person_id": person_id})

        # Log event
        await self._log_event(
            EventType.PERSON_CREATED,
            person_id=person_id,
            user_id=user_id,
            payload={"person_type": data.person_type.value}
        )

        self.db.commit()

        return {
            "id": person_id,
            "display_name": result.display_name,
            "relationship_stage": result.relationship_stage,
            "created_at": result.created_at.isoformat()
        }

    async def get_person(self, person_id: str) -> Optional[Dict[str, Any]]:
        """Get a person by ID with relationship intelligence."""
        query = text("""
            SELECT
                p.*,
                ri.timing_score,
                ri.trust_score,
                ri.engagement_score,
                ri.overall_score,
                ri.last_signal_at,
                ri.last_signal_type,
                ri.next_best_action,
                ri.why_they_might_switch,
                ri.what_they_care_about,
                o.name as org_name
            FROM rw_person p
            LEFT JOIN rw_relationship_intel ri ON ri.person_id = p.id
            LEFT JOIN rw_org o ON o.id = p.current_org_id
            WHERE p.id = :person_id
        """)
        result = self.db.execute(query, {"person_id": person_id}).fetchone()

        if not result:
            return None

        return dict(result._mapping)

    async def get_person_summary(self, person_id: str) -> Optional[Dict[str, Any]]:
        """Get person summary from the view."""
        query = text("""
            SELECT * FROM rw_person_summary WHERE id = :person_id
        """)
        result = self.db.execute(query, {"person_id": person_id}).fetchone()

        if not result:
            return None

        return dict(result._mapping)

    async def list_people(
        self,
        organization_id: Optional[int] = None,
        person_type: Optional[PersonType] = None,
        relationship_stage: Optional[RelationshipStage] = None,
        owner_user_id: Optional[int] = None,
        min_timing_score: Optional[int] = None,
        search: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "timing_score DESC"
    ) -> Dict[str, Any]:
        """List people with filters."""
        filters = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if organization_id:
            filters.append("ps.organization_id = :org_id")
            params["org_id"] = organization_id

        if person_type:
            filters.append("ps.person_type = :person_type")
            params["person_type"] = person_type.value

        if relationship_stage:
            filters.append("ps.relationship_stage = :stage")
            params["stage"] = relationship_stage.value

        if owner_user_id:
            filters.append("ps.owner_user_id = :owner_id")
            params["owner_id"] = owner_user_id

        if min_timing_score is not None:
            filters.append("COALESCE(ps.timing_score, 0) >= :min_score")
            params["min_score"] = min_timing_score

        if search:
            filters.append("""
                (ps.display_name ILIKE '%' || :search || '%'
                 OR ps.primary_email ILIKE '%' || :search || '%'
                 OR ps.primary_phone ILIKE '%' || :search || '%')
            """)
            params["search"] = search

        if tags:
            filters.append("ps.tags && :tags")
            params["tags"] = tags

        where_clause = " AND ".join(filters)

        # Validate order_by to prevent SQL injection
        allowed_orders = [
            "timing_score DESC", "timing_score ASC",
            "created_at DESC", "created_at ASC",
            "display_name ASC", "display_name DESC",
            "overall_score DESC", "overall_score ASC"
        ]
        if order_by not in allowed_orders:
            order_by = "timing_score DESC"

        query = text(f"""
            SELECT * FROM rw_person_summary ps
            WHERE {where_clause}
            ORDER BY {order_by} NULLS LAST
            LIMIT :limit OFFSET :offset
        """)

        count_query = text(f"""
            SELECT COUNT(*) as total FROM rw_person_summary ps
            WHERE {where_clause}
        """)

        results = self.db.execute(query, params).fetchall()
        total = self.db.execute(count_query, params).fetchone().total

        return {
            "data": [dict(r._mapping) for r in results],
            "total": total,
            "limit": limit,
            "offset": offset
        }

    async def update_person(
        self,
        person_id: str,
        data: PersonUpdate,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update a person."""
        updates = []
        params = {"person_id": person_id}

        # Build dynamic update
        update_fields = data.model_dump(exclude_unset=True)
        for field, value in update_fields.items():
            if field == "relationship_stage" and value:
                updates.append(f"{field} = :val_{field}")
                params[f"val_{field}"] = value.value
            elif field == "custom_fields" and value:
                updates.append(f"{field} = :val_{field}")
                params[f"val_{field}"] = json.dumps(value)
            elif value is not None:
                updates.append(f"{field} = :val_{field}")
                params[f"val_{field}"] = value

        if not updates:
            return {"id": person_id, "updated": False}

        updates.append("updated_at = NOW()")
        query = text(f"""
            UPDATE rw_person
            SET {', '.join(updates)}
            WHERE id = :person_id
            RETURNING id, display_name, relationship_stage, updated_at
        """)

        result = self.db.execute(query, params).fetchone()

        # Log stage change event if applicable
        if "relationship_stage" in update_fields:
            await self._log_event(
                EventType.STAGE_CHANGED,
                person_id=person_id,
                user_id=user_id,
                payload={"new_stage": update_fields["relationship_stage"].value}
            )

        self.db.commit()

        return {
            "id": person_id,
            "display_name": result.display_name,
            "relationship_stage": result.relationship_stage,
            "updated_at": result.updated_at.isoformat()
        }

    async def get_hot_leads(
        self,
        organization_id: Optional[int] = None,
        person_type: Optional[PersonType] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get hot leads (timing_score >= 70)."""
        query = text("""
            SELECT * FROM rw_hot_leads
            WHERE (:org_id IS NULL OR organization_id = :org_id)
            AND (:person_type IS NULL OR person_type = :person_type)
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "org_id": organization_id,
            "person_type": person_type.value if person_type else None,
            "limit": limit
        }).fetchall()

        return [dict(r._mapping) for r in results]

    # =========================================================================
    # SIGNAL DETECTION & TIMING INTELLIGENCE
    # =========================================================================

    async def create_signal(
        self,
        data: SignalCreate,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create and process a signal."""
        signal_id = str(uuid.uuid4())

        # Get person type for weight calculation
        person = await self.get_person(data.person_id)
        if not person:
            raise ValueError(f"Person {data.person_id} not found")

        person_type = PersonType(person["person_type"])

        # Calculate weight
        weight = data.weight
        if weight is None:
            weights = SIGNAL_WEIGHTS.get(person_type, {})
            weight = weights.get(data.signal_type, DEFAULT_SIGNAL_WEIGHT)

        query = text("""
            INSERT INTO rw_signal (
                id, person_id, signal_type, confidence, weight,
                evidence, source, source_reference,
                detected_by, ai_detected, expires_at
            ) VALUES (
                :id, :person_id, :signal_type, :confidence, :weight,
                :evidence, :source, :source_reference,
                :detected_by, :ai_detected, :expires_at
            )
            RETURNING id, created_at
        """)

        result = self.db.execute(query, {
            "id": signal_id,
            "person_id": data.person_id,
            "signal_type": data.signal_type.value,
            "confidence": data.confidence,
            "weight": weight,
            "evidence": data.evidence,
            "source": data.source,
            "source_reference": data.source_reference,
            "detected_by": data.detected_by or user_id,
            "ai_detected": data.ai_detected,
            "expires_at": data.expires_at,
        }).fetchone()

        # Process the signal immediately
        new_score = await self._process_signal(signal_id)

        # Log event
        await self._log_event(
            EventType.SIGNAL_DETECTED,
            person_id=data.person_id,
            user_id=user_id,
            payload={
                "signal_id": signal_id,
                "signal_type": data.signal_type.value,
                "weight": weight,
                "new_timing_score": new_score
            }
        )

        # Check for playbook triggers
        await self._evaluate_playbook_triggers(data.person_id, signal_id=signal_id)

        self.db.commit()

        return {
            "id": signal_id,
            "weight": weight,
            "new_timing_score": new_score,
            "created_at": result.created_at.isoformat()
        }

    async def _process_signal(self, signal_id: str) -> int:
        """Process a signal and update timing score."""
        # Use the database function
        query = text("SELECT rw_process_signal(:signal_id) as new_score")
        result = self.db.execute(query, {"signal_id": signal_id}).fetchone()
        return result.new_score or 0

    async def get_timing_intelligence(
        self,
        person_id: str
    ) -> Dict[str, Any]:
        """Get timing intelligence for a person."""
        # Get intel
        intel_query = text("""
            SELECT
                ri.*,
                p.person_type,
                p.display_name
            FROM rw_relationship_intel ri
            JOIN rw_person p ON p.id = ri.person_id
            WHERE ri.person_id = :person_id
        """)
        intel = self.db.execute(intel_query, {"person_id": person_id}).fetchone()

        if not intel:
            return None

        # Get recent signals
        signals_query = text("""
            SELECT * FROM rw_signal
            WHERE person_id = :person_id
            ORDER BY created_at DESC
            LIMIT 10
        """)
        signals = self.db.execute(signals_query, {"person_id": person_id}).fetchall()

        # Determine timing grade
        score = intel.timing_score or 0
        if score >= TIMING_THRESHOLD_HOT:
            grade = "HOT"
        elif score >= TIMING_THRESHOLD_WARM:
            grade = "WARM"
        elif score >= TIMING_THRESHOLD_COOL:
            grade = "COOL"
        else:
            grade = "COLD"

        return {
            "person_id": person_id,
            "display_name": intel.display_name,
            "timing_score": score,
            "timing_grade": grade,
            "last_signal_at": intel.last_signal_at.isoformat() if intel.last_signal_at else None,
            "last_signal_type": intel.last_signal_type,
            "why_now": intel.why_they_might_switch,
            "what_they_care_about": intel.what_they_care_about,
            "next_best_action": intel.next_best_action,
            "recent_signals": [dict(s._mapping) for s in signals]
        }

    async def decay_timing_scores(self) -> int:
        """Run daily timing score decay. Returns count of updated records."""
        query = text("SELECT rw_decay_timing_scores() as count")
        result = self.db.execute(query).fetchone()
        self.db.commit()
        return result.count or 0

    # =========================================================================
    # MUTUAL CONNECTIONS
    # =========================================================================

    async def create_person_edge(
        self,
        from_person_id: str,
        to_person_id: str,
        edge_type: EdgeType,
        strength: int = 1,
        evidence: Optional[str] = None,
        deal_id: Optional[int] = None,
        occurred_at: Optional[datetime] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a relationship edge between two people."""
        edge_id = str(uuid.uuid4())

        query = text("""
            INSERT INTO rw_person_edge (
                id, from_person_id, to_person_id, edge_type,
                strength, evidence, deal_id, occurred_at
            ) VALUES (
                :id, :from_person_id, :to_person_id, :edge_type,
                :strength, :evidence, :deal_id, :occurred_at
            )
            ON CONFLICT (from_person_id, to_person_id, edge_type)
            DO UPDATE SET
                strength = GREATEST(rw_person_edge.strength, EXCLUDED.strength),
                evidence = COALESCE(EXCLUDED.evidence, rw_person_edge.evidence)
            RETURNING id, created_at
        """)

        result = self.db.execute(query, {
            "id": edge_id,
            "from_person_id": from_person_id,
            "to_person_id": to_person_id,
            "edge_type": edge_type.value,
            "strength": strength,
            "evidence": evidence,
            "deal_id": deal_id,
            "occurred_at": occurred_at,
        }).fetchone()

        self.db.commit()

        return {
            "id": result.id,
            "from_person_id": from_person_id,
            "to_person_id": to_person_id,
            "edge_type": edge_type.value,
            "created_at": result.created_at.isoformat()
        }

    async def find_mutual_connections(
        self,
        person_a_id: str,
        person_b_id: str
    ) -> List[Dict[str, Any]]:
        """Find mutual connections between two people."""
        query = text("""
            SELECT * FROM rw_find_mutuals(:person_a, :person_b)
        """)

        results = self.db.execute(query, {
            "person_a": person_a_id,
            "person_b": person_b_id
        }).fetchall()

        return [dict(r._mapping) for r in results]

    async def get_top_connections(
        self,
        person_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top connections for a person."""
        query = text("""
            SELECT * FROM rw_get_top_connections(:person_id, :limit)
        """)

        results = self.db.execute(query, {
            "person_id": person_id,
            "limit": limit
        }).fetchall()

        return [dict(r._mapping) for r in results]

    # =========================================================================
    # OBJECTION MANAGEMENT
    # =========================================================================

    async def create_objection(
        self,
        data: ObjectionCreate,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Log an objection for a person."""
        objection_id = str(uuid.uuid4())

        query = text("""
            INSERT INTO rw_objection (
                id, person_id, category, subcategory, severity,
                statement, context, captured_by_user_id, captured_via
            ) VALUES (
                :id, :person_id, :category, :subcategory, :severity,
                :statement, :context, :captured_by, :captured_via
            )
            RETURNING id, next_revisit_at, created_at
        """)

        result = self.db.execute(query, {
            "id": objection_id,
            "person_id": data.person_id,
            "category": data.category.value,
            "subcategory": data.subcategory,
            "severity": data.severity,
            "statement": data.statement,
            "context": data.context,
            "captured_by": user_id,
            "captured_via": data.captured_via,
        }).fetchone()

        # Log event
        await self._log_event(
            EventType.OBJECTION_LOGGED,
            person_id=data.person_id,
            user_id=user_id,
            payload={
                "objection_id": objection_id,
                "category": data.category.value,
                "severity": data.severity
            }
        )

        self.db.commit()

        return {
            "id": objection_id,
            "next_revisit_at": result.next_revisit_at.isoformat() if result.next_revisit_at else None,
            "created_at": result.created_at.isoformat()
        }

    async def get_objections(
        self,
        person_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get objections for a person."""
        query = text("""
            SELECT * FROM rw_objection
            WHERE person_id = :person_id
            AND (:status IS NULL OR status = :status)
            ORDER BY severity DESC, created_at DESC
        """)

        results = self.db.execute(query, {
            "person_id": person_id,
            "status": status
        }).fetchall()

        return [dict(r._mapping) for r in results]

    async def update_objection(
        self,
        objection_id: str,
        status: Optional[str] = None,
        our_response: Optional[str] = None,
        resolution_notes: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update an objection."""
        updates = ["updated_at = NOW()"]
        params = {"objection_id": objection_id}

        if status:
            updates.append("status = :status")
            params["status"] = status
            if status == "ADDRESSED":
                updates.append("addressed_at = NOW()")
            elif status == "RESOLVED":
                updates.append("resolved_at = NOW()")

        if our_response:
            updates.append("our_response = :our_response")
            params["our_response"] = our_response

        if resolution_notes:
            updates.append("resolution_notes = :resolution_notes")
            params["resolution_notes"] = resolution_notes

        query = text(f"""
            UPDATE rw_objection
            SET {', '.join(updates)}
            WHERE id = :objection_id
            RETURNING id, status, updated_at
        """)

        result = self.db.execute(query, params).fetchone()

        # If objection softened, create a signal
        if status in ["ADDRESSED", "RESOLVED"]:
            person_query = text("SELECT person_id FROM rw_objection WHERE id = :id")
            person_result = self.db.execute(person_query, {"id": objection_id}).fetchone()

            if person_result:
                await self.create_signal(
                    SignalCreate(
                        person_id=person_result.person_id,
                        signal_type=SignalType.OBJECTION_SOFTENED,
                        confidence=0.8,
                        evidence=f"Objection {objection_id} marked as {status}",
                        source="objection_update"
                    ),
                    user_id=user_id
                )

        self.db.commit()

        return {
            "id": objection_id,
            "status": result.status,
            "updated_at": result.updated_at.isoformat()
        }

    async def get_objections_due_for_revisit(
        self,
        organization_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get objections due for revisit."""
        query = text("""
            SELECT * FROM rw_objections_due
            WHERE (:org_id IS NULL OR person_id IN (
                SELECT id FROM rw_person WHERE organization_id = :org_id
            ))
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "org_id": organization_id,
            "limit": limit
        }).fetchall()

        return [dict(r._mapping) for r in results]

    # =========================================================================
    # CADENCE MANAGEMENT
    # =========================================================================

    async def enroll_in_cadence(
        self,
        data: CadenceEnrollmentCreate,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Enroll a person in a cadence."""
        enrollment_id = str(uuid.uuid4())

        # Get first step timing
        step_query = text("""
            SELECT min_days_after_prev FROM rw_cadence_step
            WHERE cadence_id = :cadence_id AND step_order = 1
        """)
        step = self.db.execute(step_query, {"cadence_id": data.cadence_id}).fetchone()

        start_at = data.start_at or datetime.now(timezone.utc)
        next_due = start_at + timedelta(days=step.min_days_after_prev if step else 0)

        query = text("""
            INSERT INTO rw_cadence_enrollment (
                id, person_id, cadence_id, status,
                current_step, enrolled_at, next_step_due_at, enrolled_by
            ) VALUES (
                :id, :person_id, :cadence_id, 'ACTIVE',
                1, :enrolled_at, :next_due, :enrolled_by
            )
            RETURNING id, next_step_due_at, created_at
        """)

        result = self.db.execute(query, {
            "id": enrollment_id,
            "person_id": data.person_id,
            "cadence_id": data.cadence_id,
            "enrolled_at": start_at,
            "next_due": next_due,
            "enrolled_by": data.enrolled_by or user_id,
        }).fetchone()

        self.db.commit()

        return {
            "id": enrollment_id,
            "next_step_due_at": result.next_step_due_at.isoformat(),
            "created_at": result.created_at.isoformat()
        }

    async def get_cadences_due(
        self,
        organization_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get cadence enrollments that are due for execution."""
        query = text("""
            SELECT
                ce.id as enrollment_id,
                c.name as cadence_name,
                c.key as cadence_key,
                ce.current_step,
                cs.channel as next_channel,
                cs.template_key as next_template,
                cs.goal as next_goal,
                p.id as person_id,
                p.display_name as person_name,
                p.person_type,
                p.primary_email,
                p.primary_phone
            FROM rw_cadence_enrollment ce
            JOIN rw_cadence c ON c.id = ce.cadence_id
            JOIN rw_cadence_step cs ON cs.cadence_id = c.id AND cs.step_order = ce.current_step
            JOIN rw_person p ON p.id = ce.person_id
            WHERE ce.status = 'ACTIVE'
              AND ce.next_step_due_at <= NOW()
              AND p.do_not_contact = FALSE
              AND (:org_id IS NULL OR p.organization_id = :org_id)
            ORDER BY ce.next_step_due_at
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "org_id": organization_id,
            "limit": limit
        }).fetchall()

        return [dict(r._mapping) for r in results]

    async def advance_cadence_step(
        self,
        enrollment_id: str,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Advance a cadence enrollment to the next step."""
        # Get current enrollment and cadence info
        info_query = text("""
            SELECT
                ce.*,
                c.id as cadence_id,
                (SELECT MAX(step_order) FROM rw_cadence_step WHERE cadence_id = c.id) as max_step
            FROM rw_cadence_enrollment ce
            JOIN rw_cadence c ON c.id = ce.cadence_id
            WHERE ce.id = :enrollment_id
        """)
        info = self.db.execute(info_query, {"enrollment_id": enrollment_id}).fetchone()

        if not info:
            raise ValueError(f"Enrollment {enrollment_id} not found")

        next_step = info.current_step + 1

        if next_step > info.max_step:
            # Cadence completed
            update_query = text("""
                UPDATE rw_cadence_enrollment
                SET status = 'COMPLETED',
                    completed_at = NOW(),
                    steps_executed = steps_executed + 1,
                    updated_at = NOW()
                WHERE id = :enrollment_id
                RETURNING status, completed_at
            """)
            result = self.db.execute(update_query, {"enrollment_id": enrollment_id}).fetchone()

            self.db.commit()
            return {
                "enrollment_id": enrollment_id,
                "status": "COMPLETED",
                "completed_at": result.completed_at.isoformat()
            }

        # Get next step timing
        step_query = text("""
            SELECT min_days_after_prev FROM rw_cadence_step
            WHERE cadence_id = :cadence_id AND step_order = :step_order
        """)
        step = self.db.execute(step_query, {
            "cadence_id": info.cadence_id,
            "step_order": next_step
        }).fetchone()

        next_due = datetime.now(timezone.utc) + timedelta(days=step.min_days_after_prev)

        update_query = text("""
            UPDATE rw_cadence_enrollment
            SET current_step = :next_step,
                completed_steps = array_append(completed_steps, :completed_step),
                next_step_due_at = :next_due,
                last_step_at = NOW(),
                steps_executed = steps_executed + 1,
                updated_at = NOW()
            WHERE id = :enrollment_id
            RETURNING current_step, next_step_due_at
        """)

        result = self.db.execute(update_query, {
            "enrollment_id": enrollment_id,
            "next_step": next_step,
            "completed_step": info.current_step,
            "next_due": next_due
        }).fetchone()

        # Log event
        await self._log_event(
            EventType.CADENCE_STEP_DUE,
            person_id=info.person_id,
            user_id=user_id,
            payload={
                "enrollment_id": enrollment_id,
                "step_completed": info.current_step,
                "next_step": next_step
            }
        )

        self.db.commit()

        return {
            "enrollment_id": enrollment_id,
            "current_step": result.current_step,
            "next_step_due_at": result.next_step_due_at.isoformat()
        }

    async def pause_cadence(
        self,
        enrollment_id: str,
        reason: Optional[str] = None,
        pause_until: Optional[datetime] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Pause a cadence enrollment."""
        query = text("""
            UPDATE rw_cadence_enrollment
            SET status = 'PAUSED',
                paused_at = NOW(),
                paused_until = :pause_until,
                pause_reason = :reason,
                updated_at = NOW()
            WHERE id = :enrollment_id
            RETURNING person_id, status, paused_at
        """)

        result = self.db.execute(query, {
            "enrollment_id": enrollment_id,
            "pause_until": pause_until,
            "reason": reason
        }).fetchone()

        self.db.commit()

        return {
            "enrollment_id": enrollment_id,
            "status": "PAUSED",
            "paused_at": result.paused_at.isoformat()
        }

    # =========================================================================
    # PLAYBOOK MANAGEMENT
    # =========================================================================

    async def _evaluate_playbook_triggers(
        self,
        person_id: str,
        signal_id: Optional[str] = None,
        event_id: Optional[str] = None
    ) -> Optional[str]:
        """Evaluate if any playbooks should be triggered for a person."""
        # Get person info and timing score
        person_query = text("""
            SELECT
                p.person_type,
                p.relationship_stage,
                ri.timing_score
            FROM rw_person p
            LEFT JOIN rw_relationship_intel ri ON ri.person_id = p.id
            WHERE p.id = :person_id
        """)
        person = self.db.execute(person_query, {"person_id": person_id}).fetchone()

        if not person:
            return None

        # Get latest signal if provided
        signal_type = None
        if signal_id:
            signal_query = text("SELECT signal_type FROM rw_signal WHERE id = :id")
            signal = self.db.execute(signal_query, {"id": signal_id}).fetchone()
            if signal:
                signal_type = signal.signal_type

        # Get matching playbooks
        playbook_query = text("""
            SELECT * FROM rw_playbook
            WHERE is_active = TRUE
              AND person_type = :person_type
            ORDER BY priority DESC
        """)
        playbooks = self.db.execute(playbook_query, {
            "person_type": person.person_type
        }).fetchall()

        for playbook in playbooks:
            # Check cooldown
            cooldown_query = text("""
                SELECT 1 FROM rw_playbook_run
                WHERE playbook_id = :playbook_id
                  AND person_id = :person_id
                  AND created_at > NOW() - (:cooldown || ' days')::INTERVAL
                LIMIT 1
            """)
            cooldown_check = self.db.execute(cooldown_query, {
                "playbook_id": playbook.id,
                "person_id": person_id,
                "cooldown": playbook.cooldown_days
            }).fetchone()

            if cooldown_check:
                continue  # Skip - in cooldown period

            # Parse trigger config
            trigger_config = playbook.trigger_config
            if isinstance(trigger_config, str):
                trigger_config = json.loads(trigger_config)

            triggered = False

            # Check timing score threshold
            if trigger_config.get("timing_score_min"):
                if (person.timing_score or 0) >= trigger_config["timing_score_min"]:
                    triggered = True

            # Check signal types
            if trigger_config.get("signal_types") and signal_type:
                if signal_type in trigger_config["signal_types"]:
                    triggered = True

            # Check stage requirements
            if trigger_config.get("stage_in"):
                if person.relationship_stage not in trigger_config["stage_in"]:
                    triggered = False

            if trigger_config.get("stage_not_in"):
                if person.relationship_stage in trigger_config["stage_not_in"]:
                    triggered = False

            if triggered:
                # Create playbook run
                run_id = await self._start_playbook_run(
                    playbook.id,
                    person_id,
                    signal_id=signal_id,
                    event_id=event_id
                )
                return run_id

        return None

    async def _start_playbook_run(
        self,
        playbook_id: str,
        person_id: str,
        signal_id: Optional[str] = None,
        event_id: Optional[str] = None
    ) -> str:
        """Start a playbook run."""
        run_id = str(uuid.uuid4())

        # Get playbook actions count
        playbook_query = text("SELECT actions FROM rw_playbook WHERE id = :id")
        playbook = self.db.execute(playbook_query, {"id": playbook_id}).fetchone()
        actions = playbook.actions
        if isinstance(actions, str):
            actions = json.loads(actions)

        query = text("""
            INSERT INTO rw_playbook_run (
                id, playbook_id, person_id,
                triggered_by_signal_id, triggered_by_event_id,
                status, actions_total
            ) VALUES (
                :id, :playbook_id, :person_id,
                :signal_id, :event_id,
                'STARTED', :actions_total
            )
            RETURNING id, created_at
        """)

        result = self.db.execute(query, {
            "id": run_id,
            "playbook_id": playbook_id,
            "person_id": person_id,
            "signal_id": signal_id,
            "event_id": event_id,
            "actions_total": len(actions)
        }).fetchone()

        # Log event
        await self._log_event(
            EventType.PLAYBOOK_TRIGGERED,
            person_id=person_id,
            payload={
                "playbook_run_id": run_id,
                "playbook_id": playbook_id,
                "actions_count": len(actions)
            }
        )

        # Pause any active cadences for this person
        pause_query = text("""
            UPDATE rw_cadence_enrollment
            SET status = 'PAUSED',
                paused_at = NOW(),
                paused_until = NOW() + '14 days'::INTERVAL,
                pause_reason = 'Playbook triggered: ' || :run_id
            WHERE person_id = :person_id AND status = 'ACTIVE'
        """)
        self.db.execute(pause_query, {
            "person_id": person_id,
            "run_id": run_id
        })

        return run_id

    async def get_playbook_runs(
        self,
        person_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get playbook runs."""
        query = text("""
            SELECT
                pr.*,
                pb.key as playbook_key,
                pb.name as playbook_name,
                p.display_name as person_name
            FROM rw_playbook_run pr
            JOIN rw_playbook pb ON pb.id = pr.playbook_id
            JOIN rw_person p ON p.id = pr.person_id
            WHERE (:person_id IS NULL OR pr.person_id = :person_id)
              AND (:status IS NULL OR pr.status = :status)
            ORDER BY pr.created_at DESC
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "person_id": person_id,
            "status": status,
            "limit": limit
        }).fetchall()

        return [dict(r._mapping) for r in results]

    # =========================================================================
    # TASK MANAGEMENT
    # =========================================================================

    async def create_task(
        self,
        data: TaskCreate,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a task."""
        task_id = str(uuid.uuid4())

        query = text("""
            INSERT INTO rw_task (
                id, organization_id, person_id,
                title, description, task_type,
                priority, due_at, reminder_at,
                assigned_to, source_type, source_id
            ) VALUES (
                :id, :organization_id, :person_id,
                :title, :description, :task_type,
                :priority, :due_at, :reminder_at,
                :assigned_to, :source_type, :source_id
            )
            RETURNING id, created_at
        """)

        result = self.db.execute(query, {
            "id": task_id,
            "organization_id": data.organization_id,
            "person_id": data.person_id,
            "title": data.title,
            "description": data.description,
            "task_type": data.task_type,
            "priority": data.priority.value if data.priority else "MEDIUM",
            "due_at": data.due_at,
            "reminder_at": data.reminder_at,
            "assigned_to": data.assigned_to or user_id,
            "source_type": data.source_type,
            "source_id": data.source_id,
        }).fetchone()

        self.db.commit()

        return {
            "id": task_id,
            "created_at": result.created_at.isoformat()
        }

    async def get_tasks(
        self,
        person_id: Optional[str] = None,
        assigned_to: Optional[int] = None,
        status: Optional[TaskStatus] = None,
        overdue_only: bool = False,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get tasks with filters."""
        filters = ["1=1"]
        params = {"limit": limit}

        if person_id:
            filters.append("t.person_id = :person_id")
            params["person_id"] = person_id

        if assigned_to:
            filters.append("t.assigned_to = :assigned_to")
            params["assigned_to"] = assigned_to

        if status:
            filters.append("t.status = :status")
            params["status"] = status.value
        else:
            filters.append("t.status IN ('PENDING', 'IN_PROGRESS')")

        if overdue_only:
            filters.append("t.due_at < NOW()")

        where_clause = " AND ".join(filters)

        query = text(f"""
            SELECT
                t.*,
                p.display_name as person_name,
                u.full_name as assigned_to_name
            FROM rw_task t
            LEFT JOIN rw_person p ON p.id = t.person_id
            LEFT JOIN users u ON u.id = t.assigned_to
            WHERE {where_clause}
            ORDER BY
                CASE t.priority
                    WHEN 'URGENT' THEN 1
                    WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3
                    ELSE 4
                END,
                t.due_at NULLS LAST
            LIMIT :limit
        """)

        results = self.db.execute(query, params).fetchall()
        return [dict(r._mapping) for r in results]

    async def complete_task(
        self,
        task_id: str,
        outcome: Optional[str] = None,
        outcome_notes: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Complete a task."""
        query = text("""
            UPDATE rw_task
            SET status = 'COMPLETED',
                completed_at = NOW(),
                completed_by = :user_id,
                outcome = :outcome,
                outcome_notes = :outcome_notes,
                updated_at = NOW()
            WHERE id = :task_id
            RETURNING id, person_id, status, completed_at
        """)

        result = self.db.execute(query, {
            "task_id": task_id,
            "user_id": user_id,
            "outcome": outcome,
            "outcome_notes": outcome_notes
        }).fetchone()

        # Log event
        if result.person_id:
            await self._log_event(
                EventType.TASK_COMPLETED,
                person_id=result.person_id,
                user_id=user_id,
                payload={"task_id": task_id, "outcome": outcome}
            )

        self.db.commit()

        return {
            "id": task_id,
            "status": "COMPLETED",
            "completed_at": result.completed_at.isoformat()
        }

    # =========================================================================
    # NOTE MANAGEMENT
    # =========================================================================

    async def create_note(
        self,
        data: NoteCreate,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a note."""
        note_id = str(uuid.uuid4())

        query = text("""
            INSERT INTO rw_note (
                id, person_id, content, note_type,
                is_private, pinned, created_by
            ) VALUES (
                :id, :person_id, :content, :note_type,
                :is_private, :pinned, :created_by
            )
            RETURNING id, created_at
        """)

        result = self.db.execute(query, {
            "id": note_id,
            "person_id": data.person_id,
            "content": data.content,
            "note_type": data.note_type,
            "is_private": data.is_private,
            "pinned": data.pinned,
            "created_by": user_id,
        }).fetchone()

        # Log event
        await self._log_event(
            EventType.NOTE_ADDED,
            person_id=data.person_id,
            user_id=user_id,
            payload={"note_id": note_id, "note_type": data.note_type}
        )

        self.db.commit()

        return {
            "id": note_id,
            "created_at": result.created_at.isoformat()
        }

    async def get_notes(
        self,
        person_id: str,
        note_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get notes for a person."""
        query = text("""
            SELECT
                n.*,
                u.full_name as created_by_name
            FROM rw_note n
            LEFT JOIN users u ON u.id = n.created_by
            WHERE n.person_id = :person_id
              AND (:note_type IS NULL OR n.note_type = :note_type)
            ORDER BY n.pinned DESC, n.created_at DESC
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "person_id": person_id,
            "note_type": note_type,
            "limit": limit
        }).fetchall()

        return [dict(r._mapping) for r in results]

    # =========================================================================
    # CONTACT PREFERENCE LEARNING
    # =========================================================================

    async def record_comm_outcome(
        self,
        data: CommOutcomeCreate
    ) -> Dict[str, Any]:
        """Record a communication outcome for learning."""
        outcome_id = str(uuid.uuid4())

        # Calculate day of week and minute of day
        sent_dow = data.sent_at.weekday()  # 0 = Monday
        sent_minute = data.sent_at.hour * 60 + data.sent_at.minute

        query = text("""
            INSERT INTO rw_comm_outcome (
                id, person_id, channel, direction,
                sent_at, sent_day_of_week, sent_minute_of_day,
                template_key, campaign_id, message_preview
            ) VALUES (
                :id, :person_id, :channel, :direction,
                :sent_at, :sent_dow, :sent_minute,
                :template_key, :campaign_id, :message_preview
            )
            RETURNING id, created_at
        """)

        result = self.db.execute(query, {
            "id": outcome_id,
            "person_id": data.person_id,
            "channel": data.channel.value,
            "direction": data.direction,
            "sent_at": data.sent_at,
            "sent_dow": sent_dow,
            "sent_minute": sent_minute,
            "template_key": data.template_key,
            "campaign_id": data.campaign_id,
            "message_preview": data.message_preview,
        }).fetchone()

        # Update total outreach count
        update_query = text("""
            UPDATE rw_contact_preference
            SET total_outreach_count = total_outreach_count + 1,
                updated_at = NOW()
            WHERE person_id = :person_id
        """)
        self.db.execute(update_query, {"person_id": data.person_id})

        self.db.commit()

        return {
            "id": outcome_id,
            "created_at": result.created_at.isoformat()
        }

    async def update_comm_outcome(
        self,
        outcome_id: str,
        opened_at: Optional[datetime] = None,
        clicked_at: Optional[datetime] = None,
        replied_at: Optional[datetime] = None,
        booked_meeting_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Update a communication outcome with response data."""
        updates = []
        params = {"outcome_id": outcome_id}
        score = 0

        if opened_at:
            updates.append("opened_at = :opened_at")
            params["opened_at"] = opened_at
            score += 15

        if clicked_at:
            updates.append("clicked_at = :clicked_at")
            params["clicked_at"] = clicked_at
            score += 25

        if replied_at:
            updates.append("replied_at = :replied_at")
            params["replied_at"] = replied_at
            score += 40

        if booked_meeting_at:
            updates.append("booked_meeting_at = :booked_meeting_at")
            params["booked_meeting_at"] = booked_meeting_at
            score += 20

        updates.append("outcome_score = outcome_score + :score")
        params["score"] = score

        query = text(f"""
            UPDATE rw_comm_outcome
            SET {', '.join(updates)}
            WHERE id = :outcome_id
            RETURNING person_id, outcome_score
        """)

        result = self.db.execute(query, params).fetchone()

        # Update contact preference response count if replied
        if replied_at and result:
            update_query = text("""
                UPDATE rw_contact_preference
                SET total_response_count = total_response_count + 1,
                    last_response_at = :replied_at,
                    updated_at = NOW()
                WHERE person_id = :person_id
            """)
            self.db.execute(update_query, {
                "person_id": result.person_id,
                "replied_at": replied_at
            })

        self.db.commit()

        return {
            "outcome_id": outcome_id,
            "outcome_score": result.outcome_score
        }

    async def get_best_contact_time(
        self,
        person_id: str
    ) -> Dict[str, Any]:
        """Get the best time to contact a person based on preferences and history."""
        # Get explicit preferences
        pref_query = text("""
            SELECT * FROM rw_contact_preference WHERE person_id = :person_id
        """)
        pref = self.db.execute(pref_query, {"person_id": person_id}).fetchone()

        # Get person type for defaults
        person_query = text("""
            SELECT person_type FROM rw_person WHERE id = :person_id
        """)
        person = self.db.execute(person_query, {"person_id": person_id}).fetchone()

        result = {
            "person_id": person_id,
            "recommended_channel": None,
            "recommended_time": None,
            "recommended_day": None,
            "reasoning": []
        }

        if pref:
            # Use explicit preferences first
            if pref.preferred_time_start and pref.preferred_time_end:
                result["recommended_time"] = f"{pref.preferred_time_start} - {pref.preferred_time_end}"
                result["reasoning"].append("Using explicit time preference")

            if pref.preferred_days:
                days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
                result["recommended_day"] = [days[d] for d in pref.preferred_days]
                result["reasoning"].append("Using explicit day preference")

            # Use learned best time
            if pref.best_contact_minute and not result.get("recommended_time"):
                hours = pref.best_contact_minute // 60
                minutes = pref.best_contact_minute % 60
                result["recommended_time"] = f"{hours:02d}:{minutes:02d}"
                result["reasoning"].append("Using learned optimal time")

            if pref.best_channel:
                result["recommended_channel"] = pref.best_channel
                result["reasoning"].append("Using learned best channel")

            # Use preferred channels
            if pref.preferred_channels and not result.get("recommended_channel"):
                result["recommended_channel"] = pref.preferred_channels[0]
                result["reasoning"].append("Using explicit channel preference")

        # Fall back to persona defaults
        if not result.get("recommended_time") and person:
            if person.person_type == "LOAN_OFFICER":
                result["recommended_time"] = "10:00 - 11:30"
                result["recommended_day"] = ["Tue", "Wed", "Thu"]
                result["reasoning"].append("Using LO default window")
            else:
                result["recommended_time"] = "08:30 - 10:00"
                result["recommended_day"] = ["Mon", "Tue", "Wed", "Thu"]
                result["reasoning"].append("Using Realtor default window")

        if not result.get("recommended_channel"):
            result["recommended_channel"] = "EMAIL"
            result["reasoning"].append("Defaulting to email")

        return result

    # =========================================================================
    # NEXT BEST ACTION
    # =========================================================================

    async def get_next_best_action(
        self,
        person_id: str
    ) -> Dict[str, Any]:
        """Get AI-powered next best action recommendation."""
        # Get person summary
        person = await self.get_person_summary(person_id)
        if not person:
            return {"error": "Person not found"}

        # Get timing intelligence
        timing = await self.get_timing_intelligence(person_id)

        # Get open objections
        objections = await self.get_objections(person_id, status="OPEN")

        # Get recent notes
        notes = await self.get_notes(person_id, limit=5)

        # Get contact preferences
        contact_time = await self.get_best_contact_time(person_id)

        # Get mutual connections
        connections = await self.get_top_connections(person_id, limit=3)

        # Build recommendation based on timing score and context
        recommendation = {
            "person_id": person_id,
            "person_name": person.get("display_name"),
            "timing_score": timing.get("timing_score", 0) if timing else 0,
            "timing_grade": timing.get("timing_grade", "COLD") if timing else "COLD",
            "recommended_channel": contact_time.get("recommended_channel"),
            "recommended_time": contact_time.get("recommended_time"),
            "reasoning": []
        }

        timing_score = timing.get("timing_score", 0) if timing else 0

        # High intent - prioritize immediate action
        if timing_score >= TIMING_THRESHOLD_HOT:
            recommendation["message_goal"] = "book_meeting"
            recommendation["urgency"] = "HIGH"
            recommendation["reasoning"].append(f"Hot lead (score: {timing_score}) - prioritize meeting booking")
            if timing and timing.get("last_signal_type"):
                recommendation["reasoning"].append(f"Recent signal: {timing['last_signal_type']}")

        # Warm - accelerate nurture
        elif timing_score >= TIMING_THRESHOLD_WARM:
            recommendation["message_goal"] = "value"
            recommendation["urgency"] = "MEDIUM"
            recommendation["reasoning"].append(f"Warm lead (score: {timing_score}) - provide value")

        # Cool/Cold - nurture
        else:
            recommendation["message_goal"] = "micro_yes"
            recommendation["urgency"] = "LOW"
            recommendation["reasoning"].append(f"Nurture mode (score: {timing_score})")

        # Add objection context
        if objections:
            top_objection = objections[0]
            recommendation["open_objection"] = {
                "category": top_objection["category"],
                "severity": top_objection["severity"],
                "statement": top_objection.get("statement")
            }
            recommendation["reasoning"].append(f"Has {len(objections)} open objection(s) - tailor messaging")

        # Add connection context
        if connections:
            recommendation["top_connection"] = {
                "name": connections[0].get("display_name"),
                "strength": connections[0].get("total_strength")
            }
            recommendation["reasoning"].append("Mutual connection available for warm intro")

        return recommendation

    # =========================================================================
    # STATISTICS & REPORTING
    # =========================================================================

    async def get_workflow_stats(
        self,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get aggregate workflow statistics."""
        base_filter = "(:org_id IS NULL OR p.organization_id = :org_id)"
        params = {"org_id": organization_id}

        # Total people by type
        type_query = text(f"""
            SELECT person_type, COUNT(*) as count
            FROM rw_person p
            WHERE {base_filter}
            GROUP BY person_type
        """)
        type_results = self.db.execute(type_query, params).fetchall()
        by_type = {r.person_type: r.count for r in type_results}

        # By stage
        stage_query = text(f"""
            SELECT relationship_stage, COUNT(*) as count
            FROM rw_person p
            WHERE {base_filter}
            GROUP BY relationship_stage
        """)
        stage_results = self.db.execute(stage_query, params).fetchall()
        by_stage = {r.relationship_stage: r.count for r in stage_results}

        # Hot/warm counts
        score_query = text(f"""
            SELECT
                COUNT(CASE WHEN ri.timing_score >= :hot THEN 1 END) as hot,
                COUNT(CASE WHEN ri.timing_score >= :warm AND ri.timing_score < :hot THEN 1 END) as warm
            FROM rw_person p
            LEFT JOIN rw_relationship_intel ri ON ri.person_id = p.id
            WHERE {base_filter}
        """)
        score_result = self.db.execute(score_query, {
            **params,
            "hot": TIMING_THRESHOLD_HOT,
            "warm": TIMING_THRESHOLD_WARM
        }).fetchone()

        # Cadences active
        cadence_query = text(f"""
            SELECT COUNT(*) as count
            FROM rw_cadence_enrollment ce
            JOIN rw_person p ON p.id = ce.person_id
            WHERE ce.status = 'ACTIVE' AND {base_filter}
        """)
        cadence_result = self.db.execute(cadence_query, params).fetchone()

        # Tasks
        task_query = text(f"""
            SELECT
                COUNT(*) as pending,
                COUNT(CASE WHEN due_at < NOW() THEN 1 END) as overdue
            FROM rw_task t
            LEFT JOIN rw_person p ON p.id = t.person_id
            WHERE t.status IN ('PENDING', 'IN_PROGRESS')
              AND {base_filter}
        """)
        task_result = self.db.execute(task_query, params).fetchone()

        # Meetings upcoming
        meeting_query = text(f"""
            SELECT COUNT(*) as count
            FROM rw_meeting m
            JOIN rw_person p ON p.id = m.person_id
            WHERE m.status = 'SCHEDULED'
              AND m.scheduled_at > NOW()
              AND m.scheduled_at < NOW() + '7 days'::INTERVAL
              AND {base_filter}
        """)
        meeting_result = self.db.execute(meeting_query, params).fetchone()

        # Open objections
        objection_query = text(f"""
            SELECT COUNT(*) as count
            FROM rw_objection o
            JOIN rw_person p ON p.id = o.person_id
            WHERE o.status = 'OPEN' AND {base_filter}
        """)
        objection_result = self.db.execute(objection_query, params).fetchone()

        # Active playbook runs
        playbook_query = text(f"""
            SELECT COUNT(*) as count
            FROM rw_playbook_run pr
            JOIN rw_person p ON p.id = pr.person_id
            WHERE pr.status IN ('STARTED', 'IN_PROGRESS')
              AND {base_filter}
        """)
        playbook_result = self.db.execute(playbook_query, params).fetchone()

        return {
            "total_people": sum(by_type.values()),
            "by_type": by_type,
            "by_stage": by_stage,
            "hot_leads": score_result.hot or 0,
            "warm_leads": score_result.warm or 0,
            "cadences_active": cadence_result.count or 0,
            "tasks_pending": task_result.pending or 0,
            "tasks_overdue": task_result.overdue or 0,
            "meetings_upcoming": meeting_result.count or 0,
            "objections_open": objection_result.count or 0,
            "playbook_runs_active": playbook_result.count or 0
        }

    # =========================================================================
    # EVENT LOGGING
    # =========================================================================

    async def _log_event(
        self,
        event_type: EventType,
        person_id: Optional[str] = None,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a CRM event."""
        event_id = str(uuid.uuid4())

        query = text("""
            INSERT INTO rw_crm_event (
                id, event_type, person_id, user_id, organization_id, payload
            ) VALUES (
                :id, :event_type, :person_id, :user_id, :org_id, :payload
            )
            RETURNING id
        """)

        self.db.execute(query, {
            "id": event_id,
            "event_type": event_type.value,
            "person_id": person_id,
            "user_id": user_id,
            "org_id": organization_id,
            "payload": json.dumps(payload) if payload else "{}"
        })

        return event_id

    async def get_events(
        self,
        person_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get CRM events."""
        query = text("""
            SELECT * FROM rw_crm_event
            WHERE (:person_id IS NULL OR person_id = :person_id)
              AND (:event_type IS NULL OR event_type = :event_type)
            ORDER BY occurred_at DESC
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "person_id": person_id,
            "event_type": event_type.value if event_type else None,
            "limit": limit
        }).fetchall()

        return [dict(r._mapping) for r in results]
