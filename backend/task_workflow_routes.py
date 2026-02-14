"""
Task and Workflow Management Routes
Handles bulk task uploads, workflow assignments, and task templates
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import csv
import io
import os
from datetime import datetime, timedelta
from pydantic import BaseModel

from database import get_db

router = APIRouter()
security = HTTPBearer(auto_error=False)


# User proxy class for auth
class UserProxy:
    def __init__(self, row):
        self.id = row[0]
        self.email = row[1]
        self.name = row[2]


# Auth dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user from JWT token."""
    from jose import jwt

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        secret = os.getenv("SECRET_KEY", "")
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = db.execute(
            text("SELECT id, email, full_name FROM users WHERE email = :email"),
            {"email": email}
        )
        user_row = result.fetchone()
        if not user_row:
            raise HTTPException(status_code=401, detail="User not found")

        return UserProxy(user_row)

    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Pydantic Models
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[str] = None
    category: str = "general"
    assigned_to: int
    status: str = "pending"

class WorkflowAssign(BaseModel):
    user_id: int

class TaskTemplate(BaseModel):
    id: int
    name: str
    description: str
    tasks: List[dict]

class Workflow(BaseModel):
    id: int
    name: str
    description: str
    category: str
    tasks_count: int


# Predefined workflows
WORKFLOWS = {
    "new-employee-onboarding": {
        "id": "new-employee-onboarding",
        "name": "New Employee Onboarding",
        "description": "Complete onboarding process for new team members",
        "category": "onboarding",
        "tasks": [
            {
                "title": "Complete employee information form",
                "description": "Fill out all required personal and tax information",
                "priority": "high",
                "category": "onboarding",
                "due_days": 1
            },
            {
                "title": "Review company handbook",
                "description": "Read and acknowledge company policies and procedures",
                "priority": "high",
                "category": "onboarding",
                "due_days": 3
            },
            {
                "title": "Set up workstation and accounts",
                "description": "Configure email, computer, and necessary software accounts",
                "priority": "high",
                "category": "setup",
                "due_days": 1
            },
            {
                "title": "Complete compliance training",
                "description": "Finish all required regulatory and compliance training modules",
                "priority": "high",
                "category": "training",
                "due_days": 7
            },
            {
                "title": "Schedule 1-on-1 with manager",
                "description": "Initial check-in meeting to discuss role and expectations",
                "priority": "high",
                "category": "meeting",
                "due_days": 2
            },
            {
                "title": "Meet the team",
                "description": "Introduction meetings with key team members and stakeholders",
                "priority": "medium",
                "category": "meeting",
                "due_days": 5
            },
            {
                "title": "Review systems and tools",
                "description": "Training on CRM, communication tools, and other systems",
                "priority": "high",
                "category": "training",
                "due_days": 7
            },
            {
                "title": "30-day check-in",
                "description": "Review progress and address any questions or concerns",
                "priority": "medium",
                "category": "review",
                "due_days": 30
            }
        ]
    },
    "loan-officer-setup": {
        "id": "loan-officer-setup",
        "name": "Loan Officer Setup",
        "description": "Onboarding tasks specific to loan officers",
        "category": "role-specific",
        "tasks": [
            {
                "title": "Complete NMLS registration",
                "description": "Register or transfer NMLS license",
                "priority": "urgent",
                "category": "compliance",
                "due_days": 1
            },
            {
                "title": "Learn CRM lead management",
                "description": "Training on lead tracking and management in CRM",
                "priority": "high",
                "category": "training",
                "due_days": 3
            },
            {
                "title": "Review loan products and guidelines",
                "description": "Study available loan products and underwriting guidelines",
                "priority": "high",
                "category": "training",
                "due_days": 7
            },
            {
                "title": "Shadow experienced LO",
                "description": "Observe client consultations and application process",
                "priority": "high",
                "category": "training",
                "due_days": 5
            },
            {
                "title": "Set up email signature and marketing materials",
                "description": "Configure professional branding and marketing collateral",
                "priority": "medium",
                "category": "setup",
                "due_days": 2
            }
        ]
    },
    "processor-training": {
        "id": "processor-training",
        "name": "Processor Training",
        "description": "Training workflow for loan processors",
        "category": "role-specific",
        "tasks": [
            {
                "title": "Learn loan processing workflow",
                "description": "Understand the complete loan processing lifecycle",
                "priority": "high",
                "category": "training",
                "due_days": 3
            },
            {
                "title": "Master document collection",
                "description": "Training on required documents and collection procedures",
                "priority": "high",
                "category": "training",
                "due_days": 5
            },
            {
                "title": "Practice with test files",
                "description": "Work through sample loan files for hands-on experience",
                "priority": "high",
                "category": "training",
                "due_days": 7
            },
            {
                "title": "Learn underwriting guidelines",
                "description": "Study underwriting requirements and common conditions",
                "priority": "high",
                "category": "training",
                "due_days": 7
            }
        ]
    },
    "underwriter-onboarding": {
        "id": "underwriter-onboarding",
        "name": "Underwriter Onboarding",
        "description": "Onboarding process for underwriters",
        "category": "role-specific",
        "tasks": [
            {
                "title": "Review underwriting authority and guidelines",
                "description": "Study delegation of authority and underwriting guidelines",
                "priority": "urgent",
                "category": "compliance",
                "due_days": 1
            },
            {
                "title": "Complete underwriting certification",
                "description": "Pass required underwriting certification assessments",
                "priority": "high",
                "category": "compliance",
                "due_days": 7
            },
            {
                "title": "Shadow senior underwriter",
                "description": "Observe file reviews and decision-making process",
                "priority": "high",
                "category": "training",
                "due_days": 5
            },
            {
                "title": "Review sample underwriting scenarios",
                "description": "Analyze and practice with various loan scenarios",
                "priority": "high",
                "category": "training",
                "due_days": 7
            }
        ]
    }
}


