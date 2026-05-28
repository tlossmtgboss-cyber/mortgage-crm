"""
Workflow Role Assignment Service

Manages role assignments for workflow task routing.
Handles assigning users to roles for specific leads and loans.

Key responsibilities:
- Assign users to roles for leads/loans
- Get current role assignments
- Resolve role to user for task assignment
- Manage default role assignments from team structure
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class RoleAssignmentService:
    """
    Manages role assignments for workflow task routing.

    Provides methods to assign users to roles at the lead or loan level,
    and resolves role assignments when generating tasks.
    """

    def __init__(self, db: Session):
        self.db = db
        self._load_models()

    def _load_models(self):
        """Load required models."""
        from database.models import Lead, Loan, User
        from models.user_onboarding import Role

        self.Lead = Lead
        self.Loan = Loan
        self.User = User
        self.Role = Role

    # =========================================================================
    # LEAD ROLE ASSIGNMENTS
    # =========================================================================

    def assign_role_to_lead(
        self,
        lead_id: int,
        role_id: int,
        user_id: int,
        assigned_by_id: int = None,
        organization_id: int = None
    ) -> Dict[str, Any]:
        """
        Assign a user to a role for a specific lead.

        Args:
            lead_id: Lead ID
            role_id: Role ID to assign
            user_id: User ID to assign
            assigned_by_id: User making the assignment
            organization_id: Organization ID (auto-detected if not provided)

        Returns:
            Dict with assignment result
        """
        try:
            # Verify lead exists
            lead = self.db.query(self.Lead).filter(self.Lead.id == lead_id).first()
            if not lead:
                return {"success": False, "error": "Lead not found"}

            # Verify role exists
            role = self.db.query(self.Role).filter(self.Role.id == role_id).first()
            if not role:
                return {"success": False, "error": "Role not found"}

            # Verify user exists
            user = self.db.query(self.User).filter(self.User.id == user_id).first()
            if not user:
                return {"success": False, "error": "User not found"}

            # Get organization ID
            if not organization_id:
                if lead.owner_id:
                    owner = self.db.query(self.User).filter(self.User.id == lead.owner_id).first()
                    organization_id = owner.organization_id if owner else None
                if not organization_id:
                    logger.warning(f"Cannot assign role for lead {lead_id}: no organization context")
                    return {"success": False, "error": "No organization context for lead"}

            # Deactivate existing assignment for this role
            self.db.execute(text("""
                UPDATE lead_workflow_role_assignments
                SET is_active = false, deactivated_at = NOW()
                WHERE lead_id = :lead_id AND role_id = :role_id AND is_active = true
            """), {"lead_id": lead_id, "role_id": role_id})

            # Create new assignment
            self.db.execute(text("""
                INSERT INTO lead_workflow_role_assignments (
                    organization_id, lead_id, role_id, assigned_user_id,
                    assigned_at, assigned_by_id, is_active,
                    created_at, updated_at
                ) VALUES (
                    :org_id, :lead_id, :role_id, :user_id,
                    NOW(), :assigned_by_id, true,
                    NOW(), NOW()
                )
            """), {
                "org_id": organization_id,
                "lead_id": lead_id,
                "role_id": role_id,
                "user_id": user_id,
                "assigned_by_id": assigned_by_id
            })
            self.db.commit()

            logger.info(f"Assigned user {user_id} to role {role.name} for lead {lead_id}")

            return {
                "success": True,
                "message": f"Assigned {user.name} as {role.name}",
                "assignment": {
                    "lead_id": lead_id,
                    "role_id": role_id,
                    "role_name": role.name,
                    "user_id": user_id,
                    "user_name": user.name
                }
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to assign role: {e}")
            return {"success": False, "error": "Internal server error"}

    def remove_role_from_lead(
        self,
        lead_id: int,
        role_id: int
    ) -> Dict[str, Any]:
        """Remove a role assignment from a lead."""
        try:
            result = self.db.execute(text("""
                UPDATE lead_workflow_role_assignments
                SET is_active = false, deactivated_at = NOW()
                WHERE lead_id = :lead_id AND role_id = :role_id AND is_active = true
            """), {"lead_id": lead_id, "role_id": role_id})

            self.db.commit()

            if result.rowcount > 0:
                return {"success": True, "message": "Role assignment removed"}
            else:
                return {"success": False, "error": "No active assignment found"}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to remove role: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_lead_role_assignments(self, lead_id: int) -> List[Dict[str, Any]]:
        """Get all active role assignments for a lead."""
        results = self.db.execute(text("""
            SELECT
                lra.id,
                lra.role_id,
                r.name as role_name,
                r.abbreviation as role_abbr,
                lra.assigned_user_id,
                u.full_name as user_name,
                u.email as user_email,
                lra.assigned_at
            FROM lead_workflow_role_assignments lra
            JOIN roles r ON r.id = lra.role_id
            JOIN users u ON u.id = lra.assigned_user_id
            WHERE lra.lead_id = :lead_id AND lra.is_active = true
            ORDER BY r.name
        """), {"lead_id": lead_id}).fetchall()

        return [
            {
                "id": row[0],
                "role_id": row[1],
                "role_name": row[2],
                "role_abbr": row[3],
                "user_id": row[4],
                "user_name": row[5],
                "user_email": row[6],
                "assigned_at": row[7].isoformat() if row[7] else None
            }
            for row in results
        ]

    # =========================================================================
    # LOAN ROLE ASSIGNMENTS
    # =========================================================================

    def assign_role_to_loan(
        self,
        loan_id: int,
        role_id: int,
        user_id: int,
        assigned_by_id: int = None,
        organization_id: int = None
    ) -> Dict[str, Any]:
        """
        Assign a user to a role for a specific loan.

        Args:
            loan_id: Loan ID
            role_id: Role ID to assign
            user_id: User ID to assign
            assigned_by_id: User making the assignment
            organization_id: Organization ID (auto-detected if not provided)

        Returns:
            Dict with assignment result
        """
        try:
            # Verify loan exists
            loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": "Loan not found"}

            # Verify role exists
            role = self.db.query(self.Role).filter(self.Role.id == role_id).first()
            if not role:
                return {"success": False, "error": "Role not found"}

            # Verify user exists
            user = self.db.query(self.User).filter(self.User.id == user_id).first()
            if not user:
                return {"success": False, "error": "User not found"}

            # Get organization ID
            if not organization_id:
                if loan.loan_officer_id:
                    lo = self.db.query(self.User).filter(self.User.id == loan.loan_officer_id).first()
                    organization_id = lo.organization_id if lo else None
                if not organization_id:
                    logger.warning(f"Cannot assign role for loan {loan_id}: no organization context")
                    return {"success": False, "error": "No organization context for loan"}

            # Deactivate existing assignment for this role
            self.db.execute(text("""
                UPDATE loan_workflow_role_assignments
                SET is_active = false, deactivated_at = NOW()
                WHERE loan_id = :loan_id AND role_id = :role_id AND is_active = true
            """), {"loan_id": loan_id, "role_id": role_id})

            # Create new assignment
            self.db.execute(text("""
                INSERT INTO loan_workflow_role_assignments (
                    organization_id, loan_id, role_id, assigned_user_id,
                    assigned_at, assigned_by_id, is_active,
                    created_at, updated_at
                ) VALUES (
                    :org_id, :loan_id, :role_id, :user_id,
                    NOW(), :assigned_by_id, true,
                    NOW(), NOW()
                )
            """), {
                "org_id": organization_id,
                "loan_id": loan_id,
                "role_id": role_id,
                "user_id": user_id,
                "assigned_by_id": assigned_by_id
            })
            self.db.commit()

            logger.info(f"Assigned user {user_id} to role {role.name} for loan {loan_id}")

            return {
                "success": True,
                "message": f"Assigned {user.name} as {role.name}",
                "assignment": {
                    "loan_id": loan_id,
                    "role_id": role_id,
                    "role_name": role.name,
                    "user_id": user_id,
                    "user_name": user.name
                }
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to assign role: {e}")
            return {"success": False, "error": "Internal server error"}

    def remove_role_from_loan(
        self,
        loan_id: int,
        role_id: int
    ) -> Dict[str, Any]:
        """Remove a role assignment from a loan."""
        try:
            result = self.db.execute(text("""
                UPDATE loan_workflow_role_assignments
                SET is_active = false, deactivated_at = NOW()
                WHERE loan_id = :loan_id AND role_id = :role_id AND is_active = true
            """), {"loan_id": loan_id, "role_id": role_id})

            self.db.commit()

            if result.rowcount > 0:
                return {"success": True, "message": "Role assignment removed"}
            else:
                return {"success": False, "error": "No active assignment found"}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to remove role: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_loan_role_assignments(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get all active role assignments for a loan."""
        results = self.db.execute(text("""
            SELECT
                lra.id,
                lra.role_id,
                r.name as role_name,
                r.abbreviation as role_abbr,
                lra.assigned_user_id,
                u.full_name as user_name,
                u.email as user_email,
                lra.assigned_at
            FROM loan_workflow_role_assignments lra
            JOIN roles r ON r.id = lra.role_id
            JOIN users u ON u.id = lra.assigned_user_id
            WHERE lra.loan_id = :loan_id AND lra.is_active = true
            ORDER BY r.name
        """), {"loan_id": loan_id}).fetchall()

        return [
            {
                "id": row[0],
                "role_id": row[1],
                "role_name": row[2],
                "role_abbr": row[3],
                "user_id": row[4],
                "user_name": row[5],
                "user_email": row[6],
                "assigned_at": row[7].isoformat() if row[7] else None
            }
            for row in results
        ]

    # =========================================================================
    # ROLE RESOLUTION
    # =========================================================================

    def resolve_user_for_role(
        self,
        role_id: int,
        lead_id: int = None,
        loan_id: int = None,
        fallback_to_owner: bool = True
    ) -> Optional[int]:
        """
        Resolve a role to a specific user ID.

        Checks entity-specific assignments first, then falls back to
        owner/loan officer if allowed.

        Args:
            role_id: Role ID to resolve
            lead_id: Lead ID (if entity is a lead)
            loan_id: Loan ID (if entity is a loan)
            fallback_to_owner: Whether to fall back to entity owner

        Returns:
            User ID or None if not resolvable
        """
        # 1. Check org-wide default_role_assignments (primary source of truth)
        try:
            org_id = None
            if lead_id:
                lead = self.db.query(self.Lead).filter(self.Lead.id == lead_id).first()
                if lead and lead.owner_id:
                    owner = self.db.query(self.User).filter(self.User.id == lead.owner_id).first()
                    org_id = owner.organization_id if owner else None
            elif loan_id:
                loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
                if loan and loan.loan_officer_id:
                    lo = self.db.query(self.User).filter(self.User.id == loan.loan_officer_id).first()
                    org_id = lo.organization_id if lo else None

            if not org_id:
                logger.warning(f"Cannot resolve user for role {role_id}: no organization context (lead_id={lead_id}, loan_id={loan_id})")
                return None

            default_result = self.db.execute(text("""
                SELECT user_id FROM default_role_assignments
                WHERE role_id = :role_id AND organization_id = :org_id AND user_id IS NOT NULL
                LIMIT 1
            """), {"role_id": role_id, "org_id": org_id}).fetchone()

            if default_result:
                return default_result[0]
        except Exception as e:
            logger.debug(f"Org-wide default lookup failed: {e}")

        # 2. Fallback to entity owner
        if fallback_to_owner:
            if lead_id:
                lead = self.db.query(self.Lead).filter(self.Lead.id == lead_id).first()
                if lead and lead.owner_id:
                    return lead.owner_id
            if loan_id:
                loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
                if loan and loan.loan_officer_id:
                    return loan.loan_officer_id

        # 3. Least-loaded user with this role
        try:
            org_fallback = self.db.execute(text("""
                SELECT u.id
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.id
                WHERE ur.role_id = :role_id
                AND u.is_active = true
                ORDER BY (
                    SELECT COUNT(*) FROM tasks t
                    WHERE t.owner_id = u.id AND t.status IN ('pending', 'in_progress')
                ) ASC
                LIMIT 1
            """), {"role_id": role_id}).fetchone()
            if org_fallback:
                logger.info(f"RL-004 fallback: assigned role {role_id} to least-loaded user {org_fallback[0]}")
                return org_fallback[0]
        except Exception as e:
            logger.debug(f"Org-level fallback lookup failed (user_roles table may not exist): {e}")

        return None

    def resolve_role_by_name(
        self,
        role_name: str,
        lead_id: int = None,
        loan_id: int = None,
        fallback_to_owner: bool = True
    ) -> Optional[int]:
        """
        Resolve a role by name to a specific user ID.

        Args:
            role_name: Role name (e.g., 'Loan Officer', 'Processor')
            lead_id: Lead ID
            loan_id: Loan ID
            fallback_to_owner: Whether to fall back to entity owner

        Returns:
            User ID or None
        """
        # Get role ID
        role = self.db.query(self.Role).filter(self.Role.name == role_name).first()
        if not role:
            return None

        return self.resolve_user_for_role(
            role_id=role.id,
            lead_id=lead_id,
            loan_id=loan_id,
            fallback_to_owner=fallback_to_owner
        )

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================

    def copy_assignments_lead_to_loan(
        self,
        lead_id: int,
        loan_id: int
    ) -> Dict[str, Any]:
        """
        Copy role assignments from a lead to a loan.

        Useful when a lead converts to a loan and we want to
        preserve the team structure.
        """
        try:
            # Get lead assignments
            lead_assignments = self.get_lead_role_assignments(lead_id)

            # Get loan's organization
            loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": "Loan not found"}

            org_id = None
            if loan.loan_officer_id:
                lo = self.db.query(self.User).filter(self.User.id == loan.loan_officer_id).first()
                org_id = lo.organization_id if lo else None
            if not org_id:
                logger.warning(f"Cannot copy role assignments to loan {loan_id}: no organization context")
                return {"success": False, "error": "No organization context for loan"}

            copied = 0
            for assignment in lead_assignments:
                # Check if role already assigned on loan
                existing = self.db.execute(text("""
                    SELECT 1 FROM loan_workflow_role_assignments
                    WHERE loan_id = :loan_id AND role_id = :role_id AND is_active = true
                """), {"loan_id": loan_id, "role_id": assignment["role_id"]}).fetchone()

                if not existing:
                    self.db.execute(text("""
                        INSERT INTO loan_workflow_role_assignments (
                            organization_id, loan_id, role_id, assigned_user_id,
                            assigned_at, is_active, created_at, updated_at
                        ) VALUES (
                            :org_id, :loan_id, :role_id, :user_id,
                            NOW(), true, NOW(), NOW()
                        )
                    """), {
                        "org_id": org_id,
                        "loan_id": loan_id,
                        "role_id": assignment["role_id"],
                        "user_id": assignment["user_id"]
                    })
                    copied += 1

            self.db.commit()

            return {
                "success": True,
                "message": f"Copied {copied} role assignments from lead to loan",
                "copied_count": copied
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to copy assignments: {e}")
            return {"success": False, "error": "Internal server error"}

    def get_available_roles(self) -> List[Dict[str, Any]]:
        """Get all available roles for assignment."""
        roles = self.db.query(self.Role).filter(
            self.Role.is_active == True
        ).order_by(self.Role.name).all()

        return [
            {
                "id": role.id,
                "name": role.name,
                "abbreviation": getattr(role, 'abbreviation', None),
                "description": role.description
            }
            for role in roles
        ]


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_role_assignment_service(db: Session) -> RoleAssignmentService:
    """Factory function to get a RoleAssignmentService instance."""
    return RoleAssignmentService(db)
