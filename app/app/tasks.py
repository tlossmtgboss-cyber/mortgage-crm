from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import sys
sys.path.append('..')
from app.db import get_db
from app.models import Activity

router = APIRouter(
    prefix="/api/tasks",
    tags=["tasks"]
)

# Pydantic schemas for Tasks (using Activity model)
class TaskBase(BaseModel):
    lead_id: int
    activity_type: str  # e.g., 'call', 'email', 'meeting', 'note', 'follow-up'
    subject: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = "scheduled"  # e.g., 'scheduled', 'in_progress', 'completed', 'cancelled'
    due_date: Optional[datetime] = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    lead_id: Optional[int] = None
    activity_type: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class TaskResponse(TaskBase):
    id: int
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

# CRUD endpoints for Tasks
@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    """Create a new task"""
    db_task = Activity(**task.dict())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

@router.get("/", response_model=List[TaskResponse])
def get_tasks(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    activity_type: Optional[str] = None,
    lead_id: Optional[int] = None,
    overdue: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Get all tasks with optional filters"""
    query = db.query(Activity)
    
    if status_filter:
        query = query.filter(Activity.status == status_filter)
    if activity_type:
        query = query.filter(Activity.activity_type == activity_type)
    if lead_id:
        query = query.filter(Activity.lead_id == lead_id)
    if overdue is not None:
        now = datetime.utcnow()
        if overdue:
            query = query.filter(Activity.due_date < now, Activity.status != 'completed')
        else:
            query = query.filter(Activity.due_date >= now)
    
    tasks = query.order_by(Activity.due_date).offset(skip).limit(limit).all()
    return tasks

@router.get("/upcoming", response_model=List[TaskResponse])
def get_upcoming_tasks(
    days: int = 7,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get upcoming tasks for the next N days"""
    from datetime import timedelta
    now = datetime.utcnow()
    future_date = now + timedelta(days=days)
    
    tasks = db.query(Activity).filter(
        Activity.due_date >= now,
        Activity.due_date <= future_date,
        Activity.status != 'completed'
    ).order_by(Activity.due_date).limit(limit).all()
    
    return tasks

@router.get("/overdue", response_model=List[TaskResponse])
def get_overdue_tasks(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get all overdue tasks"""
    now = datetime.utcnow()
    tasks = db.query(Activity).filter(
        Activity.due_date < now,
        Activity.status != 'completed'
    ).order_by(Activity.due_date).limit(limit).all()
    
    return tasks

@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """Get a specific task by ID"""
    task = db.query(Activity).filter(Activity.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task_update: TaskUpdate, db: Session = Depends(get_db)):
    """Update a task"""
    db_task = db.query(Activity).filter(Activity.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_data = task_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_task, field, value)
    
    # Auto-set completed_at if status is being set to completed
    if update_data.get('status') == 'completed' and not db_task.completed_at:
        db_task.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_task)
    return db_task

@router.patch("/{task_id}/complete", response_model=TaskResponse)
def complete_task(task_id: int, db: Session = Depends(get_db)):
    """Mark a task as completed"""
    db_task = db.query(Activity).filter(Activity.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db_task.status = 'completed'
    db_task.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_task)
    return db_task

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """Delete a task"""
    db_task = db.query(Activity).filter(Activity.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db.delete(db_task)
    db.commit()
    return None
