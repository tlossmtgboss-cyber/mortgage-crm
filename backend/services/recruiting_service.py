"""
Recruiting Service
Candidate pipeline management for Master Manager Platform Phase 2.
"""

from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Optional, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from dataclasses import dataclass
import logging
import json
import re
import secrets
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

logger = logging.getLogger(__name__)

# Valid state transitions: maps current status → set of allowed next statuses.
# Prevents invalid jumps like "new" → "hired" without going through the pipeline.
VALID_TRANSITIONS = {
    "new": {"screening", "phone_screen", "rejected", "withdrawn"},
    "screening": {"phone_screen", "rejected", "withdrawn"},
    "phone_screen": {"interview", "rejected", "withdrawn"},
    "interview": {"assessment", "offer", "rejected", "withdrawn", "not_selected"},
    "assessment": {"offer", "rejected", "withdrawn", "not_selected"},
    "offer": {"hired", "rejected", "withdrawn", "not_selected"},
    "hired": set(),  # Terminal state
    "rejected": {"new"},  # Allow re-opening
    "withdrawn": {"new"},  # Allow re-opening
    "not_selected": {"new"},  # Allow re-opening
}

# Score gates: minimum assessment score and required quizzes to advance to each stage
SCORE_GATES = {
    "interview": {"min_score": 4.0, "required_quizzes": ["screening"]},
    "assessment": {"min_score": 5.0, "required_quizzes": ["screening", "phone_screen"]},
    "offer": {"min_score": 6.0, "required_quizzes": ["screening", "phone_screen", "interview"]},
}


@dataclass
class PipelineMetrics:
    """Recruiting pipeline metrics."""
    total_candidates: int
    by_status: Dict[str, int]
    avg_time_to_hire_days: float
    conversion_rates: Dict[str, float]
    open_positions: int
    pending_offers: int


@dataclass
class CandidateDetail:
    """Detailed candidate information."""
    id: int
    name: str
    email: str
    phone: Optional[str]
    status: str
    target_role: Optional[str]
    source: Optional[str]
    applied_at: datetime
    overall_score: Optional[float]
    interviews_count: int
    has_offer: bool


