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
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


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
        organization_id: Optional[int] = None,
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
            AND (:org_id IS NULL OR organization_id = :org_id)
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
            AND (:org_id IS NULL OR organization_id = :org_id)
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
            AND (:org_id IS NULL OR organization_id = :org_id)
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
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)
        positions = self.db.execute(positions_query, {"org_id": organization_id}).fetchone()

        # Pending offers
        offers_query = text("""
            SELECT COUNT(*) as count
            FROM mm_offers
            WHERE status IN ('sent', 'viewed', 'negotiating')
            AND (:org_id IS NULL OR organization_id = :org_id)
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
        organization_id: Optional[int] = None,
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
                (SELECT COUNT(*) FROM mm_interviews WHERE candidate_id = c.id) as interview_count,
                (SELECT COUNT(*) FROM mm_offers WHERE candidate_id = c.id AND status NOT IN ('declined', 'withdrawn', 'expired')) as offer_count,
                ras.overall_score as assessment_score
            FROM mm_candidates c
            LEFT JOIN recruit_assessment_scores ras ON ras.candidate_id = c.id
            WHERE c.is_active = true
            AND (:org_id IS NULL OR c.organization_id = :org_id)
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

    async def get_candidate_detail(
        self,
        candidate_id: int,
        organization_id: Optional[int] = None
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
            AND (:org_id IS NULL OR c.organization_id = :org_id)
        """)

        result = self.db.execute(query, {
            "id": candidate_id,
            "org_id": organization_id
        }).fetchone()

        if not result:
            return None

        # Get interviews
        interviews = self.db.execute(text("""
            SELECT
                i.id, i.interview_type, i.interview_round, i.title,
                i.scheduled_at, i.status, i.overall_score, i.recommendation,
                u.full_name as interviewer_name
            FROM mm_interviews i
            LEFT JOIN users u ON u.id = i.primary_interviewer_id
            WHERE i.candidate_id = :id
            ORDER BY i.scheduled_at DESC
        """), {"id": candidate_id}).fetchall()

        # Get offers
        offers = self.db.execute(text("""
            SELECT
                o.id, o.offer_number, o.role_title, o.salary_amount,
                o.status, o.sent_at, o.responded_at
            FROM mm_offers o
            WHERE o.candidate_id = :id
            ORDER BY o.created_at DESC
        """), {"id": candidate_id}).fetchall()

        # Get activities
        activities = self.db.execute(text("""
            SELECT
                a.id, a.activity_type, a.description, a.created_at,
                u.full_name as performed_by_name
            FROM mm_candidate_activities a
            LEFT JOIN users u ON u.id = a.performed_by
            WHERE a.candidate_id = :id
            ORDER BY a.created_at DESC
            LIMIT 20
        """), {"id": candidate_id}).fetchall()

        # Get notes (exclude private notes — private notes are internal-only)
        notes = self.db.execute(text("""
            SELECT
                n.id, n.note_type, n.content, n.is_private, n.created_at,
                u.full_name as author_name
            FROM mm_candidate_notes n
            JOIN users u ON u.id = n.created_by
            WHERE n.candidate_id = :id AND (n.is_private = false OR n.is_private IS NULL)
            ORDER BY n.created_at DESC
        """), {"id": candidate_id}).fetchall()

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
        organization_id: Optional[int] = None
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

    async def update_candidate_status(
        self,
        candidate_id: int,
        new_status: str,
        updated_by: int,
        reason: Optional[str] = None,
        organization_id: Optional[int] = None,
        disposition_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update candidate status with optional OFCCP disposition tracking."""

        # Get current status with org isolation
        org_filter = "AND organization_id = :org_id" if organization_id else ""
        params = {"id": candidate_id}
        if organization_id:
            params["org_id"] = organization_id

        current = self.db.execute(text(f"""
            SELECT status FROM mm_candidates WHERE id = :id {org_filter}
        """), params).fetchone()

        if not current:
            raise ValueError(f"Candidate {candidate_id} not found")

        old_status = current.status

        # Build update query — include disposition fields when provided
        if disposition_code:
            self.db.execute(text(f"""
                UPDATE mm_candidates
                SET status = :status,
                    status_changed_at = CURRENT_TIMESTAMP,
                    status_changed_by = :user_id,
                    disposition_code = :disposition_code,
                    disposition_date = CURRENT_TIMESTAMP,
                    disposition_by = :user_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id {org_filter}
            """), {
                "id": candidate_id,
                "status": new_status,
                "user_id": updated_by,
                "disposition_code": disposition_code,
                **({"org_id": organization_id} if organization_id else {}),
            })
        else:
            self.db.execute(text(f"""
                UPDATE mm_candidates
                SET status = :status,
                    status_changed_at = CURRENT_TIMESTAMP,
                    status_changed_by = :user_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id {org_filter}
            """), {
                "id": candidate_id,
                "status": new_status,
                "user_id": updated_by,
                **({"org_id": organization_id} if organization_id else {}),
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
        organization_id: Optional[int] = None,
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
                (SELECT COUNT(*) FROM mm_candidates WHERE target_role_id = jp.role_definition_id AND status NOT IN ('rejected', 'withdrawn', 'hired')) as active_candidates
            FROM mm_job_postings jp
            LEFT JOIN mm_role_definitions rd ON rd.id = jp.role_definition_id
            WHERE (:org_id IS NULL OR jp.organization_id = :org_id)
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
        organization_id: Optional[int] = None
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
        organization_id: Optional[int] = None
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

        # Update candidate status if still in early stage
        self.db.execute(text("""
            UPDATE mm_candidates
            SET status = CASE
                WHEN status IN ('new', 'screening', 'phone_screen') THEN 'interview'
                ELSE status
            END,
            updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": candidate_id})

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
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Submit feedback for an interview."""

        # Get current feedback with org isolation
        org_filter = ""
        params = {"id": interview_id}
        if organization_id:
            org_filter = "AND i.organization_id = :org_id"
            params["org_id"] = organization_id

        current = self.db.execute(text(f"""
            SELECT i.feedback, i.candidate_id FROM mm_interviews i WHERE i.id = :id {org_filter}
        """), params).fetchone()

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
        update_org_filter = ""
        if organization_id:
            update_org_filter = "AND organization_id = :org_id"
            update_params["org_id"] = organization_id

        self.db.execute(text(f"""
            UPDATE mm_interviews
            SET feedback = :feedback,
                overall_score = :score,
                recommendation = :recommendation,
                completed_at = CURRENT_TIMESTAMP,
                status = 'completed',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id {update_org_filter}
        """), update_params)

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
        organization_id: Optional[int] = None
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

        # Update candidate status
        self.db.execute(text("""
            UPDATE mm_candidates
            SET status = 'offer', updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": candidate_id})

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
        expires_in_days: int = 7,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Send an offer to candidate."""

        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        send_params = {
            "id": offer_id,
            "sent_by": sent_by,
            "expires_at": expires_at
        }
        send_org_filter = ""
        if organization_id:
            send_org_filter = "AND organization_id = :org_id"
            send_params["org_id"] = organization_id

        result = self.db.execute(text(f"""
            UPDATE mm_offers
            SET status = 'sent',
                sent_at = CURRENT_TIMESTAMP,
                sent_by = :sent_by,
                expires_at = :expires_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id {send_org_filter}
            RETURNING candidate_id, offer_number
        """), send_params).fetchone()

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
        notes: Optional[str] = None,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Record candidate's response to offer."""

        resp_org_filter = ""
        resp_params_base = {"id": offer_id, "notes": notes}
        if organization_id:
            resp_org_filter = "AND organization_id = :org_id"
            resp_params_base["org_id"] = organization_id

        if accepted:
            result = self.db.execute(text(f"""
                UPDATE mm_offers
                SET status = 'accepted',
                    accepted_at = CURRENT_TIMESTAMP,
                    responded_at = CURRENT_TIMESTAMP,
                    response_notes = :notes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id {resp_org_filter}
                RETURNING candidate_id, offer_number
            """), resp_params_base).fetchone()

            if not result:
                raise ValueError(f"Offer {offer_id} not found")

            # Update candidate to hired (scoped via offer's candidate_id)
            hired_params = {"id": result.candidate_id}
            hired_org_filter = ""
            if organization_id:
                hired_org_filter = "AND organization_id = :org_id"
                hired_params["org_id"] = organization_id

            self.db.execute(text(f"""
                UPDATE mm_candidates
                SET status = 'hired',
                    hired_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id {hired_org_filter}
            """), hired_params)

            activity_type = "offer_accepted"
            description = f"Offer {result.offer_number} accepted"
        else:
            result = self.db.execute(text(f"""
                UPDATE mm_offers
                SET status = 'declined',
                    declined_at = CURRENT_TIMESTAMP,
                    responded_at = CURRENT_TIMESTAMP,
                    declined_notes = :notes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id {resp_org_filter}
                RETURNING candidate_id, offer_number
            """), resp_params_base).fetchone()

            if not result:
                raise ValueError(f"Offer {offer_id} not found")

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
        performed_by: Optional[int] = None,
        organization_id: Optional[int] = None,
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

        # Update last activity
        self.db.execute(text("""
            UPDATE mm_candidates
            SET last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"id": candidate_id})

    async def _create_portal_workspace(
        self,
        candidate_id: int,
        first_name: str,
        last_name: str
    ) -> Dict[str, Any]:
        """Auto-create recruit portal workspace for a candidate."""
        import re
        import secrets

        try:
            # Generate slug from name
            base_slug = f"{first_name.lower()}-{last_name.lower()}" if first_name and last_name else f"candidate-{candidate_id}"
            base_slug = re.sub(r'[^a-z0-9-]', '', base_slug)
            slug = base_slug

            # Check for uniqueness
            count = 1
            while True:
                result = self.db.execute(
                    text("SELECT id FROM recruit_portal_workspaces WHERE slug = :slug"),
                    {"slug": slug}
                )
                if not result.fetchone():
                    break
                slug = f"{base_slug}-{count}"
                count += 1

            # Create workspace
            result = self.db.execute(
                text("""
                    INSERT INTO recruit_portal_workspaces (candidate_id, slug, is_active, created_at)
                    VALUES (:candidate_id, :slug, true, NOW())
                    RETURNING id
                """),
                {"candidate_id": candidate_id, "slug": slug}
            )
            workspace_id = result.fetchone().id

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

        except Exception as e:
            logger.error(f"Failed to create portal workspace for candidate {candidate_id}: {e}")
            return {}


# =========================================================================
# FACTORY FUNCTION
# =========================================================================

def get_recruiting_service(db: Session) -> RecruitingService:
    """Factory function to get RecruitingService instance."""
    return RecruitingService(db)