@router.post("/api/v1/tasks/bulk-upload")
async def bulk_upload_tasks(
    file: UploadFile = File(...),
    assigned_to: int = Form(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Bulk upload tasks from CSV file
    CSV format: title,description,priority,due_date,category,status
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        # Read CSV file
        contents = await file.read()
        csv_data = contents.decode('utf-8')
        csv_file = io.StringIO(csv_data)
        reader = csv.DictReader(csv_file)

        created_count = 0
        tasks_to_create = []

        for row in reader:
            # Validate required fields
            if not row.get('title'):
                continue

            # Parse due date
            due_date = None
            if row.get('due_date'):
                try:
                    due_date = datetime.strptime(row['due_date'], '%Y-%m-%d')
                except ValueError:
                    pass

            task_data = {
                'title': row['title'],
                'description': row.get('description', ''),
                'priority': row.get('priority', 'medium'),
                'due_date': due_date,
                'status': row.get('status', 'pending'),
                'owner_id': assigned_to
            }
            tasks_to_create.append(task_data)

        # Bulk insert tasks
        if tasks_to_create:
            for task_data in tasks_to_create:
                db.execute(
                    text("""
                        INSERT INTO tasks (title, description, priority, due_date, status, owner_id, created_at, updated_at)
                        VALUES (:title, :description, :priority, :due_date, :status, :owner_id, NOW(), NOW())
                    """),
                    task_data
                )
                created_count += 1

            db.commit()

        return {
            "success": True,
            "created_count": created_count,
            "message": f"Successfully created {created_count} tasks"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error processing CSV")


@router.get("/api/v1/tasks/templates")
async def get_task_templates(
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get task templates
    """
    # This is a placeholder - replace with actual DB query
    templates = [
        {
            "id": 1,
            "name": "New Hire Onboarding",
            "description": "Standard tasks for new employees",
            "category": "onboarding",
            "task_count": 8
        },
        {
            "id": 2,
            "name": "Loan Officer Training",
            "description": "Training tasks for new loan officers",
            "category": "training",
            "task_count": 5
        }
    ]

    if category:
        templates = [t for t in templates if t['category'] == category]

    return {"success": True, "templates": templates}


@router.get("/api/v1/workflows")
async def get_workflows(
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get available workflows
    """
    workflows = []
    for workflow_id, workflow_data in WORKFLOWS.items():
        workflow = {
            "id": workflow_id,
            "name": workflow_data["name"],
            "description": workflow_data["description"],
            "category": workflow_data["category"],
            "tasks_count": len(workflow_data["tasks"])
        }
        if not category or workflow_data["category"] == category:
            workflows.append(workflow)

    return {"success": True, "workflows": workflows}


@router.get("/api/v1/workflows/{workflow_id}")
async def get_workflow_details(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed workflow information
    """
    if workflow_id not in WORKFLOWS:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = WORKFLOWS[workflow_id]
    return {
        "id": workflow_id,
        "name": workflow["name"],
        "description": workflow["description"],
        "category": workflow["category"],
        "tasks": workflow["tasks"]
    }


@router.post("/api/v1/workflows/{workflow_id}/assign")
async def assign_workflow(
    workflow_id: str,
    assignment: WorkflowAssign,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Assign a workflow to a user (creates all tasks in the workflow)
    """
    if workflow_id not in WORKFLOWS:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = WORKFLOWS[workflow_id]
    created_count = 0

    try:
        for task_template in workflow["tasks"]:
            # Calculate due date based on due_days
            due_date = None
            if task_template.get("due_days"):
                due_date = datetime.now() + timedelta(days=task_template["due_days"])

            task_data = {
                'title': task_template['title'],
                'description': task_template.get('description', ''),
                'priority': task_template.get('priority', 'medium'),
                'due_date': due_date,
                'status': 'pending',
                'owner_id': assignment.user_id
            }

            db.execute(
                text("""
                    INSERT INTO tasks (title, description, priority, due_date, status, owner_id, created_at, updated_at)
                    VALUES (:title, :description, :priority, :due_date, :status, :owner_id, NOW(), NOW())
                """),
                task_data
            )
            created_count += 1

        db.commit()

        return {
            "success": True,
            "tasks_created": created_count,
            "workflow_name": workflow["name"],
            "message": f"Successfully assigned workflow to user. Created {created_count} tasks."
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error assigning workflow")
