"""
Workflow Role Assignment Routes

This module handles workflow role assignment endpoints including:
- Getting available roles
- Loan role assignments (get, assign, remove)
- Lead role assignments (get, assign, remove)
- Copying role assignments from lead to loan
- Resolving users for roles
- Default team role settings
- Seeding workflow roles
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Workflow Roles"])


# ============================================================================
# RUNTIME IMPORT HELPERS
# ============================================================================

def get_current_user_dep():
    """Get current user dependency - imports from main at runtime to avoid circular imports."""
    import main
    return main.get_current_user


def get_user_model():
    """Get User model - imports from main at runtime to avoid circular imports."""
    import main
    return main.User


def get_loan_model():
    """Get Loan model - imports from main at runtime to avoid circular imports."""
    import main
    return main.Loan


def get_lead_model():
    """Get Lead model - imports from main at runtime to avoid circular imports."""
    import main
    return main.Lead


# All workflow roles from the Active Loan Workflow page
WORKFLOW_ROLES = [
    {"name": "Admin", "code": "ADM", "description": "System administrator with full access"},
    {"name": "Application Analysis", "code": "AA", "description": "Analyzes and processes loan applications"},
    {"name": "Branch Manager", "code": "BM", "description": "Branch manager overseeing branch operations"},
    {"name": "Closer", "code": "CLO", "description": "Handles loan closing process"},
    {"name": "Concierge", "code": "CON", "description": "Client-facing concierge support"},
    {"name": "Executive Management", "code": "EM", "description": "Executive management team"},
    {"name": "Funder", "code": "FUN", "description": "Handles loan funding process"},
    {"name": "Jr. Loan Officer", "code": "JLO", "description": "Junior loan officer in training"},
    {"name": "Jr. Processor", "code": "JP", "description": "Junior processor in training"},
    {"name": "Loan Officer", "code": "LO", "description": "Primary loan officer handling client relationships"},
    {"name": "Loan Officer Assistant", "code": "LOA", "description": "Assists loan officer with administrative tasks"},
    {"name": "Management", "code": "MAN", "description": "Management role with oversight responsibilities"},
    {"name": "Operations Manager", "code": "OM", "description": "Oversees daily operations"},
    {"name": "Processing Assistant", "code": "PA", "description": "Assists processor with loan processing tasks"},
    {"name": "Processor", "code": "PRO", "description": "Handles loan processing and documentation"},
    {"name": "Production Assistant 1", "code": "PA1", "description": "First level production assistant"},
    {"name": "Production Assistant 2", "code": "PA2", "description": "Second level production assistant"},
    {"name": "Site Admin", "code": "SA", "description": "Site-level administrator"},
    {"name": "Site Administrator", "code": "SA2", "description": "Site-level administrator with full site access"},
    {"name": "Company Admin", "code": "CA", "description": "Company-level administrator"},
    {"name": "Underwriter", "code": "UND", "description": "Reviews and approves loan applications"},
]


# ============================================================================
# WORKFLOW ROLE ASSIGNMENT ENDPOINTS
# ============================================================================

@router.get("/roles")
async def get_available_roles(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get all available roles for workflow assignment."""
    from services.workflow_role_assignment import get_role_assignment_service

    try:
        service = get_role_assignment_service(db)
        roles = service.get_available_roles()
        return {"roles": roles, "count": len(roles)}
    except Exception as e:
        logger.error(f"Error fetching roles: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/loans/{loan_id}/roles")
