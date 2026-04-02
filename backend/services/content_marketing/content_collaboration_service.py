"""
Content Collaboration Service

Handles team collaboration features:
- Comments on content briefs and items
- Approval workflows with multiple stages
- Team notifications and assignments
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session

from models.content_marketing import (
    ContentBrief, ContentComment, ContentApproval,
    ApprovalStatus, ContentStatus
)

logger = logging.getLogger(__name__)


class ContentCollaborationService:
    """
    Service for team collaboration on content.

    Handles comments, approvals, and workflow management
    for content briefs and items.
    """

    # Standard approval workflow stages
    APPROVAL_STAGES = [
        "draft_review",      # Initial content review
        "compliance_review", # Compliance/legal review
        "final_approval",    # Final sign-off before publishing
    ]

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    # =========================================================================
    # Comments
    # =========================================================================

    def add_comment(
        self,
        user_id: int,
        content: str,
        brief_id: Optional[str] = None,
        content_item_id: Optional[str] = None,
        comment_type: str = "general",
        parent_comment_id: Optional[str] = None,
        highlighted_text: Optional[str] = None,
        position_start: Optional[int] = None,
        position_end: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Add a comment to a brief or content item.

        Args:
            user_id: Commenting user's ID
            content: Comment text
            brief_id: Associated brief ID
            content_item_id: Associated content item ID
            comment_type: Type of comment (general, suggestion, edit_request, approval_note)
            parent_comment_id: Parent comment ID for replies
            highlighted_text: Text being commented on
            position_start: Start position for inline comments
            position_end: End position for inline comments

        Returns:
            Created comment data
        """
        try:
            if not brief_id and not content_item_id:
                return {"success": False, "error": "brief_id or content_item_id required"}

            comment = ContentComment(
                brief_id=brief_id,
                content_item_id=content_item_id,
                user_id=user_id,
                parent_comment_id=parent_comment_id,
                comment_type=comment_type,
                content=content,
                highlighted_text=highlighted_text,
                position_start=position_start,
                position_end=position_end,
                resolved=False,
            )

            self.db.add(comment)
            self.db.commit()
            self.db.refresh(comment)

            return {
                "success": True,
                "comment_id": comment.id,
                "comment_type": comment.comment_type,
                "created_at": comment.created_at.isoformat(),
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to add comment: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_comment(self, comment_id: str) -> Optional[ContentComment]:
        """Get a comment by ID."""
        return self.db.query(ContentComment).filter(
            ContentComment.id == comment_id
        ).first()

    def list_comments(
        self,
        brief_id: Optional[str] = None,
        content_item_id: Optional[str] = None,
        include_resolved: bool = False,
        comment_type: Optional[str] = None,
    ) -> List[ContentComment]:
        """List comments for a brief or content item."""
        query = self.db.query(ContentComment)

        if brief_id:
            query = query.filter(ContentComment.brief_id == brief_id)
        if content_item_id:
            query = query.filter(ContentComment.content_item_id == content_item_id)
        if not include_resolved:
            query = query.filter(ContentComment.resolved == False)
        if comment_type:
            query = query.filter(ContentComment.comment_type == comment_type)

        # Get top-level comments only (replies fetched via relationship)
        query = query.filter(ContentComment.parent_comment_id == None)

        return query.order_by(ContentComment.created_at.desc()).all()

    def reply_to_comment(
        self,
        parent_comment_id: str,
        user_id: int,
        content: str
    ) -> Dict[str, Any]:
        """Reply to an existing comment."""
        parent = self.get_comment(parent_comment_id)
        if not parent:
            return {"success": False, "error": "Parent comment not found"}

        return self.add_comment(
            user_id=user_id,
            content=content,
            brief_id=parent.brief_id,
            content_item_id=parent.content_item_id,
            comment_type="general",
            parent_comment_id=parent_comment_id,
        )

    def resolve_comment(
        self,
        comment_id: str,
        resolved_by: int
    ) -> bool:
        """Mark a comment as resolved."""
        comment = self.get_comment(comment_id)
        if not comment:
            return False

        comment.resolved = True
        comment.resolved_by = resolved_by
        comment.resolved_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def unresolve_comment(self, comment_id: str) -> bool:
        """Reopen a resolved comment."""
        comment = self.get_comment(comment_id)
        if not comment:
            return False

        comment.resolved = False
        comment.resolved_by = None
        comment.resolved_at = None
        self.db.commit()
        return True

    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment and its replies."""
        comment = self.get_comment(comment_id)
        if not comment:
            return False

        # Delete replies first
        self.db.query(ContentComment).filter(
            ContentComment.parent_comment_id == comment_id
        ).delete()

        self.db.delete(comment)
        self.db.commit()
        return True

    def get_comment_thread(self, comment_id: str) -> Dict[str, Any]:
        """Get a comment and all its replies as a thread."""
        comment = self.get_comment(comment_id)
        if not comment:
            return {}

        def build_reply_tree(parent_id):
            replies = self.db.query(ContentComment).filter(
                ContentComment.parent_comment_id == parent_id
            ).order_by(ContentComment.created_at).all()

            return [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "content": r.content,
                    "created_at": r.created_at.isoformat(),
                    "resolved": r.resolved,
                    "replies": build_reply_tree(r.id),
                }
                for r in replies
            ]

        return {
            "id": comment.id,
            "user_id": comment.user_id,
            "content": comment.content,
            "comment_type": comment.comment_type,
            "highlighted_text": comment.highlighted_text,
            "created_at": comment.created_at.isoformat(),
            "resolved": comment.resolved,
            "replies": build_reply_tree(comment.id),
        }

    # =========================================================================
    # Approvals
    # =========================================================================

    def request_approval(
        self,
        workflow_stage: str,
        requested_by: int,
        assigned_to: int,
        brief_id: Optional[str] = None,
        content_item_id: Optional[str] = None,
        due_date: Optional[datetime] = None,
        content_snapshot: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an approval request.

        Args:
            workflow_stage: Stage of approval (draft_review, compliance_review, final_approval)
            requested_by: User requesting approval
            assigned_to: User assigned to approve
            brief_id: Associated brief ID
            content_item_id: Associated content item ID
            due_date: Due date for approval
            content_snapshot: Snapshot of content at request time

        Returns:
            Created approval data
        """
        try:
            if not brief_id and not content_item_id:
                return {"success": False, "error": "brief_id or content_item_id required"}

            # Get current version
            version = 1
            existing = self.db.query(ContentApproval).filter(
                ContentApproval.brief_id == brief_id if brief_id else True,
                ContentApproval.content_item_id == content_item_id if content_item_id else True,
                ContentApproval.workflow_stage == workflow_stage
            ).count()
            if existing:
                version = existing + 1

            approval = ContentApproval(
                brief_id=brief_id,
                content_item_id=content_item_id,
                workflow_stage=workflow_stage,
                status=ApprovalStatus.PENDING.value,
                requested_by=requested_by,
                assigned_to=assigned_to,
                due_date=due_date,
                content_version=version,
                content_snapshot=content_snapshot,
            )

            self.db.add(approval)
            self.db.commit()
            self.db.refresh(approval)

            # Update brief status if applicable
            if brief_id:
                brief = self.db.query(ContentBrief).filter(
                    ContentBrief.id == brief_id
                ).first()
                if brief:
                    brief.status = ContentStatus.REVIEW.value
                    self.db.commit()

            return {
                "success": True,
                "approval_id": approval.id,
                "workflow_stage": approval.workflow_stage,
                "assigned_to": approval.assigned_to,
                "status": approval.status,
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create approval request: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_approval(self, approval_id: str) -> Optional[ContentApproval]:
        """Get an approval by ID."""
        return self.db.query(ContentApproval).filter(
            ContentApproval.id == approval_id
        ).first()

    def list_approvals(
        self,
        brief_id: Optional[str] = None,
        content_item_id: Optional[str] = None,
        assigned_to: Optional[int] = None,
        status: Optional[str] = None,
        workflow_stage: Optional[str] = None,
    ) -> List[ContentApproval]:
        """List approvals with filters."""
        query = self.db.query(ContentApproval)

        if brief_id:
            query = query.filter(ContentApproval.brief_id == brief_id)
        if content_item_id:
            query = query.filter(ContentApproval.content_item_id == content_item_id)
        if assigned_to:
            query = query.filter(ContentApproval.assigned_to == assigned_to)
        if status:
            query = query.filter(ContentApproval.status == status)
        if workflow_stage:
            query = query.filter(ContentApproval.workflow_stage == workflow_stage)

        return query.order_by(ContentApproval.created_at.desc()).all()

    def get_pending_approvals(
        self,
        user_id: int
    ) -> List[ContentApproval]:
        """Get all pending approvals assigned to a user."""
        return self.list_approvals(
            assigned_to=user_id,
            status=ApprovalStatus.PENDING.value
        )

    def approve(
        self,
        approval_id: str,
        decision_by: int,
        decision_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Approve a request."""
        approval = self.get_approval(approval_id)
        if not approval:
            return {"success": False, "error": "Approval not found"}

        if approval.status != ApprovalStatus.PENDING.value:
            return {"success": False, "error": "Approval is not pending"}

        approval.status = ApprovalStatus.APPROVED.value
        approval.decision_by = decision_by
        approval.decision_at = datetime.now(timezone.utc)
        approval.decision_notes = decision_notes
        self.db.commit()

        # Check if all approvals complete to move brief to approved
        self._check_brief_approval_complete(approval.brief_id)

        return {
            "success": True,
            "approval_id": approval.id,
            "status": approval.status,
            "decided_at": approval.decision_at.isoformat(),
        }

    def reject(
        self,
        approval_id: str,
        decision_by: int,
        decision_notes: str
    ) -> Dict[str, Any]:
        """Reject an approval request."""
        approval = self.get_approval(approval_id)
        if not approval:
            return {"success": False, "error": "Approval not found"}

        if approval.status != ApprovalStatus.PENDING.value:
            return {"success": False, "error": "Approval is not pending"}

        approval.status = ApprovalStatus.REJECTED.value
        approval.decision_by = decision_by
        approval.decision_at = datetime.now(timezone.utc)
        approval.decision_notes = decision_notes
        self.db.commit()

        # Update brief status back to draft
        if approval.brief_id:
            brief = self.db.query(ContentBrief).filter(
                ContentBrief.id == approval.brief_id
            ).first()
            if brief:
                brief.status = ContentStatus.DRAFT.value
                self.db.commit()

        return {
            "success": True,
            "approval_id": approval.id,
            "status": approval.status,
            "decided_at": approval.decision_at.isoformat(),
        }

    def request_changes(
        self,
        approval_id: str,
        decision_by: int,
        decision_notes: str
    ) -> Dict[str, Any]:
        """Request changes on an approval."""
        approval = self.get_approval(approval_id)
        if not approval:
            return {"success": False, "error": "Approval not found"}

        if approval.status != ApprovalStatus.PENDING.value:
            return {"success": False, "error": "Approval is not pending"}

        approval.status = ApprovalStatus.CHANGES_REQUESTED.value
        approval.decision_by = decision_by
        approval.decision_at = datetime.now(timezone.utc)
        approval.decision_notes = decision_notes
        self.db.commit()

        return {
            "success": True,
            "approval_id": approval.id,
            "status": approval.status,
            "decided_at": approval.decision_at.isoformat(),
        }

    def _check_brief_approval_complete(self, brief_id: Optional[str]) -> bool:
        """Check if all approvals for a brief are complete."""
        if not brief_id:
            return False

        pending_approvals = self.db.query(ContentApproval).filter(
            ContentApproval.brief_id == brief_id,
            ContentApproval.status == ApprovalStatus.PENDING.value
        ).count()

        if pending_approvals == 0:
            # Check if there are any approvals at all
            total_approvals = self.db.query(ContentApproval).filter(
                ContentApproval.brief_id == brief_id
            ).count()

            if total_approvals > 0:
                # All approved (or no pending)
                rejected_count = self.db.query(ContentApproval).filter(
                    ContentApproval.brief_id == brief_id,
                    ContentApproval.status == ApprovalStatus.REJECTED.value
                ).count()

                if rejected_count == 0:
                    brief = self.db.query(ContentBrief).filter(
                        ContentBrief.id == brief_id
                    ).first()
                    if brief:
                        brief.status = ContentStatus.APPROVED.value
                        self.db.commit()
                    return True

        return False

    # =========================================================================
    # Workflow Management
    # =========================================================================

    def start_approval_workflow(
        self,
        brief_id: str,
        requested_by: int,
        stages: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Start a full approval workflow for a brief.

        Args:
            brief_id: Brief to start workflow for
            requested_by: User starting the workflow
            stages: Custom stages with assigned_to users

        Returns:
            Workflow status
        """
        if not stages:
            return {
                "success": False,
                "error": "Stages configuration required with assigned_to users"
            }

        # Get brief content for snapshot
        brief = self.db.query(ContentBrief).filter(
            ContentBrief.id == brief_id
        ).first()
        if not brief:
            return {"success": False, "error": "Brief not found"}

        content_snapshot = f"Title: {brief.title or brief.topic}\n\n{brief.generated_content or ''}"

        created_approvals = []
        for stage_config in stages:
            stage_name = stage_config.get("stage")
            assigned_to = stage_config.get("assigned_to")
            due_date = stage_config.get("due_date")

            if not stage_name or not assigned_to:
                continue

            result = self.request_approval(
                workflow_stage=stage_name,
                requested_by=requested_by,
                assigned_to=assigned_to,
                brief_id=brief_id,
                due_date=due_date,
                content_snapshot=content_snapshot,
            )

            if result.get("success"):
                created_approvals.append(result)

        return {
            "success": True,
            "brief_id": brief_id,
            "approvals_created": len(created_approvals),
            "approvals": created_approvals,
        }

    def get_workflow_status(self, brief_id: str) -> Dict[str, Any]:
        """Get the current workflow status for a brief."""
        approvals = self.list_approvals(brief_id=brief_id)

        if not approvals:
            return {
                "brief_id": brief_id,
                "workflow_started": False,
                "stages": [],
            }

        stages = []
        for approval in approvals:
            stages.append({
                "approval_id": approval.id,
                "stage": approval.workflow_stage,
                "status": approval.status,
                "assigned_to": approval.assigned_to,
                "decision_by": approval.decision_by,
                "decision_at": approval.decision_at.isoformat() if approval.decision_at else None,
                "decision_notes": approval.decision_notes,
            })

        # Determine overall status
        pending_count = len([s for s in stages if s["status"] == ApprovalStatus.PENDING.value])
        approved_count = len([s for s in stages if s["status"] == ApprovalStatus.APPROVED.value])
        rejected_count = len([s for s in stages if s["status"] == ApprovalStatus.REJECTED.value])
        changes_count = len([s for s in stages if s["status"] == ApprovalStatus.CHANGES_REQUESTED.value])

        overall_status = "pending"
        if rejected_count > 0:
            overall_status = "rejected"
        elif changes_count > 0:
            overall_status = "changes_requested"
        elif pending_count == 0 and approved_count > 0:
            overall_status = "approved"

        return {
            "brief_id": brief_id,
            "workflow_started": True,
            "overall_status": overall_status,
            "total_stages": len(stages),
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "changes_requested_count": changes_count,
            "stages": stages,
        }

    # =========================================================================
    # Assignments
    # =========================================================================

    def assign_brief(
        self,
        brief_id: str,
        assigned_to: int,
        due_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Assign a brief to a team member."""
        brief = self.db.query(ContentBrief).filter(
            ContentBrief.id == brief_id
        ).first()

        if not brief:
            return {"success": False, "error": "Brief not found"}

        brief.assigned_to = assigned_to
        if due_date:
            brief.due_date = due_date.date() if isinstance(due_date, datetime) else due_date
        self.db.commit()

        return {
            "success": True,
            "brief_id": brief_id,
            "assigned_to": assigned_to,
            "due_date": brief.due_date.isoformat() if brief.due_date else None,
        }

    def get_user_assignments(
        self,
        user_id: int,
        include_completed: bool = False
    ) -> List[ContentBrief]:
        """Get all briefs assigned to a user."""
        query = self.db.query(ContentBrief).filter(
            ContentBrief.assigned_to == user_id
        )

        if not include_completed:
            query = query.filter(
                ContentBrief.status.notin_([
                    ContentStatus.PUBLISHED.value,
                    ContentStatus.FAILED.value
                ])
            )

        return query.order_by(ContentBrief.due_date).all()

    def get_overdue_assignments(
        self,
        organization_id: int = 1
    ) -> List[ContentBrief]:
        """Get all overdue brief assignments."""
        from datetime import date

        return self.db.query(ContentBrief).filter(
            ContentBrief.organization_id == organization_id,
            ContentBrief.due_date < date.today(),
            ContentBrief.status.notin_([
                ContentStatus.PUBLISHED.value,
                ContentStatus.APPROVED.value,
                ContentStatus.FAILED.value
            ])
        ).order_by(ContentBrief.due_date).all()
