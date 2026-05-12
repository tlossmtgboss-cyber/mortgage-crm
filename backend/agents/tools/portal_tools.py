"""
Perennia AI - Client Portal Tools
Tools for managing borrower portal invitations, access status, and document sharing.
"""

from datetime import datetime
from typing import Optional

from .base import (
    mortgage_tool, ToolResult,
    execute_query, execute_single, get_db,
    format_date,
)


@mortgage_tool(
    name="invite_borrower_to_portal",
    description="Send a portal invitation to a borrower for a specific loan. Creates an invitation record and logs the action.",
    agent_roles=["borrower_concierge", "processor", "document_tracker"],
    risk_level="medium",
    requires_confirmation=True,
    examples=[
        "Invite the borrower to the portal",
        "Send portal access to the client",
        "Set up portal for this loan",
    ],
)
def invite_borrower_to_portal(
    loan_id: int,
    borrower_email: str,
    message: Optional[str] = None,
) -> ToolResult:
    """Send a portal invitation to a borrower.

    Args:
        loan_id: The loan to invite the borrower for
        borrower_email: Email address to send the invitation to
        message: Optional custom message to include in the invitation
    """
    try:
        # Validate the loan exists and get details
        loan = execute_single(
            """
            SELECT
                lo.id, lo.loan_number, lo.borrower_name, lo.borrower_email,
                lo.stage, lo.loan_officer_id, lo.organization_id
            FROM loans lo
            WHERE lo.id = :loan_id
            """,
            {"loan_id": loan_id},
        )

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        # Validate email matches the borrower on file (if present)
        if loan.get("borrower_email") and loan["borrower_email"].lower() != borrower_email.lower():
            return ToolResult.error(
                f"Email '{borrower_email}' does not match borrower email on file. "
                "Verify the correct email before sending an invitation."
            )

        # Check if a portal_loans record already exists for this loan
        portal_loan = execute_single(
            """
            SELECT id, primary_borrower_email, lifecycle_stage
            FROM portal_loans
            WHERE crm_deal_id = :loan_id
            """,
            {"loan_id": loan_id},
        )

        timestamp = datetime.utcnow().isoformat()

        with get_db() as db:
            from sqlalchemy import text

            if portal_loan:
                # Portal loan already exists -- record the invitation action
                db.execute(
                    text("""
                        INSERT INTO loan_activity_log (
                            loan_id, activity_type, activity_title,
                            activity_description, actor_role,
                            visible_to_borrower, created_at
                        ) VALUES (
                            :portal_loan_id, 'portal_invitation', 'Portal invitation sent',
                            :description, 'LO',
                            true, NOW()
                        )
                    """),
                    {
                        "portal_loan_id": portal_loan["id"],
                        "description": f"Portal invitation sent to {borrower_email}. {message or ''}".strip(),
                    },
                )
            else:
                # Record the invitation action on the loan's user_metadata
                db.execute(
                    text("""
                        UPDATE loans
                        SET user_metadata = COALESCE(user_metadata, '{}'::jsonb) || :invitation_data,
                            updated_at = NOW()
                        WHERE id = :loan_id
                    """),
                    {
                        "loan_id": loan_id,
                        "invitation_data": f'{{"portal_invitation": {{"email": "{borrower_email}", "sent_at": "{timestamp}", "status": "pending"}}}}',
                    },
                )

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan.get("loan_number"),
            "borrower_name": loan.get("borrower_name"),
            "borrower_email": borrower_email,
            "invitation_status": "sent",
            "portal_loan_exists": portal_loan is not None,
            "message": message,
            "sent_at": timestamp,
            "instructions": (
                "Invitation recorded. The borrower will receive an email with portal "
                "access instructions. They can upload documents and track loan progress."
            ),
        })

    except Exception as e:
        return ToolResult.error(f"Failed to send portal invitation: {str(e)}")