class RecruitingService:
    """
    Service for managing the recruiting pipeline.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # PIPELINE OVERVIEW
    # =========================================================================

    async def get_pipeline_metrics(
        self,
        organization_id: int,
        days: int = 90
    ) -> PipelineMetrics:
        """Get recruiting pipeline metrics."""

        # Count by status
        status_query = text("""
            SELECT
                status,
                COUNT(*) as count
            FROM mm_candidates
            WHERE is_active = true
            AND applied_at >= CURRENT_DATE - :days
            AND organization_id = :org_id
            GROUP BY status
        """)
        status_results = self.db.execute(status_query, {
            "days": days,
            "org_id": organization_id
        }).fetchall()

        by_status = {r.status: r.count for r in status_results}
        total = sum(by_status.values())

        # Average time to hire
        time_query = text("""
            SELECT
                AVG(EXTRACT(EPOCH FROM (hired_at - applied_at)) / 86400) as avg_days
            FROM mm_candidates
            WHERE hired_at IS NOT NULL
            AND applied_at >= CURRENT_DATE - :days
            AND organization_id = :org_id
        """)
        time_result = self.db.execute(time_query, {
            "days": days,
            "org_id": organization_id
        }).fetchone()

        # Conversion rates
        funnel_query = text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status IN ('screening', 'phone_screen', 'interview', 'assessment', 'offer', 'hired') THEN 1 END) as screened,
                COUNT(CASE WHEN status IN ('interview', 'assessment', 'offer', 'hired') THEN 1 END) as interviewed,
                COUNT(CASE WHEN status IN ('offer', 'hired') THEN 1 END) as offered,
                COUNT(CASE WHEN status = 'hired' THEN 1 END) as hired
            FROM mm_candidates
            WHERE is_active = true
            AND applied_at >= CURRENT_DATE - :days
            AND organization_id = :org_id
        """)
        funnel = self.db.execute(funnel_query, {
            "days": days,
            "org_id": organization_id
        }).fetchone()

        def calc_rate(num, denom):
            return round((num / denom) * 100, 1) if denom > 0 else 0

        conversion_rates = {
            "apply_to_screen": calc_rate(funnel.screened, funnel.total),
            "screen_to_interview": calc_rate(funnel.interviewed, funnel.screened),
            "interview_to_offer": calc_rate(funnel.offered, funnel.interviewed),
            "offer_to_hire": calc_rate(funnel.hired, funnel.offered),
            "overall": calc_rate(funnel.hired, funnel.total)
        }

        # Open positions
        positions_query = text("""
            SELECT COUNT(*) as count
            FROM mm_job_postings
            WHERE is_published = true
            AND (expires_at IS NULL OR expires_at > CURRENT_DATE)
            AND organization_id = :org_id
        """)
        positions = self.db.execute(positions_query, {"org_id": organization_id}).fetchone()

        # Pending offers
        offers_query = text("""
            SELECT COUNT(*) as count
            FROM mm_offers
            WHERE status IN ('sent', 'viewed', 'negotiating')
            AND organization_id = :org_id
        """)
        offers = self.db.execute(offers_query, {"org_id": organization_id}).fetchone()

        return PipelineMetrics(
            total_candidates=total,
            by_status=by_status,
            avg_time_to_hire_days=round(time_result.avg_days or 0, 1),
            conversion_rates=conversion_rates,
            open_positions=positions.count or 0,
            pending_offers=offers.count or 0
        )

    # =========================================================================
    # CANDIDATES
    # =========================================================================

    async def get_candidates(
        self,
        organization_id: int,
        status: Optional[str] = None,
        role_id: Optional[int] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get candidates with filters."""

        query = text("""
            SELECT
                c.id,
                c.first_name,
                c.last_name,
                c.email,
                c.phone,
                c.status,
                c.source,
                c.target_role_name,
                c.applied_at,
                c.overall_score,
                c.years_experience,
                c.has_mortgage_experience,
                c.placement_recommendation,
                (SELECT COUNT(*) FROM mm_interviews WHERE candidate_id = c.id AND organization_id = :org_id) as interview_count,
                (SELECT COUNT(*) FROM mm_offers WHERE candidate_id = c.id AND organization_id = :org_id AND status NOT IN ('declined', 'withdrawn', 'expired')) as offer_count,
                ras.overall_score as assessment_score
            FROM mm_candidates c
            LEFT JOIN recruit_assessment_scores ras ON ras.candidate_id = c.id
            WHERE c.is_active = true
            AND c.organization_id = :org_id
            AND (:status IS NULL OR c.status = :status)
            AND (:role_id IS NULL OR c.target_role_id = :role_id)
            AND (:source IS NULL OR c.source = :source)
            AND (:search IS NULL OR
                 c.first_name ILIKE '%' || :search || '%' OR
                 c.last_name ILIKE '%' || :search || '%' OR
                 c.email ILIKE '%' || :search || '%')
            ORDER BY c.applied_at DESC
            LIMIT :limit OFFSET :offset
        """)

        results = self.db.execute(query, {
            "org_id": organization_id,
            "status": status,
            "role_id": role_id,
            "source": source,
            "search": search,
            "limit": limit,
            "offset": offset
        }).fetchall()

        def get_grade(score):
            """Convert score to letter grade."""
            if score is None:
                return None
            if score >= 90:
                return "A"
            elif score >= 80:
                return "B+"
            elif score >= 70:
                return "B"
            elif score >= 60:
                return "C"
            elif score >= 50:
                return "D"
            else:
                return "F"

        return [
            {
                "id": r.id,
                "name": f"{r.first_name} {r.last_name}",
                "first_name": r.first_name,
                "last_name": r.last_name,
                "email": r.email,
                "phone": r.phone,
                "status": r.status,
                "source": r.source,
                "target_role": r.target_role_name,
                "applied_at": r.applied_at.isoformat() if r.applied_at else None,
                "overall_score": r.overall_score,
                "years_experience": r.years_experience,
                "has_mortgage_experience": r.has_mortgage_experience,
                "placement_recommendation": r.placement_recommendation,
                "interview_count": r.interview_count,
                "has_offer": r.offer_count > 0,
                "assessment_score": float(r.assessment_score) if r.assessment_score else None,
                "assessment_grade": get_grade(float(r.assessment_score)) if r.assessment_score else None
            }
            for r in results
        ]

    async def count_candidates(
        self,
        organization_id: int,
        status: Optional[str] = None,
        role_id: Optional[int] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count candidates matching the given filters (for pagination)."""
        result = self.db.execute(text("""
            SELECT COUNT(*) FROM mm_candidates c
            WHERE c.is_active = true
            AND c.organization_id = :org_id
            AND (:status IS NULL OR c.status = :status)
            AND (:role_id IS NULL OR c.target_role_id = :role_id)
            AND (:source IS NULL OR c.source = :source)
            AND (:search IS NULL OR
                 c.first_name ILIKE '%' || :search || '%' OR
                 c.last_name ILIKE '%' || :search || '%' OR
                 c.email ILIKE '%' || :search || '%')
        """), {
            "org_id": organization_id,
            "status": status,
            "role_id": role_id,
            "source": source,
            "search": search,
        }).scalar()
        return result or 0

    async def get_candidate_detail(
        self,
        candidate_id: int,
        organization_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get detailed candidate information."""

        query = text("""
            SELECT
                c.*,
                rd.role_name as target_role_full,
                rd.role_category,
                u.full_name as referrer_name
            FROM mm_candidates c
            LEFT JOIN mm_role_definitions rd ON rd.id = c.target_role_id
            LEFT JOIN users u ON u.id = c.referrer_user_id
            WHERE c.id = :id
            AND c.organization_id = :org_id
        """)

        result = self.db.execute(query, {
            "id": candidate_id,
            "org_id": organization_id
        }).fetchone()

        if not result:
            return None

        # Get interviews (org-scoped via candidate FK)
        interviews = self.db.execute(text("""
            SELECT
                i.id, i.interview_type, i.interview_round, i.title,
                i.scheduled_at, i.status, i.overall_score, i.recommendation,
                u.full_name as interviewer_name
            FROM mm_interviews i
            JOIN mm_candidates c ON c.id = i.candidate_id
                AND c.organization_id = :org_id
            LEFT JOIN users u ON u.id = i.primary_interviewer_id
            WHERE i.candidate_id = :id
            ORDER BY i.scheduled_at DESC
        """), {"id": candidate_id, "org_id": organization_id}).fetchall()

        # Get offers (org-scoped via candidate FK)
        offers = self.db.execute(text("""
            SELECT
                o.id, o.offer_number, o.role_title, o.salary_amount,
                o.status, o.sent_at, o.responded_at
            FROM mm_offers o
            JOIN mm_candidates c ON c.id = o.candidate_id
                AND c.organization_id = :org_id
            WHERE o.candidate_id = :id
            ORDER BY o.created_at DESC
        """), {"id": candidate_id, "org_id": organization_id}).fetchall()

        # Get activities (org-scoped via candidate FK)
        activities = self.db.execute(text("""
            SELECT
                a.id, a.activity_type, a.description, a.created_at,
                u.full_name as performed_by_name
            FROM mm_candidate_activities a
            JOIN mm_candidates c ON c.id = a.candidate_id
                AND c.organization_id = :org_id
            LEFT JOIN users u ON u.id = a.performed_by
            WHERE a.candidate_id = :id
            ORDER BY a.created_at DESC
            LIMIT 20
        """), {"id": candidate_id, "org_id": organization_id}).fetchall()

        # Get notes (exclude private notes — org-scoped via candidate FK)
        notes = self.db.execute(text("""
            SELECT
                n.id, n.note_type, n.content, n.is_private, n.created_at,
                u.full_name as author_name
            FROM mm_candidate_notes n
            JOIN mm_candidates c ON c.id = n.candidate_id
                AND c.organization_id = :org_id
            JOIN users u ON u.id = n.created_by
            WHERE n.candidate_id = :id AND (n.is_private = false OR n.is_private IS NULL)
            ORDER BY n.created_at DESC
        """), {"id": candidate_id, "org_id": organization_id}).fetchall()

        return {
            "id": result.id,
            "name": f"{result.first_name} {result.last_name}",
            "first_name": result.first_name,
            "last_name": result.last_name,
            "email": result.email,
            "phone": result.phone,
            "status": result.status,
            "source": result.source,
            "referrer_name": result.referrer_name,
            "target_role": result.target_role_full,
            "target_role_category": result.role_category,
            "placement_recommendation": result.placement_recommendation,
            "applied_at": result.applied_at.isoformat() if result.applied_at else None,
            "experience": {
                "years_total": result.years_experience,
                "years_mortgage": result.years_mortgage_experience,
                "has_mortgage": result.has_mortgage_experience,
                "previous_companies": result.previous_companies,
                "licenses": result.licenses
            },
            "scores": {
                "overall": result.overall_score,
                "vetting": result.vetting_score,
                "behavioral": result.behavioral_score,
                "technical": result.technical_score,
                "culture_fit": result.culture_fit_score,
                "interview": result.interview_score
            },
            "talent_profile": result.talent_profile,
            "resume_url": result.resume_url,
            "linkedin_url": result.linkedin_url,
            "interviews": [
                {
                    "id": i.id,
                    "type": i.interview_type,
                    "round": i.interview_round,
                    "title": i.title,
                    "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
                    "status": i.status,
                    "score": i.overall_score,
                    "recommendation": i.recommendation,
                    "interviewer": i.interviewer_name
                }
                for i in interviews
            ],
            "offers": [
                {
                    "id": o.id,
                    "offer_number": o.offer_number,
                    "role": o.role_title,
                    "salary": o.salary_amount,
                    "status": o.status,
                    "sent_at": o.sent_at.isoformat() if o.sent_at else None
                }
                for o in offers
            ],
            "activities": [
                {
                    "id": a.id,
                    "type": a.activity_type,
                    "description": a.description,
                    "performed_by": a.performed_by_name,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                }
                for a in activities
            ],
            "notes": [
                {
                    "id": n.id,
                    "type": n.note_type,
                    "content": n.content,
                    "is_private": n.is_private,
                    "author": n.author_name,
                    "created_at": n.created_at.isoformat() if n.created_at else None
                }
                for n in notes
            ]
        }

    async def create_candidate(
        self,
        data: Dict[str, Any],
        created_by: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Create a new candidate."""

        query = text("""
            INSERT INTO mm_candidates (
                organization_id, first_name, last_name, email, phone,
                source, referrer_user_id, target_role_id, target_role_name,
                years_experience, years_mortgage_experience, has_mortgage_experience,
                resume_url, linkedin_url, status, applied_at
            ) VALUES (
                :org_id, :first_name, :last_name, :email, :phone,
                :source, :referrer_id, :role_id, :role_name,
                :years_exp, :years_mortgage, :has_mortgage,
                :resume_url, :linkedin_url, 'new', CURRENT_TIMESTAMP
            )
            RETURNING id
        """)

        # Use created_by as referrer if not explicitly provided (the recruiter who creates the candidate)
        referrer_id = data.get("referrer_user_id") or created_by

        result = self.db.execute(query, {
            "org_id": organization_id,
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "source": data.get("source", "direct"),
            "referrer_id": referrer_id,
            "role_id": data.get("target_role_id"),
            "role_name": data.get("target_role_name"),
            "years_exp": data.get("years_experience"),
            "years_mortgage": data.get("years_mortgage_experience"),
            "has_mortgage": data.get("has_mortgage_experience", False),
            "resume_url": data.get("resume_url"),
            "linkedin_url": data.get("linkedin_url")
        }).fetchone()

        candidate_id = result.id

        # Log activity
        await self._log_activity(
            candidate_id=candidate_id,
            activity_type="applied",
            description="Candidate applied for position",
            performed_by=created_by,
            organization_id=organization_id
        )

        # Auto-create recruit portal workspace for the candidate
        portal_result = await self._create_portal_workspace(candidate_id, data.get("first_name"), data.get("last_name"))

        self.db.commit()

        return {
            "id": candidate_id,
            "status": "new",
            "portal_slug": portal_result.get("slug"),
            "portal_url": portal_result.get("portal_url")
        }

    def _check_score_gate(
        self,
        candidate_id: int,
        target_status: str,
        skip_gate: bool = False,
    ) -> Optional[str]:
        """Check if candidate meets score gate for target status.
        Returns error message if blocked, None if allowed."""
        if skip_gate:
            return None

        gate = SCORE_GATES.get(target_status)
        if not gate:
            return None

        # Check assessment score
        score_row = self.db.execute(text("""
            SELECT overall_score, quiz_count
            FROM recruit_assessment_scores
            WHERE candidate_id = :cid
        """), {"cid": candidate_id}).fetchone()

        if not score_row or score_row.overall_score is None:
            return f"Cannot advance to {target_status}: no assessment score on file. Complete required quizzes first."

        if float(score_row.overall_score) < gate["min_score"]:
            return (
                f"Cannot advance to {target_status}: overall score {score_row.overall_score:.1f} "
                f"is below minimum {gate['min_score']}"
            )

        # Check required quizzes completed
        for required_quiz in gate["required_quizzes"]:
            quiz_done = self.db.execute(text("""
                SELECT COUNT(*) as cnt
                FROM recruit_quiz_responses
                WHERE candidate_id = :cid AND disposition = :disp
            """), {"cid": candidate_id, "disp": required_quiz}).fetchone()

            if not quiz_done or quiz_done.cnt == 0:
                return f"Cannot advance to {target_status}: '{required_quiz}' quiz not completed"

        return None

    async def update_candidate_status(
        self,
        candidate_id: int,
        new_status: str,
        updated_by: int,
        *,
        organization_id: int,
        reason: Optional[str] = None,
        disposition_code: Optional[str] = None,
        skip_score_gate: bool = False
    ) -> Dict[str, Any]:
        """Update candidate status with optional OFCCP disposition tracking."""

        # Get current status with org isolation
        org_filter = "AND organization_id = :org_id"
        params = {"id": candidate_id, "org_id": organization_id}

        query = f"""
            SELECT status FROM mm_candidates WHERE id = :id {org_filter}
        """
        current = self.db.execute(text(query), params).fetchone()

        if not current:
            raise ValueError(f"Candidate {candidate_id} not found")

        old_status = current.status

        # State machine: enforce valid transitions
        allowed = VALID_TRANSITIONS.get(old_status)
        if allowed is not None and new_status not in allowed:
            allowed_list = ", ".join(sorted(allowed)) if allowed else "(none — terminal state)"
            raise ValueError(
                f"Invalid transition: '{old_status}' → '{new_status}'. "
                f"Allowed transitions from '{old_status}': {allowed_list}"
            )

        # Score gate check
        gate_error = self._check_score_gate(candidate_id, new_status, skip_score_gate)
        if gate_error:
            raise ValueError(gate_error)

        # NMLS gate for offer/hired stages
        if new_status in ("offer", "hired") and not skip_score_gate:
            from services.nmls_validation_service import NMLSValidationService
            nmls_service = NMLSValidationService(self.db)
            nmls_result = nmls_service.check_license_status(candidate_id, organization_id)
            if not nmls_result.is_valid:
                issue_msgs = "; ".join(i["message"] for i in nmls_result.issues)
                raise ValueError(f"NMLS validation failed: {issue_msgs}")

        # Build update query — include disposition fields when provided
        if disposition_code:
            query = f"""
                UPDATE mm_candidates
                SET status = :status,
                    status_changed_at = CURRENT_TIMESTAMP,
                    status_changed_by = :user_id,
                    disposition_code = :disposition_code,
                    disposition_date = CURRENT_TIMESTAMP,
                    disposition_by = :user_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id {org_filter}
            """
            self.db.execute(text(query), {
                "id": candidate_id,
                "status": new_status,
                "user_id": updated_by,
                "disposition_code": disposition_code,
                "org_id": organization_id,
            })
        else:
            query = f"""
                UPDATE mm_candidates
                SET status = :status,
                    status_changed_at = CURRENT_TIMESTAMP,
                    status_changed_by = :user_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id {org_filter}
            """
            self.db.execute(text(query), {
                "id": candidate_id,
                "status": new_status,
                "user_id": updated_by,
                "org_id": organization_id,
            })

        # Log activity
        description = f"Status changed from {old_status} to {new_status}"
        if reason:
            description += f": {reason}"
        if disposition_code:
            description += f" [disposition: {disposition_code}]"

        await self._log_activity(
            candidate_id=candidate_id,
            activity_type="status_change",
            description=description,
            performed_by=updated_by,
            organization_id=organization_id
        )

        # Insert audit log entry for disposition tracking
        if disposition_code:
            try:
                self.db.execute(text("""
                    INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details, created_at)
                    VALUES (:user_id, 'disposition_set', 'candidate', :candidate_id,
                            :details, CURRENT_TIMESTAMP)
                """), {
                    "user_id": updated_by,
                    "candidate_id": str(candidate_id),
                    "details": json.dumps({
                        "old_status": old_status,
                        "new_status": new_status,
                        "disposition_code": disposition_code,
                        "reason": reason,
                    }),
                })
            except Exception as e:
                logger.warning(f"Failed to insert audit log for disposition: {e}")

        self.db.commit()

        return {
            "candidate_id": candidate_id,
            "old_status": old_status,
            "new_status": new_status,
            "disposition_code": disposition_code,
        }

    # =========================================================================
    # JOB POSTINGS
    # =========================================================================

    async def get_job_postings(
        self,
        organization_id: int,
        is_published: Optional[bool] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get job postings."""

        query = text("""
            SELECT
                jp.id, jp.title, jp.slug, jp.summary,
                jp.is_published, jp.is_remote, jp.location,
                jp.employment_type, jp.salary_min, jp.salary_max,
                jp.views, jp.applications,
                jp.published_at, jp.expires_at, jp.created_at,
                rd.role_name, rd.role_category,
                (SELECT COUNT(*) FROM mm_candidates WHERE target_role_id = jp.role_definition_id AND organization_id = :org_id AND status NOT IN ('rejected', 'withdrawn', 'hired')) as active_candidates
            FROM mm_job_postings jp
            LEFT JOIN mm_role_definitions rd ON rd.id = jp.role_definition_id
            WHERE jp.organization_id = :org_id
            AND (:is_published IS NULL OR jp.is_published = :is_published)
            ORDER BY jp.created_at DESC
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "org_id": organization_id,
            "is_published": is_published,
            "limit": limit
        }).fetchall()

        return [
            {
                "id": r.id,
                "title": r.title,
                "slug": r.slug,
                "summary": r.summary,
                "role_name": r.role_name,
                "role_category": r.role_category,
                "is_published": r.is_published,
                "is_remote": r.is_remote,
                "location": r.location,
                "employment_type": r.employment_type,
                "salary_range": f"${r.salary_min:,} - ${r.salary_max:,}" if r.salary_min and r.salary_max else None,
                "views": r.views or 0,
                "applications": r.applications or 0,
                "active_candidates": r.active_candidates,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None
            }
            for r in results
        ]

    async def create_job_posting(
        self,
        data: Dict[str, Any],
        created_by: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Create a job posting."""
        import json
        import re

        # Generate slug from title
        slug = re.sub(r'[^a-z0-9]+', '-', data.get("title", "").lower()).strip('-')

        # Convert text fields to JSONB format (as arrays)
        def to_jsonb(val):
            if val is None:
                return None
            if isinstance(val, (list, dict)):
                return json.dumps(val)
            # Convert string to array of lines
            if isinstance(val, str):
                lines = [line.strip() for line in val.split(',') if line.strip()]
                if not lines:
                    lines = [val]
                return json.dumps(lines)
            return json.dumps([str(val)])

        query = text("""
            INSERT INTO mm_job_postings (
                organization_id, title, slug, role_definition_id,
                summary, description, requirements, responsibilities, benefits,
                salary_min, salary_max, salary_type,
                is_published, is_remote, location, employment_type,
                created_by
            ) VALUES (
                :org_id, :title, :slug, :role_id,
                :summary, :description, CAST(:requirements AS jsonb), CAST(:responsibilities AS jsonb), CAST(:benefits AS jsonb),
                :salary_min, :salary_max, :salary_type,
                :is_published, :is_remote, :location, :employment_type,
                :created_by
            )
            RETURNING id, slug
        """)

        result = self.db.execute(query, {
            "org_id": organization_id,
            "title": data.get("title"),
            "slug": slug,
            "role_id": data.get("role_definition_id"),
            "summary": data.get("summary"),
            "description": data.get("description"),
            "requirements": to_jsonb(data.get("requirements")),
            "responsibilities": to_jsonb(data.get("responsibilities")),
            "benefits": to_jsonb(data.get("benefits")),
            "salary_min": data.get("salary_min"),
            "salary_max": data.get("salary_max"),
            "salary_type": data.get("salary_type", "salary"),
            "is_published": data.get("is_published", False),
            "is_remote": data.get("is_remote", False),
            "location": data.get("location"),
            "employment_type": data.get("employment_type", "full_time"),
            "created_by": created_by
        }).fetchone()

        self.db.commit()

        return {"id": result.id, "slug": result.slug}

    # =========================================================================
    # INTERVIEWS
    # =========================================================================

    async def schedule_interview(
        self,
        candidate_id: int,
        data: Dict[str, Any],
        created_by: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Schedule an interview."""

        query = text("""
            INSERT INTO mm_interviews (
                organization_id, candidate_id,
                interview_type, interview_round, title,
                scheduled_at, duration_minutes, timezone,
                location, meeting_link,
                interviewer_user_ids, primary_interviewer_id,
                created_by
            ) VALUES (
                :org_id, :candidate_id,
                :type, :round, :title,
                :scheduled_at, :duration, :timezone,
                :location, :meeting_link,
                :interviewers, :primary_interviewer,
                :created_by
            )
            RETURNING id
        """)

        # Convert interviewer_user_ids to JSON string for JSONB column
        interviewer_ids = data.get("interviewer_user_ids", [])
        if not isinstance(interviewer_ids, str):
            interviewer_ids = json.dumps(interviewer_ids)

        result = self.db.execute(query, {
            "org_id": organization_id,
            "candidate_id": candidate_id,
            "type": data.get("interview_type", "video"),
            "round": data.get("interview_round", 1),
            "title": data.get("title"),
            "scheduled_at": data.get("scheduled_at"),
            "duration": data.get("duration_minutes", 30),
            "timezone": data.get("timezone", "America/New_York"),
            "location": data.get("location"),
            "meeting_link": data.get("meeting_link"),
            "interviewers": interviewer_ids,
            "primary_interviewer": data.get("primary_interviewer_id"),
            "created_by": created_by
        }).fetchone()

        interview_id = result.id

        # Update candidate status if still in early stage (org-scoped)
        org_filter = "AND organization_id = :org_id"
        update_params = {"id": candidate_id, "org_id": organization_id}
        query = f"""
            UPDATE mm_candidates
            SET status = CASE
                WHEN status IN ('new', 'screening', 'phone_screen') THEN 'interview'
                ELSE status
            END,
            updated_at = CURRENT_TIMESTAMP
            WHERE id = :id {org_filter}
        """
        self.db.execute(text(query), update_params)

        # Log activity
        await self._log_activity(
            candidate_id=candidate_id,
            activity_type="interview_scheduled",
            description=f"Interview scheduled for {data.get('scheduled_at')}",
            performed_by=created_by,
            organization_id=organization_id,
            interview_id=interview_id
        )

        self.db.commit()

        return {"id": interview_id}

    async def submit_interview_feedback(
        self,
        interview_id: int,
        interviewer_id: int,
        feedback: Dict[str, Any],
        organization_id: int
    ) -> Dict[str, Any]:
        """Submit feedback for an interview."""

        # Get current feedback with org isolation
        org_filter = "AND i.organization_id = :org_id"
        params = {"id": interview_id, "org_id": organization_id}

        query = f"""
            SELECT i.feedback, i.candidate_id FROM mm_interviews i WHERE i.id = :id {org_filter}
        """
        current = self.db.execute(text(query), params).fetchone()

        if not current:
            raise ValueError(f"Interview {interview_id} not found")

        # Merge feedback
        all_feedback = current.feedback or {}
        all_feedback[str(interviewer_id)] = feedback

        # Calculate overall score if all interviewers submitted
        overall_scores = [f.get("overall_score") for f in all_feedback.values() if f.get("overall_score")]
        overall_score = sum(overall_scores) / len(overall_scores) if overall_scores else None

        # Determine recommendation (hire if majority recommend)
        recommendations = [f.get("recommendation") for f in all_feedback.values() if f.get("recommendation")]
        hire_votes = len([r for r in recommendations if r in ("strong_hire", "hire")])
        no_hire_votes = len([r for r in recommendations if r in ("strong_no_hire", "no_hire")])
        recommendation = "hire" if hire_votes > no_hire_votes else "no_hire" if no_hire_votes > hire_votes else "undecided"

        # Update interview - convert feedback dict to JSON string for JSONB column
        update_params = {
            "id": interview_id,
            "feedback": json.dumps(all_feedback),
            "score": overall_score,
            "recommendation": recommendation
        }
        update_org_filter = "AND organization_id = :org_id"
        update_params["org_id"] = organization_id

        query = f"""
            UPDATE mm_interviews
            SET feedback = :feedback,
                overall_score = :score,
                recommendation = :recommendation,
                completed_at = CURRENT_TIMESTAMP,
                status = 'completed',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id {update_org_filter}
        """
        self.db.execute(text(query), update_params)

        # Log activity
        await self._log_activity(
            candidate_id=current.candidate_id,
            activity_type="feedback_submitted",
            description=f"Interview feedback submitted",
            performed_by=interviewer_id,
            organization_id=organization_id,
            interview_id=interview_id
        )

        self.db.commit()

        return {
            "interview_id": interview_id,
            "overall_score": overall_score,
            "recommendation": recommendation
        }

    # =========================================================================
    # OFFERS
    # =========================================================================

    async def create_offer(
        self,
        candidate_id: int,
        data: Dict[str, Any],
        created_by: int,
        organization_id: int
    ) -> Dict[str, Any]:
        """Create an offer for a candidate."""

        query = text("""
            INSERT INTO mm_offers (
                organization_id, candidate_id, job_posting_id,
                role_title, role_definition_id, department, reports_to_user_id,
                salary_amount, salary_type, bonus_amount, bonus_type,
                benefits_summary, pto_days,
                employment_type, start_date, is_remote, work_location,
                status, created_by
            ) VALUES (
                :org_id, :candidate_id, :job_id,
                :role_title, :role_def_id, :department, :reports_to,
                :salary, :salary_type, :bonus, :bonus_type,
                :benefits, :pto,
                :emp_type, :start_date, :is_remote, :location,
                'draft', :created_by
            )
            RETURNING id, offer_number
        """)

        result = self.db.execute(query, {
            "org_id": organization_id,
            "candidate_id": candidate_id,
            "job_id": data.get("job_posting_id"),
            "role_title": data.get("role_title"),
            "role_def_id": data.get("role_definition_id"),
            "department": data.get("department"),
            "reports_to": data.get("reports_to_user_id"),
            "salary": data.get("salary_amount"),
            "salary_type": data.get("salary_type", "salary"),
            "bonus": data.get("bonus_amount"),
            "bonus_type": data.get("bonus_type"),
            "benefits": data.get("benefits_summary"),
            "pto": data.get("pto_days"),
            "emp_type": data.get("employment_type", "full_time"),
            "start_date": data.get("start_date"),
            "is_remote": data.get("is_remote", False),
            "location": data.get("work_location"),
            "created_by": created_by
        }).fetchone()

        # Update candidate status (org-scoped)
        offer_org_filter = "AND organization_id = :org_id"
        offer_update_params = {"id": candidate_id, "org_id": organization_id}
        query = f"""
            UPDATE mm_candidates
            SET status = 'offer', updated_at = CURRENT_TIMESTAMP
            WHERE id = :id {offer_org_filter}
        """
        self.db.execute(text(query), offer_update_params)

        # Log activity
        await self._log_activity(
            candidate_id=candidate_id,
            activity_type="offer_created",
            description=f"Offer {result.offer_number} created",
            performed_by=created_by,
            organization_id=organization_id,
            offer_id=result.id
        )

        self.db.commit()

        return {"id": result.id, "offer_number": result.offer_number}

    async def send_offer(
        self,
        offer_id: int,
        sent_by: int,
        *,
        expires_in_days: int = 7,
        organization_id: int
    ) -> Dict[str, Any]:
        """Send an offer to candidate."""

        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        send_params = {
            "id": offer_id,
            "sent_by": sent_by,
            "expires_at": expires_at
        }
        send_org_filter = "AND organization_id = :org_id"
        send_params["org_id"] = organization_id

        query = f"""
            UPDATE mm_offers
            SET status = 'sent',
                sent_at = CURRENT_TIMESTAMP,
                sent_by = :sent_by,
                expires_at = :expires_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id {send_org_filter}
            RETURNING candidate_id, offer_number
        """
        result = self.db.execute(text(query), send_params).fetchone()

        if not result:
            raise ValueError(f"Offer {offer_id} not found")

        # Log activity
        await self._log_activity(
            candidate_id=result.candidate_id,
            activity_type="offer_sent",
            description=f"Offer {result.offer_number} sent to candidate",
            performed_by=sent_by,
            organization_id=organization_id,
            offer_id=offer_id
        )

        self.db.commit()

        return {"offer_id": offer_id, "expires_at": expires_at.isoformat()}

    async def respond_to_offer(
        self,
        offer_id: int,
        accepted: bool,
        *,
        notes: Optional[str] = None,
        organization_id: int
    ) -> Dict[str, Any]:
        """Record candidate's response to offer."""

        resp_org_filter = "AND organization_id = :org_id"
        resp_params_base = {"id": offer_id, "notes": notes, "org_id": organization_id}

        if accepted:
            query = f"""
                UPDATE mm_offers
                SET status = 'accepted',
                    accepted_at = CURRENT_TIMESTAMP,
                    responded_at = CURRENT_TIMESTAMP,
                    response_notes = :notes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status IN ('sent', 'viewed', 'negotiating')
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                {resp_org_filter}
                RETURNING candidate_id, offer_number
            """
            result = self.db.execute(text(query), resp_params_base).fetchone()

            if not result:
                # Check if it exists but is expired
                expired = self.db.execute(text("""
                    SELECT id FROM mm_offers WHERE id = :id AND organization_id = :org_id
                """), {"id": offer_id, "org_id": organization_id}).fetchone()
                if expired:
                    raise ValueError(f"Offer {offer_id} has expired or already been responded to")
                raise ValueError(f"Offer {offer_id} not found")

            # Update candidate to hired (scoped via offer's candidate_id)
            hired_params = {"id": result.candidate_id, "org_id": organization_id}
            hired_org_filter = "AND organization_id = :org_id"

            query = f"""
                UPDATE mm_candidates
                SET status = 'hired',
                    hired_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id {hired_org_filter}
            """
            self.db.execute(text(query), hired_params)

            # Bridge: create talent state for new hire
            candidate_row = self.db.execute(text("""
                SELECT hired_as_user_id FROM mm_candidates
                WHERE id = :id AND organization_id = :org_id
            """), {"id": result.candidate_id, "org_id": organization_id}).fetchone()

            if candidate_row and candidate_row.hired_as_user_id:
                await self._create_talent_state_for_hire(
                    candidate_id=result.candidate_id,
                    hired_as_user_id=candidate_row.hired_as_user_id,
                    organization_id=organization_id,
                )

            activity_type = "offer_accepted"
            description = f"Offer {result.offer_number} accepted"
        else:
            query = f"""
                UPDATE mm_offers
                SET status = 'declined',
                    declined_at = CURRENT_TIMESTAMP,
                    responded_at = CURRENT_TIMESTAMP,
                    declined_notes = :notes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status IN ('sent', 'viewed', 'negotiating') {resp_org_filter}
                RETURNING candidate_id, offer_number
            """
            result = self.db.execute(text(query), resp_params_base).fetchone()

            if not result:
                raise ValueError(f"Offer {offer_id} not found or already responded to")

            activity_type = "offer_declined"
            description = f"Offer {result.offer_number} declined"

        # Log activity
        await self._log_activity(
            candidate_id=result.candidate_id,
            activity_type=activity_type,
            description=description,
            organization_id=organization_id,
            offer_id=offer_id,
            is_automated=True
        )

        self.db.commit()

        return {"offer_id": offer_id, "status": "accepted" if accepted else "declined"}

    # =========================================================================
    # HELPERS
    # =========================================================================

    async def _log_activity(
        self,
        candidate_id: int,
        activity_type: str,
        description: str,
        *,
        organization_id: int,
        performed_by: Optional[int] = None,
        interview_id: Optional[int] = None,
        offer_id: Optional[int] = None,
        is_automated: bool = False
    ):
        """Log candidate activity."""
        try:
            # Validate performed_by exists if provided
            if performed_by:
                user_exists = self.db.execute(text(
                    "SELECT 1 FROM users WHERE id = :id"
                ), {"id": performed_by}).fetchone()
                if not user_exists:
                    performed_by = None  # Clear invalid FK reference

            self.db.execute(text("""
                INSERT INTO mm_candidate_activities (
                    organization_id, candidate_id,
                    activity_type, description,
                    interview_id, offer_id,
                    performed_by, is_automated
                ) VALUES (
                    :org_id, :candidate_id,
                    :type, :description,
                    :interview_id, :offer_id,
                    :performed_by, :is_automated
                )
            """), {
                "org_id": organization_id,
                "candidate_id": candidate_id,
                "type": activity_type,
                "description": description,
                "interview_id": interview_id,
                "offer_id": offer_id,
                "performed_by": performed_by,
                "is_automated": is_automated
            })
        except Exception as e:
            logger.warning(f"Failed to log activity for candidate {candidate_id}: {e}")

        # Update last activity (org-scoped)
        activity_org_filter = "AND organization_id = :org_id"
        activity_params = {"id": candidate_id, "org_id": organization_id}
        query = f"""
            UPDATE mm_candidates
            SET last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :id {activity_org_filter}
        """
        self.db.execute(text(query), activity_params)

    async def _create_talent_state_for_hire(
        self,
        candidate_id: int,
        hired_as_user_id: int,
        organization_id: int,
    ) -> Optional[Dict]:
        """Create mm_talent_state and mm_talent_state_history for a newly hired candidate."""
        try:
            # Get ramp duration from target role definition (default 90 days)
            role_info = self.db.execute(text("""
                SELECT rd.learning_curve_days, rd.id as role_id,
                       rd.default_max_files, rd.default_max_leads, rd.default_max_tasks_daily
                FROM mm_candidates c
                LEFT JOIN mm_role_definitions rd ON rd.id = c.target_role_id
                WHERE c.id = :cid AND c.organization_id = :org_id
            """), {"cid": candidate_id, "org_id": organization_id}).fetchone()

            ramp_days = 90
            role_definition_id = None
            if role_info and role_info.learning_curve_days:
                ramp_days = role_info.learning_curve_days
                role_definition_id = role_info.role_id

            # Insert talent state (upsert)
            self.db.execute(text("""
                INSERT INTO mm_talent_state (
                    organization_id, user_id, state, state_reason,
                    state_changed_at, is_new_hire, is_in_ramp,
                    hire_date, ramp_day, ramp_completion_date, ramp_progress_pct,
                    created_at, updated_at
                ) VALUES (
                    :org_id, :user_id, 'new_hire', 'Hired from recruiting pipeline',
                    CURRENT_TIMESTAMP, true, true,
                    CURRENT_DATE, 0,
                    CURRENT_DATE + make_interval(days => :ramp_days), 0.0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (organization_id, user_id) DO UPDATE SET
                    state = 'new_hire',
                    state_reason = 'Hired from recruiting pipeline',
                    state_changed_at = CURRENT_TIMESTAMP,
                    is_new_hire = true, is_in_ramp = true,
                    hire_date = CURRENT_DATE, ramp_day = 0,
                    ramp_completion_date = CURRENT_DATE + make_interval(days => :ramp_days),
                    ramp_progress_pct = 0.0,
                    updated_at = CURRENT_TIMESTAMP
            """), {"org_id": organization_id, "user_id": hired_as_user_id, "ramp_days": ramp_days})

            # Insert state history
            self.db.execute(text("""
                INSERT INTO mm_talent_state_history (
                    organization_id, user_id, previous_state, new_state,
                    reason, created_at
                ) VALUES (
                    :org_id, :user_id, NULL, 'new_hire',
                    :reason, CURRENT_TIMESTAMP
                )
            """), {
                "org_id": organization_id,
                "user_id": hired_as_user_id,
                "reason": f"Hired from recruiting pipeline (candidate {candidate_id})",
            })

            # Create talent capacity with role defaults
            if role_info and role_definition_id:
                self.db.execute(text("""
                    INSERT INTO mm_talent_capacity (
                        organization_id, user_id, role_definition_id,
                        max_files_concurrent, max_leads_concurrent, max_tasks_daily,
                        capacity_status, is_available, availability_status,
                        created_at, updated_at
                    ) VALUES (
                        :org_id, :user_id, :role_id,
                        :max_files, :max_leads, :max_tasks,
                        'available', true, 'active',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (organization_id, user_id) DO NOTHING
                """), {
                    "org_id": organization_id,
                    "user_id": hired_as_user_id,
                    "role_id": role_definition_id,
                    "max_files": role_info.default_max_files or 25,
                    "max_leads": role_info.default_max_leads or 50,
                    "max_tasks": role_info.default_max_tasks_daily or 30,
                })

            logger.info(f"Created talent state for hired candidate {candidate_id} -> user {hired_as_user_id}")
            return {"user_id": hired_as_user_id, "state": "new_hire", "ramp_days": ramp_days}

        except Exception as e:
            logger.error(f"Failed to create talent state for candidate {candidate_id}: {e}")
            return None

    async def _create_portal_workspace(
        self,
        candidate_id: int,
        first_name: str,
        last_name: str
    ) -> Dict[str, Any]:
        """Auto-create recruit portal workspace for a candidate."""
        try:
            # Generate slug from name with cryptographic random suffix
            base_slug = f"{first_name.lower()}-{last_name.lower()}" if first_name and last_name else f"candidate-{candidate_id}"
            base_slug = re.sub(r'[^a-z0-9-]', '', base_slug)
            slug = f"{base_slug}-{secrets.token_hex(8)}"

            # Insert with unique constraint — retry on collision instead of TOCTOU check
            workspace_id = None
            for _ in range(10):
                try:
                    result = self.db.execute(
                        text("""
                            INSERT INTO recruit_portal_workspaces (candidate_id, slug, is_active, created_at)
                            VALUES (:candidate_id, :slug, true, NOW())
                            RETURNING id
                        """),
                        {"candidate_id": candidate_id, "slug": slug}
                    )
                    workspace_id = result.fetchone().id
                    break
                except IntegrityError:
                    self.db.rollback()
                    slug = f"{base_slug}-{secrets.token_hex(8)}"
            else:
                raise RuntimeError("Could not generate unique portal slug after 10 attempts")

            # Generate access token
            token = f"recruit_{secrets.token_hex(32)}"
            self.db.execute(
                text("""
                    INSERT INTO recruit_portal_tokens (workspace_id, token, scope, created_at)
                    VALUES (:workspace_id, :token, 'full', NOW())
                """),
                {"workspace_id": workspace_id, "token": token}
            )

            logger.info(f"Created portal workspace for candidate {candidate_id}: slug={slug}")

            return {
                "workspace_id": workspace_id,
                "slug": slug,
                "token": token,
                "portal_url": f"/join/{slug}"
            }

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed to create portal workspace for candidate {candidate_id}: {e}")
            return {}


# =========================================================================
# FACTORY FUNCTION
# =========================================================================

def get_recruiting_service(db: Session) -> RecruitingService:
    """Factory function to get RecruitingService instance."""
    return RecruitingService(db)
