"""
Workflow Models for Post-Closing Referral Automation
Pipeline 360 - TL Development, LLC

SQLAlchemy models for:
- EmployerRecord
- Opportunity
- RecurringTask
- WorkflowExecution
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Numeric, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class EmployerRecord(Base):
    """Tracks workplace/employer partnership opportunities"""
    __tablename__ = "employer_records"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(255), nullable=False, index=True)
    champion_lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    status = Column(String(50), default="Opportunity Identified", index=True)
    employee_count = Column(Integer, nullable=True)
    source = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    champion_lead = relationship("Lead", back_populates="employer_records", foreign_keys=[champion_lead_id])
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<EmployerRecord(id={self.id}, company={self.company_name}, status={self.status})>"


class Opportunity(Base):
    """B2B partnership pipeline management"""
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(100), nullable=False, index=True)
    primary_lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    company_name = Column(String(255), nullable=True, index=True)
    stage = Column(String(50), default="Initial Discovery", index=True)
    estimated_value = Column(Numeric(10, 2), nullable=True)
    estimated_employee_count = Column(Integer, nullable=True)
    champion_name = Column(String(255), nullable=True)
    source = Column(String(100), nullable=True)
    status = Column(String(50), default="Active", index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Relationships
    primary_lead = relationship("Lead", back_populates="opportunities", foreign_keys=[primary_lead_id])
    assigned_user = relationship("User", foreign_keys=[assigned_to])

    def __repr__(self):
        return f"<Opportunity(id={self.id}, type={self.type}, company={self.company_name}, stage={self.stage})>"


class RecurringTask(Base):
    """Automated quarterly check-ins and recurring follow-ups"""
    __tablename__ = "recurring_tasks"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    recurrence_pattern = Column(String(50), nullable=True)
    recurrence_interval_days = Column(Integer, nullable=True, index=True)
    priority = Column(String(20), default="medium", index=True)
    category = Column(String(100), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    next_due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    last_completed_date = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    lead = relationship("Lead", back_populates="recurring_tasks", foreign_keys=[lead_id])
    assigned_user = relationship("User", foreign_keys=[assigned_to])

    def __repr__(self):
        return f"<RecurringTask(id={self.id}, title={self.title}, next_due={self.next_due_date})>"


class WorkflowExecution(Base):
    """Audit log of all workflow runs"""
    __tablename__ = "workflow_executions"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(String(100), nullable=False, index=True)
    workflow_name = Column(String(255), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True, index=True)
    trigger_event = Column(String(100), nullable=True, index=True)
    execution_status = Column(String(50), nullable=True, index=True)
    actions_completed = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    lead = relationship("Lead", back_populates="workflow_executions", foreign_keys=[lead_id])
    loan = relationship("Loan", back_populates="workflow_executions", foreign_keys=[loan_id])

    def __repr__(self):
        return f"<WorkflowExecution(id={self.id}, workflow={self.workflow_id}, status={self.execution_status})>"