async def get_loan_role_assignments(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get all role assignments for a loan."""
    from services.workflow_role_assignment import get_role_assignment_service


    Loan = get_loan_model()

    try:
        # Verify loan exists
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        service = get_role_assignment_service(db)
        assignments = service.get_loan_role_assignments(loan_id)

        return {
            "loan_id": loan_id,
            "assignments": assignments,
            "count": len(assignments)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching loan role assignments: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/loans/{loan_id}/roles/{role_id}/assign")
async def assign_role_to_loan(
    loan_id: int,
    role_id: int,
    user_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Assign a user to a role for a specific loan."""
    from services.workflow_role_assignment import get_role_assignment_service



    try:
        service = get_role_assignment_service(db)
        result = service.assign_role_to_loan(
            loan_id=loan_id,
            role_id=role_id,
            user_id=user_id,
            assigned_by_id=current_user.id
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning role to loan: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/loans/{loan_id}/roles/{role_id}")
async def remove_role_from_loan(
    loan_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Remove a role assignment from a loan."""
    from services.workflow_role_assignment import get_role_assignment_service



    try:
        service = get_role_assignment_service(db)
        result = service.remove_role_from_loan(loan_id, role_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing role from loan: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/leads/{lead_id}/roles")
async def get_lead_role_assignments(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get all role assignments for a lead."""
    from services.workflow_role_assignment import get_role_assignment_service


    Lead = get_lead_model()

    try:
        # Verify lead exists
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        service = get_role_assignment_service(db)
        assignments = service.get_lead_role_assignments(lead_id)

        return {
            "lead_id": lead_id,
            "assignments": assignments,
            "count": len(assignments)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lead role assignments: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/leads/{lead_id}/roles/{role_id}/assign")
async def assign_role_to_lead(
    lead_id: int,
    role_id: int,
    user_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Assign a user to a role for a specific lead."""
    from services.workflow_role_assignment import get_role_assignment_service



    try:
        service = get_role_assignment_service(db)
        result = service.assign_role_to_lead(
            lead_id=lead_id,
            role_id=role_id,
            user_id=user_id,
            assigned_by_id=current_user.id
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning role to lead: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/leads/{lead_id}/roles/{role_id}")
async def remove_role_from_lead(
    lead_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Remove a role assignment from a lead."""
    from services.workflow_role_assignment import get_role_assignment_service



    try:
        service = get_role_assignment_service(db)
        result = service.remove_role_from_lead(lead_id, role_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing role from lead: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/loans/{loan_id}/roles/copy-from-lead/{lead_id}")
async def copy_role_assignments_to_loan(
    loan_id: int,
    lead_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Copy role assignments from a lead to a loan (when lead converts)."""
    from services.workflow_role_assignment import get_role_assignment_service



    try:
        service = get_role_assignment_service(db)
        result = service.copy_assignments_lead_to_loan(lead_id, loan_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error copying role assignments: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/loans/{loan_id}/roles/{role_id}/resolve")
async def resolve_user_for_loan_role(
    loan_id: int,
    role_id: int,
    fallback: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Resolve which user is assigned to a role for a loan."""
    from services.workflow_role_assignment import get_role_assignment_service


    User = get_user_model()

    try:
        service = get_role_assignment_service(db)
        user_id = service.resolve_user_for_role(
            role_id=role_id,
            loan_id=loan_id,
            fallback_to_owner=fallback
        )

        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            return {
                "role_id": role_id,
                "loan_id": loan_id,
                "resolved_user_id": user_id,
                "resolved_user_name": user.full_name if user else None,
                "resolved_user_email": user.email if user else None
            }
        else:
            return {
                "role_id": role_id,
                "loan_id": loan_id,
                "resolved_user_id": None,
                "message": "No user assigned to this role"
            }
    except Exception as e:
        logger.error(f"Error resolving role: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# DEFAULT TEAM ROLE SETTINGS ENDPOINTS
# ============================================================================

@router.get("/settings/team-roles")
async def get_default_role_assignments(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get default role assignments for the organization (Team Settings)."""


    try:
        # Auto-seed: ensure roles table exists and is populated
        try:
            count = db.execute(text("SELECT COUNT(*) FROM roles WHERE is_active = true")).scalar()
        except Exception as e:
            logger.error(f"Error querying roles table in get_default_role_assignments: {e}")
            count = 0

        if count == 0:
            logger.info("Roles table empty — auto-seeding workflow roles...")
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS roles (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    code VARCHAR(10),
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS default_role_assignments (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL DEFAULT 1,
                    role_id INTEGER NOT NULL,
                    user_id INTEGER,
                    assigned_by_id INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(organization_id, role_id)
                )
            """))
            for role in WORKFLOW_ROLES:
                db.execute(text("""
                    INSERT INTO roles (name, code, description, is_active, created_at, updated_at)
                    VALUES (:name, :code, :description, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (name) DO NOTHING
                """), role)
            db.commit()
            logger.info(f"Auto-seeded {len(WORKFLOW_ROLES)} workflow roles")

        # Get all roles with their default assignments
        result = db.execute(text("""
            SELECT
                r.id as role_id,
                r.name as role_name,
                r.description as role_description,
                dra.user_id,
                COALESCE(u.first_name || ' ' || u.last_name, u.first_name, u.last_name, '') as user_name,
                u.email as user_email
            FROM roles r
            LEFT JOIN default_role_assignments dra ON dra.role_id = r.id
                AND dra.organization_id = :org_id
            LEFT JOIN users u ON u.id = dra.user_id
            WHERE r.is_active = true
            ORDER BY r.name
        """), {"org_id": current_user.organization_id or 1}).fetchall()

        assignments = []
        for row in result:
            assignments.append({
                "role_id": row[0],
                "role_name": row[1],
                "role_description": row[2],
                "user_id": row[3],
                "user_name": row[4],
                "user_email": row[5]
            })

        return {
            "organization_id": current_user.organization_id or 1,
            "assignments": assignments,
            "count": len(assignments)
        }
    except Exception as e:
        logger.error(f"Error fetching default role assignments: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/settings/team-roles/{role_id}")
async def set_default_role_assignment(
    role_id: int,
    user_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Set default user for a role (Team Settings)."""

    User = get_user_model()

    try:
        org_id = current_user.organization_id or 1

        # Verify role exists
        role = db.execute(text("SELECT id, name FROM roles WHERE id = :role_id"),
                         {"role_id": role_id}).fetchone()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        # Verify user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Upsert the default assignment for this role
        # First try to update (in case someone else was assigned to this role)
        result = db.execute(text("""
            UPDATE default_role_assignments
            SET user_id = :user_id,
                assigned_by_id = :assigned_by_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE organization_id = :org_id AND role_id = :role_id
        """), {
            "org_id": org_id,
            "role_id": role_id,
            "user_id": user_id,
            "assigned_by_id": current_user.id
        })

        if result.rowcount == 0:
            # Insert new
            db.execute(text("""
                INSERT INTO default_role_assignments
                (organization_id, role_id, user_id, assigned_by_id)
                VALUES (:org_id, :role_id, :user_id, :assigned_by_id)
            """), {
                "org_id": org_id,
                "role_id": role_id,
                "user_id": user_id,
                "assigned_by_id": current_user.id
            })

        db.commit()

        return {
            "success": True,
            "message": f"Set {user.full_name} as default {role[1]}",
            "role_id": role_id,
            "role_name": role[1],
            "user_id": user_id,
            "user_name": user.full_name
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting default role assignment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/settings/team-roles/{role_id}")
async def remove_default_role_assignment(
    role_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Remove default user assignment for a role."""


    try:
        org_id = current_user.organization_id or 1

        db.execute(text("""
            DELETE FROM default_role_assignments
            WHERE organization_id = :org_id AND role_id = :role_id
        """), {"org_id": org_id, "role_id": role_id})

        db.commit()

        return {
            "success": True,
            "message": "Default role assignment removed"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing default role assignment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# SEED WORKFLOW ROLES ENDPOINT
# ============================================================================

@router.post("/settings/seed-workflow-roles")
async def seed_workflow_roles(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Seed workflow roles into the database."""


    try:
        # Ensure the roles table exists
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS roles (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                code VARCHAR(10),
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Ensure the default_role_assignments table exists
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS default_role_assignments (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL DEFAULT 1,
                role_id INTEGER NOT NULL,
                user_id INTEGER,
                assigned_by_id INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, role_id)
            )
        """))

        db.commit()

        added_count = 0
        updated_count = 0
        skipped_count = 0

        for role in WORKFLOW_ROLES:
            # Check if role already exists
            existing = db.execute(
                text("SELECT id, code FROM roles WHERE name = :name"),
                {"name": role["name"]}
            ).fetchone()

            if existing:
                # Update code if needed
                if existing[1] != role["code"]:
                    db.execute(
                        text("""
                            UPDATE roles SET code = :code, description = :description,
                            updated_at = CURRENT_TIMESTAMP WHERE name = :name
                        """),
                        {
                            "name": role["name"],
                            "code": role["code"],
                            "description": role["description"],
                        }
                    )
                    updated_count += 1
                else:
                    skipped_count += 1
            else:
                # Insert new role
                db.execute(
                    text("""
                        INSERT INTO roles (name, code, description, is_active, created_at, updated_at)
                        VALUES (:name, :code, :description, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """),
                    {
                        "name": role["name"],
                        "code": role["code"],
                        "description": role["description"],
                    }
                )
                added_count += 1

        db.commit()

        # Get total count
        total = db.execute(text("SELECT COUNT(*) FROM roles WHERE is_active = true")).scalar()

        return {
            "success": True,
            "message": f"Workflow roles seeded: {added_count} added, {updated_count} updated, {skipped_count} skipped",
            "added": added_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "total_roles": total
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding workflow roles: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