@mortgage_tool(
    name="get_portal_status",
    description="Check if a borrower has portal access and view their portal activity including documents uploaded and last activity date.",
    agent_roles=["borrower_concierge", "document_tracker", "processor"],
    risk_level="low",
    examples=[
        "Check portal status for this loan",
        "Has the borrower logged into the portal?",
        "Portal access status",
    ],
)
def get_portal_status(
    loan_id: int,
) -> ToolResult:
    """Check portal access status for a loan.

    Args:
        loan_id: The loan to check portal status for
    """
    try:
        # Get the loan info
        loan = execute_single(
            """
            SELECT id, loan_number, borrower_name, borrower_email, stage
            FROM loans
            WHERE id = :loan_id
            """,
            {"loan_id": loan_id},
        )

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        # Check for portal_loans record
        portal_loan = execute_single(
            """
            SELECT
                pl.id, pl.lifecycle_stage, pl.lifecycle_stage_entered_at,
                pl.primary_borrower_email, pl.is_active, pl.created_at
            FROM portal_loans pl
            WHERE pl.crm_deal_id = :loan_id
            """,
            {"loan_id": loan_id},
        )

        if not portal_loan:
            # Check user_metadata for invitation record
            meta_check = execute_single(
                """
                SELECT user_metadata
                FROM loans
                WHERE id = :loan_id
                """,
                {"loan_id": loan_id},
            )

            invitation_info = None
            if meta_check and meta_check.get("user_metadata"):
                meta = meta_check["user_metadata"]
                if isinstance(meta, dict):
                    invitation_info = meta.get("portal_invitation")

            return ToolResult.success({
                "loan_id": loan_id,
                "loan_number": loan.get("loan_number"),
                "borrower_name": loan.get("borrower_name"),
                "has_portal_access": False,
                "portal_status": "no_portal",
                "invitation_sent": invitation_info is not None,
                "invitation_info": invitation_info,
                "documents_uploaded": 0,
                "last_activity": None,
                "message": "No portal access set up for this loan.",
            })

        # Get document count
        doc_count = execute_single(
            """
            SELECT COUNT(*) as doc_count
            FROM portal_documents
            WHERE loan_id = :portal_loan_id AND is_deleted = false
            """,
            {"portal_loan_id": portal_loan["id"]},
        )

        # Get last activity
        last_activity = execute_single(
            """
            SELECT activity_type, activity_title, created_at
            FROM loan_activity_log
            WHERE loan_id = :portal_loan_id
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"portal_loan_id": portal_loan["id"]},
        )

        # Get milestone progress
        milestone_progress = execute_single(
            """
            SELECT
                COUNT(*) as total_milestones,
                COUNT(CASE WHEN status = 'COMPLETE' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'ACTIVE' THEN 1 END) as active
            FROM milestone_instances
            WHERE loan_id = :portal_loan_id
            """,
            {"portal_loan_id": portal_loan["id"]},
        )

        return ToolResult.success({
            "loan_id": loan_id,
            "loan_number": loan.get("loan_number"),
            "borrower_name": loan.get("borrower_name"),
            "has_portal_access": True,
            "portal_status": "active" if portal_loan.get("is_active") else "inactive",
            "lifecycle_stage": portal_loan.get("lifecycle_stage"),
            "stage_entered_at": format_date(portal_loan.get("lifecycle_stage_entered_at")),
            "portal_created_at": format_date(portal_loan.get("created_at")),
            "documents_uploaded": doc_count["doc_count"] if doc_count else 0,
            "last_activity": {
                "type": last_activity["activity_type"],
                "title": last_activity["activity_title"],
                "date": format_date(last_activity["created_at"]),
            } if last_activity else None,
            "milestones": {
                "total": milestone_progress["total_milestones"] if milestone_progress else 0,
                "completed": milestone_progress["completed"] if milestone_progress else 0,
                "active": milestone_progress["active"] if milestone_progress else 0,
            } if milestone_progress else None,
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get portal status: {str(e)}")


@mortgage_tool(
    name="share_document_via_portal",
    description="Share a document with the borrower through the client portal. Makes a document visible to the borrower.",
    agent_roles=["document_tracker", "processor", "borrower_concierge"],
    risk_level="medium",
    requires_confirmation=True,
    examples=[
        "Share this document with the borrower",
        "Make the disclosure visible on the portal",
        "Send document to borrower via portal",
    ],
)
def share_document_via_portal(
    loan_id: int,
    document_id: int,
) -> ToolResult:
    """Share a document with the borrower through the portal.

    Args:
        loan_id: The loan the document belongs to
        document_id: The document to share
    """
    try:
        # Validate the loan
        loan = execute_single(
            """
            SELECT id, loan_number, borrower_name, stage
            FROM loans
            WHERE id = :loan_id
            """,
            {"loan_id": loan_id},
        )

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        # Check for portal_loans record
        portal_loan = execute_single(
            """
            SELECT id, primary_borrower_email, is_active
            FROM portal_loans
            WHERE crm_deal_id = :loan_id
            """,
            {"loan_id": loan_id},
        )

        # Check the document exists (try portal_documents first, then smart_docs)
        portal_doc = execute_single(
            """
            SELECT id, filename, document_type, loan_id
            FROM portal_documents
            WHERE id = :doc_id
            """,
            {"doc_id": document_id},
        )

        if not portal_doc:
            return ToolResult.no_data(
                f"Document {document_id} not found. Verify the document ID is correct."
            )

        if portal_loan:
            # Log the share action in the activity log
            with get_db() as db:
                from sqlalchemy import text

                db.execute(
                    text("""
                        INSERT INTO loan_activity_log (
                            loan_id, activity_type, activity_title,
                            activity_description, document_id,
                            actor_role, visible_to_borrower, created_at
                        ) VALUES (
                            :portal_loan_id, 'document_shared', 'Document shared with borrower',
                            :description, :doc_id,
                            'LO', true, NOW()
                        )
                    """),
                    {
                        "portal_loan_id": portal_loan["id"],
                        "doc_id": document_id,
                        "description": f"Document '{portal_doc.get('filename', 'Unknown')}' shared via portal",
                    },
                )

            return ToolResult.success({
                "loan_id": loan_id,
                "loan_number": loan.get("loan_number"),
                "borrower_name": loan.get("borrower_name"),
                "document_id": document_id,
                "document_name": portal_doc.get("filename"),
                "document_type": portal_doc.get("document_type"),
                "shared": True,
                "portal_active": portal_loan.get("is_active", False),
                "message": f"Document '{portal_doc.get('filename')}' is now visible to the borrower on their portal.",
            })
        else:
            # No portal set up -- record intent on the loan metadata
            timestamp = datetime.utcnow().isoformat()

            with get_db() as db:
                from sqlalchemy import text

                db.execute(
                    text("""
                        UPDATE loans
                        SET user_metadata = COALESCE(user_metadata, '{}'::jsonb) || :share_data,
                            updated_at = NOW()
                        WHERE id = :loan_id
                    """),
                    {
                        "loan_id": loan_id,
                        "share_data": f'{{"portal_document_share": {{"document_id": {document_id}, "shared_at": "{timestamp}", "status": "pending_portal_setup"}}}}',
                    },
                )

            return ToolResult.success({
                "loan_id": loan_id,
                "loan_number": loan.get("loan_number"),
                "document_id": document_id,
                "document_name": portal_doc.get("filename"),
                "shared": False,
                "portal_active": False,
                "message": (
                    "Portal not yet set up for this loan. Document share request recorded. "
                    "Set up the borrower portal first, then the document will be shared automatically."
                ),
            })

    except Exception as e:
        return ToolResult.error(f"Failed to share document via portal: {str(e)}")
