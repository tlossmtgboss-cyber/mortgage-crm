"""
IT Helpdesk Models

ITHelpdeskTicket and ITHelpdeskTool models for AI-powered IT support.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.it_helpdesk import ITHelpdeskTicket, ITHelpdeskTool
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, ForeignKey, JSON
)

from db import Base


class ITHelpdeskTicket(Base):
    __tablename__ = "it_helpdesk_tickets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    description = Column(Text)
    category = Column(String)  # dev_env, build_deploy, git, vscode, os, network, saas_config
    urgency = Column(String, default="normal")  # low, normal, high, critical
    status = Column(String, default="analyzing")  # analyzing, awaiting_approval, fixing, resolved, failed

    # AI Analysis
    ai_diagnosis = Column(Text)  # AI's understanding of the problem
    root_cause = Column(String)  # Short summary of root cause
    proposed_fix = Column(JSON)  # {steps: [], commands: [], risk_level: "low|medium|high"}

    # Execution
    approved_at = Column(DateTime)  # When user approved the fix
    executed_at = Column(DateTime)  # When fix was executed
    execution_log = Column(JSON)  # {commands_run: [], outputs: [], errors: []}
    resolution_notes = Column(Text)  # Final outcome

    # Metadata
    affected_system = Column(String)  # vercel, railway, local, github, vscode, etc.
    affected_project = Column(String)  # Project/repo name if applicable
    logs_attached = Column(JSON)  # Screenshots, error logs, stack traces
    auto_resolved = Column(Boolean, default=False)  # Was it auto-fixed or manual?

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime)


class ITHelpdeskTool(Base):
    __tablename__ = "it_helpdesk_tools"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)  # e.g., "fix_vercel_output_dir"
    description = Column(Text)  # What this tool does
    category = Column(String)  # build_deploy, git, vscode, etc.
    risk_level = Column(String)  # low, medium, high
    requires_approval = Column(Boolean, default=True)  # Does it need user approval?

    # Tool definition
    parameters_schema = Column(JSON)  # OpenAI function calling schema
    implementation = Column(Text)  # Code/script to run (or API endpoint)

    # Stats
    times_used = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


__all__ = [
    "ITHelpdeskTicket",
    "ITHelpdeskTool",
]
