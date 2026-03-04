"""
Recruit Retention Service — CCPA/GDPR Data Retention & Anonymization

Handles:
- Candidate PII anonymization (right-to-delete)
- Retention policy enforcement (auto-purge after threshold)
- Dry-run reporting for compliance review
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ANONYMIZABLE_STATUSES = ("rejected", "withdrawn")


class RecruitRetentionService:
    """Manages candidate data retention and CCPA compliance."""

    def __init__(self, db: Session):
        self.db = db

    def anonymize_candidate(
        self,
        candidate_id: int,
        organization_id: int,
        performed_by: int,
        reason: str = "manual_anonymization",
    ) -> Dict[str, Any]:
        """Anonymize candidate PII. Preserves aggregate analytics data."""

        # Verify candidate exists and belongs to org
        candidate = self.db.execute(text("""
            SELECT id, first_name, last_name, email, status, is_active
            FROM mm_candidates
            WHERE id = :cid AND organization_id = :org_id
        """), {"cid": candidate_id, "org_id": organization_id}).fetchone()

        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found in organization")

        # Anonymize PII fields on mm_candidates
        self.db.execute(text("""
            UPDATE mm_candidates SET
                first_name = 'REDACTED',
                last_name = 'REDACTED',
                email = :redacted_email,
                phone = NULL,
                resume_url = NULL,
                cover_letter = NULL,
                linkedin_url = NULL,
                facebook_url = NULL,
                instagram_url = NULL,
                twitter_url = NULL,
                headshot_url = NULL,
                bio = NULL,
                recruiter_notes = NULL,
                hiring_manager_notes = NULL,
                social_profiles = NULL,
                social_posts = NULL,
                previous_companies = NULL,
                personal_emails = NULL,
                personal_numbers = NULL,
                is_active = false,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :cid AND organization_id = :org_id
        """), {
            "cid": candidate_id,
            "org_id": organization_id,
            "redacted_email": f"redacted_{candidate_id}@deleted.local",
        })

        # Anonymize candidate notes
        self.db.execute(text("""
            UPDATE mm_candidate_notes
            SET content = '[REDACTED]', updated_at = CURRENT_TIMESTAMP
            WHERE candidate_id = :cid AND organization_id = :org_id
        """), {"cid": candidate_id, "org_id": organization_id})

        # Anonymize activity descriptions (keep types for funnel analytics)
        self.db.execute(text("""
            UPDATE mm_candidate_activities
            SET description = '[REDACTED]'
            WHERE candidate_id = :cid AND organization_id = :org_id
        """), {"cid": candidate_id, "org_id": organization_id})

        # Anonymize portal chat messages
        self.db.execute(text("""
            UPDATE recruit_portal_messages SET content = '[REDACTED]'
            WHERE workspace_id IN (
                SELECT id FROM recruit_portal_workspaces WHERE candidate_id = :cid
            )
        """), {"cid": candidate_id})

        # Deactivate portal workspace
        self.db.execute(text("""
            UPDATE recruit_portal_workspaces
            SET is_active = false, updated_at = CURRENT_TIMESTAMP
            WHERE candidate_id = :cid
        """), {"cid": candidate_id})

        # Log to audit_logs
        try:
            self.db.execute(text("""
                INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details, created_at)
                VALUES (:user_id, 'candidate_anonymized', 'candidate', :entity_id, :details, CURRENT_TIMESTAMP)
            """), {
                "user_id": performed_by,
                "entity_id": str(candidate_id),
                "details": json.dumps({
                    "reason": reason,
                    "original_name": f"{candidate.first_name} {candidate.last_name}",
                    "original_email": candidate.email,
                    "status_at_deletion": candidate.status,
                }),
            })
        except Exception as e:
            logger.warning(f"Failed to log anonymization audit for candidate {candidate_id}: {e}")

        self.db.commit()

        logger.info(f"Anonymized candidate {candidate_id} (reason: {reason}, by: {performed_by})")

        return {
            "candidate_id": candidate_id,
            "status": "anonymized",
            "reason": reason,
            "fields_cleared": [
                "first_name", "last_name", "email", "phone", "resume_url",
                "linkedin_url", "facebook_url", "notes", "portal_messages"
            ],
            "preserved": ["organization_id", "status", "applied_at", "hired_at", "eeoc_data", "assessment_scores"],
        }

    def enforce_candidate_retention(
        self,
        organization_id: int,
        retention_days: int = 365,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Find and optionally anonymize candidates past retention window."""

        eligible = self.db.execute(text("""
            SELECT id, first_name, last_name, email, status, status_changed_at
            FROM mm_candidates
            WHERE organization_id = :org_id
                AND is_active = true
                AND status IN ('rejected', 'withdrawn')
                AND status_changed_at < CURRENT_TIMESTAMP - make_interval(days => :days)
            ORDER BY status_changed_at ASC
        """), {"org_id": organization_id, "days": retention_days}).fetchall()

        candidates_list = [
            {
                "id": row.id,
                "name": f"{row.first_name} {row.last_name}",
                "email": row.email,
                "status": row.status,
                "status_changed_at": row.status_changed_at.isoformat() if row.status_changed_at else None,
            }
            for row in eligible
        ]

        if dry_run:
            return {
                "dry_run": True,
                "retention_days": retention_days,
                "eligible_count": len(candidates_list),
                "candidates": candidates_list,
            }

        # Execute anonymization
        anonymized_count = 0
        errors = []

        for candidate in eligible:
            try:
                self.anonymize_candidate(
                    candidate_id=candidate.id,
                    organization_id=organization_id,
                    performed_by=0,  # System action
                    reason="retention_policy_enforcement",
                )
                anonymized_count += 1
            except Exception as e:
                errors.append({"candidate_id": candidate.id, "error": str(e)})
                logger.error(f"Failed to anonymize candidate {candidate.id}: {e}")

        return {
            "dry_run": False,
            "retention_days": retention_days,
            "eligible_count": len(eligible),
            "anonymized_count": anonymized_count,
            "error_count": len(errors),
            "errors": errors if errors else None,
        }

    def process_deletion_request(
        self,
        candidate_id: int,
        organization_id: int,
        requested_by: int,
    ) -> Dict[str, Any]:
        """CCPA right-to-delete: immediately anonymize candidate data."""
        return self.anonymize_candidate(
            candidate_id=candidate_id,
            organization_id=organization_id,
            performed_by=requested_by,
            reason="ccpa_deletion_request",
        )
