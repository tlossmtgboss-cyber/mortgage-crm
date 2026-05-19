"""
HR, Goals & Skills Models

Job descriptions, skills, responsibilities, goals/OKRs, and skill assessments.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.hr_goals import UserJobDescription, Skill, UserGoal, GoalKeyResult
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, UniqueConstraint, Numeric
)
from sqlalchemy.orm import relationship

from db import Base


class UserJobDescription(Base):
    __tablename__ = "user_job_descriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Skill(Base):
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    category = Column(String(100), nullable=True)  # 'technical', 'soft_skill', 'domain_knowledge', etc.
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class EmployeeResponsibility(Base):
    __tablename__ = "employee_responsibilities"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    ownership = Column(String(50), nullable=False)  # 'primary', 'secondary', 'shared'
    time_allocation = Column(Integer, nullable=True)  # 0-100 percentage
    priority = Column(String(50), nullable=False)  # 'critical', 'high', 'medium', 'low'
    effective_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    archived = Column(Boolean, default=False, index=True)
    display_order = Column(Integer, default=0, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ResponsibilitySkill(Base):
    __tablename__ = "responsibility_skills"
    responsibility_id = Column(Integer, ForeignKey("employee_responsibilities.id", ondelete="CASCADE"), primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)


# Goals & OKRs Models
class UserGoal(Base):
    __tablename__ = "user_goals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    objective = Column(Text, nullable=False)  # The main goal statement
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(SQLEnum('not_started', 'on_track', 'at_risk', 'blocked', 'completed', name='goal_status'), default='not_started')
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    key_results = relationship("GoalKeyResult", back_populates="goal", cascade="all, delete-orphan")
    employee_assessment = relationship("GoalEmployeeAssessment", uselist=False, back_populates="goal", cascade="all, delete-orphan")
    manager_assessment = relationship("GoalManagerAssessment", uselist=False, back_populates="goal", cascade="all, delete-orphan")


class GoalKeyResult(Base):
    __tablename__ = "goal_key_results"
    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("user_goals.id", ondelete="CASCADE"), nullable=False, index=True)
    metric = Column(String(255), nullable=False)  # "Close loans", "Total volume"
    target = Column(Numeric(18, 2), nullable=False)  # 15, 5000000
    current = Column(Numeric(18, 2), default=0)  # Current progress
    unit = Column(String(50), nullable=True)  # "loans", "dollars", "percent"
    status = Column(SQLEnum('not_started', 'on_track', 'at_risk', 'ahead', 'completed', name='key_result_status'), default='not_started')

    # Relationship
    goal = relationship("UserGoal", back_populates="key_results")


class GoalEmployeeAssessment(Base):
    __tablename__ = "goal_employee_assessments"
    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("user_goals.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    progress_percent = Column(Integer, nullable=True)  # 0-100
    status = Column(SQLEnum('on_track', 'at_risk', 'blocked', name='assessment_status'), default='on_track')
    achievements = Column(Text, nullable=True)
    challenges = Column(Text, nullable=True)
    support_needed = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    goal = relationship("UserGoal", back_populates="employee_assessment")


class GoalManagerAssessment(Base):
    __tablename__ = "goal_manager_assessments"
    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("user_goals.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    notes = Column(Text, nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    goal = relationship("UserGoal", back_populates="manager_assessment")


# Junction table for goals <-> responsibilities
class GoalResponsibility(Base):
    __tablename__ = "goal_responsibilities"
    goal_id = Column(Integer, ForeignKey("user_goals.id", ondelete="CASCADE"), primary_key=True)
    responsibility_id = Column(Integer, ForeignKey("employee_responsibilities.id", ondelete="CASCADE"), primary_key=True)


# Skills Assessment Model
class UserSkillAssessment(Base):
    __tablename__ = "user_skill_assessments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)
    required_proficiency = Column(Integer, nullable=False)  # 1-5
    current_proficiency = Column(Integer, default=0)  # 1-5, 0 = not assessed
    assessment_notes = Column(Text, nullable=True)
    training_recommendations = Column(JSON, nullable=True)
    assessed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assessed_at = Column(DateTime, nullable=True)
    next_assessment_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Unique constraint: one assessment per user per skill
    __table_args__ = (
        UniqueConstraint('user_id', 'skill_id', name='unique_user_skill'),
    )


__all__ = [
    "UserJobDescription",
    "Skill",
    "EmployeeResponsibility",
    "ResponsibilitySkill",
    "UserGoal",
    "GoalKeyResult",
    "GoalEmployeeAssessment",
    "GoalManagerAssessment",
    "GoalResponsibility",
    "UserSkillAssessment",
]
