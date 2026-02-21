"""
Perennia AI - Agent Tools Base Infrastructure
Core utilities, decorators, and registry for all agent tools.

Database Connection:
    This module uses the shared database connection from backend.database,
    ensuring consistency between the main application and agent tools.
    Works with both SQLite (local development) and PostgreSQL (production).
"""

import os
import functools
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Callable, TypeVar, Union
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker, Session
from langchain_core.tools import Tool

# Import shared database connection from main application
# This ensures agents use the same database as the main app
# Note: Uses 'database' not 'backend.database' as Railway deploys from backend/ directory
from database import engine as shared_engine, SessionLocal as SharedSessionLocal

logger = logging.getLogger(__name__)


# =============================================================================
# Database Configuration - Using Shared Connection
# =============================================================================

class DatabaseConfig:
    """
    Database configuration management.

    Uses the shared database engine from backend.database to ensure
    consistency across the application. This allows agent tools to
    work with both SQLite (local) and PostgreSQL (production) without
    any configuration changes.
    """

    _session_factory = None

    @classmethod
    def get_engine(cls):
        """Get the shared database engine from backend.database."""
        return shared_engine

    @classmethod
    def get_session_factory(cls):
        """Get or create session factory using shared engine."""
        if cls._session_factory is None:
            cls._session_factory = sessionmaker(
                bind=cls.get_engine(),
                expire_on_commit=False
            )
        return cls._session_factory


def get_engine():
    """Get database engine (shared with main application)."""
    return DatabaseConfig.get_engine()


def get_session_factory():
    """Get session factory."""
    return DatabaseConfig.get_session_factory()


@contextmanager
def get_db():
    """Context manager for database sessions."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Alias for modules that import db_session
db_session = get_db


def execute_query(query: str, params: Optional[Dict] = None) -> List[Dict]:
    """
    Execute a query and return results as list of dicts.

    Uses the shared database connection from backend.database,
    which supports both SQLite and PostgreSQL.
    """
    try:
        with get_db() as db:
            result = db.execute(text(query), params or {})
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        logger.debug(f"Query: {query[:200]}...")
        raise


def execute_single(query: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Execute a query and return single result as dict."""
    results = execute_query(query, params)
    return results[0] if results else None


# =============================================================================
# Database-Agnostic SQL Helpers
# =============================================================================

def is_sqlite() -> bool:
    """Check if the current database is SQLite."""
    db_url = os.getenv("DATABASE_URL", "sqlite:///")
    return db_url.startswith("sqlite")


def sql_days_since(column: str) -> str:
    """
    Return SQL expression for days since a timestamp column.

    Args:
        column: The timestamp column name (e.g., 'l.stage_changed_at')

    Returns:
        SQL expression that calculates days since the column value

    Examples:
        PostgreSQL: EXTRACT(EPOCH FROM (NOW() - l.stage_changed_at)) / 86400
        SQLite: julianday('now') - julianday(l.stage_changed_at)
    """
    if is_sqlite():
        return f"(julianday('now') - julianday({column}))"
    else:
        return f"EXTRACT(EPOCH FROM (NOW() - {column})) / 86400"


def sql_now() -> str:
    """
    Return SQL expression for current timestamp.

    Returns:
        'NOW()' for PostgreSQL, "datetime('now')" for SQLite
    """
    if is_sqlite():
        return "datetime('now')"
    else:
        return "NOW()"


def sql_interval(days: int) -> str:
    """
    Return SQL expression for a time interval.

    Args:
        days: Number of days for the interval

    Returns:
        SQL expression for the interval

    Examples:
        PostgreSQL: INTERVAL '30 days'
        SQLite: '-30 days'
    """
    if is_sqlite():
        return f"'{-days} days'"
    else:
        return f"INTERVAL '{days} days'"


def sql_date_subtract(days: int) -> str:
    """
    Return SQL expression for current date minus N days.

    Args:
        days: Number of days to subtract

    Returns:
        SQL expression for date calculation

    Examples:
        PostgreSQL: NOW() - INTERVAL '30 days'
        SQLite: datetime('now', '-30 days')
    """
    if is_sqlite():
        return f"datetime('now', '-{days} days')"
    else:
        return f"NOW() - INTERVAL '{days} days'"


# =============================================================================
# Enums and Constants
# =============================================================================

class ToolStatus(str, Enum):
    """Status of a tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    NO_DATA = "no_data"
    PARTIAL = "partial"


class LoanStatus(str, Enum):
    """
    Loan pipeline status values.

    IMPORTANT: These values MUST match the LoanStage enum in main.py exactly.
    The database stores these as PostgreSQL enums with these exact values.
    """
    APPLICATION = "Application"
    DISCLOSED = "Disclosed"
    PROCESSING = "Processing"
    SUBMITTED = "Submitted"
    UNDERWRITING = "Underwriting"
    UW_RECEIVED = "UW Received"
    CONDITIONAL_APPROVAL = "Conditional Approval"
    APPROVED = "Approved"
    SUSPENDED = "Suspended"
    CTC = "CTC"
    CLEAR_TO_CLOSE = "Clear to Close"
    CLOSING = "Closing"
    DOCS_OUT = "Docs Out"
    FUNDED = "Funded"


class LoanType(str, Enum):
    """Loan product types."""
    CONVENTIONAL = "conventional"
    FHA = "fha"
    VA = "va"
    USDA = "usda"
    JUMBO = "jumbo"
    NON_QM = "non_qm"
    HELOC = "heloc"
    REVERSE = "reverse"


class PropertyType(str, Enum):
    """Property types."""
    SINGLE_FAMILY = "single_family"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    MULTI_FAMILY = "multi_family"
    MANUFACTURED = "manufactured"
    CO_OP = "co_op"


class OccupancyType(str, Enum):
    """Occupancy types."""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    INVESTMENT = "investment"


# SLA targets in days for each stage
# Keys match LoanStatus enum values (case-insensitive lookup supported)
SLA_TARGETS = {
    "Application": 1,
    "Disclosed": 3,
    "Processing": 5,
    "Submitted": 2,
    "Underwriting": 3,
    "UW Received": 3,
    "Conditional Approval": 5,
    "Approved": 2,
    "Suspended": 7,
    "CTC": 2,
    "Clear to Close": 2,
    "Closing": 3,
    "Docs Out": 3,
    "Funded": 0,
}

# Document categories
DOCUMENT_CATEGORIES = {
    "income": ["W2s", "Paystubs", "Tax Returns", "1099s", "P&L Statement", "Business Returns"],
    "asset": ["Bank Statements", "Investment Statements", "Retirement Accounts", "Gift Letter"],
    "identity": ["Government ID", "SSN Card", "DD-214", "Green Card"],
    "property": ["Purchase Contract", "Appraisal", "Title Report", "Insurance", "Survey"],
    "compliance": ["Initial Disclosures", "CD", "LE", "URLA", "4506-C", "VOE", "VOR"],
    "credit": ["Credit Report", "Credit Supplement", "LOX", "Fraud Report"],
}


# =============================================================================
# Tool Result Types
# =============================================================================

@dataclass
class ToolResult:
    """Standardized result from tool execution."""
    status: ToolStatus
    data: Optional[Any] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "data": self.data,
            "message": self.message,
            "metadata": self.metadata,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    @classmethod
    def success(cls, data: Any, message: Optional[str] = None, **metadata) -> "ToolResult":
        """Create a successful result."""
        return cls(
            status=ToolStatus.SUCCESS,
            data=data,
            message=message,
            metadata=metadata,
        )

    @classmethod
    def error(cls, message: str, errors: Optional[List[str]] = None) -> "ToolResult":
        """Create an error result."""
        return cls(
            status=ToolStatus.ERROR,
            message=message,
            errors=errors or [message],
        )

    @classmethod
    def no_data(cls, message: str = "No data found") -> "ToolResult":
        """Create a no-data result."""
        return cls(
            status=ToolStatus.NO_DATA,
            message=message,
        )

    @classmethod
    def partial(cls, data: Any, message: str, warnings: List[str]) -> "ToolResult":
        """Create a partial success result."""
        return cls(
            status=ToolStatus.PARTIAL,
            data=data,
            message=message,
            warnings=warnings,
        )


class ToolError(Exception):
    """Exception raised by tools."""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# =============================================================================
# Tool Registry
# =============================================================================

@dataclass
class ToolDefinition:
    """Definition of a registered tool."""
    name: str
    description: str
    func: Callable
    agent_roles: List[str]
    risk_level: str = "low"
    requires_confirmation: bool = False
    examples: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Central registry for all agent tools."""

    _instance = None
    _tools: Dict[str, ToolDefinition] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    @classmethod
    def register(cls, tool_def: ToolDefinition):
        """Register a tool definition."""
        instance = cls()
        instance._tools[tool_def.name] = tool_def

    @classmethod
    def get(cls, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        instance = cls()
        return instance._tools.get(name)

    @classmethod
    def get_metadata(cls, name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a tool by name.

        Args:
            name: The tool name

        Returns:
            Dict with tool metadata or None if tool not found
        """
        tool_def = cls.get(name)
        if tool_def is None:
            return None

        return {
            "name": tool_def.name,
            "description": tool_def.description,
            "agent_roles": tool_def.agent_roles,
            "risk_level": tool_def.risk_level.upper(),  # Normalize to uppercase
            "requires_confirmation": tool_def.requires_confirmation,
            "examples": tool_def.examples,
            "parameters": tool_def.parameters,
        }

    @classmethod
    def get_all(cls) -> Dict[str, ToolDefinition]:
        """Get all registered tools."""
        instance = cls()
        return instance._tools.copy()

    @classmethod
    def get_for_agent(cls, agent_role: str) -> List[ToolDefinition]:
        """Get all tools available for a specific agent role."""
        instance = cls()
        return [
            tool for tool in instance._tools.values()
            if agent_role in tool.agent_roles or "all" in tool.agent_roles
        ]

    @classmethod
    def get_langchain_tools(cls, agent_role: Optional[str] = None) -> List[Tool]:
        """Get tools as LangChain Tool objects."""
        instance = cls()

        if agent_role:
            tool_defs = cls.get_for_agent(agent_role)
        else:
            tool_defs = list(instance._tools.values())

        langchain_tools = []
        for tool_def in tool_defs:
            langchain_tools.append(
                Tool(
                    name=tool_def.name,
                    description=tool_def.description,
                    func=tool_def.func,
                )
            )
        return langchain_tools

    @classmethod
    def clear(cls):
        """Clear all registered tools (for testing)."""
        instance = cls()
        instance._tools.clear()

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)

    def __iter__(self):
        """Iterate over tool names."""
        return iter(self._tools)


# =============================================================================
# Tool Decorator
# =============================================================================

F = TypeVar('F', bound=Callable)


def mortgage_tool(
    name: str,
    description: str,
    agent_roles: List[str],
    risk_level: str = "low",
    requires_confirmation: bool = False,
    examples: Optional[List[str]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Callable[[F], F]:
    """
    Decorator to register a function as a mortgage tool.

    Args:
        name: Unique tool name
        description: Human-readable description
        agent_roles: List of agent roles that can use this tool
        risk_level: Risk level (low, medium, high)
        requires_confirmation: Whether tool requires user confirmation
        examples: Example usage strings
        parameters: Parameter schema for the tool
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                # Ensure result is a ToolResult
                if not isinstance(result, ToolResult):
                    result = ToolResult.success(result)
                return result
            except ToolError as e:
                return ToolResult.error(e.message, [e.message])
            except Exception as e:
                return ToolResult.error(f"Tool error: {str(e)}", [str(e)])

        # Register the tool
        tool_def = ToolDefinition(
            name=name,
            description=description,
            func=wrapper,
            agent_roles=agent_roles,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            examples=examples or [],
            parameters=parameters or {},
        )
        ToolRegistry.register(tool_def)

        # Store metadata on function
        wrapper._tool_definition = tool_def

        return wrapper
    return decorator


# =============================================================================
# Helper Functions
# =============================================================================

def format_currency(amount: Union[float, Decimal, int, None]) -> str:
    """Format a number as currency."""
    if amount is None:
        return "$0.00"
    return f"${float(amount):,.2f}"


def format_percentage(value: Union[float, Decimal, None], decimals: int = 2) -> str:
    """Format a number as percentage."""
    if value is None:
        return "0.00%"
    return f"{float(value):.{decimals}f}%"


def format_date(dt: Union[datetime, date, None], fmt: str = "%Y-%m-%d") -> str:
    """Format a date/datetime."""
    if dt is None:
        return ""
    return dt.strftime(fmt)


def days_between(start: Union[datetime, date, None], end: Union[datetime, date, None] = None) -> int:
    """Calculate days between two dates."""
    if start is None:
        return 0
    if end is None:
        end = datetime.now().date() if isinstance(start, date) else datetime.now()

    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()

    return (end - start).days


def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """Calculate percentage change between two values."""
    if old_value == 0:
        return 0.0 if new_value == 0 else 100.0
    return ((new_value - old_value) / old_value) * 100


def add_business_days(start_date: date, days: int) -> date:
    """Add business days to a date."""
    current = start_date
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday = 0, Friday = 4
            added += 1
    return current


def subtract_business_days(start_date: date, days: int) -> date:
    """Subtract business days from a date."""
    current = start_date
    subtracted = 0
    while subtracted < days:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            subtracted += 1
    return current


def get_loan_stage_order() -> List[str]:
    """
    Get the standard loan stage progression order.

    These values match the LoanStage enum in main.py exactly.
    """
    return [
        "Disclosed",
        "Processing",
        "Submitted",
        "UW Received",
        "Approved",
        "Suspended",
        "CTC",
        "Docs Out",
        "Funded",
    ]


def is_loan_active(status: str) -> bool:
    """
    Check if a loan status indicates an active loan.

    Uses case-insensitive comparison for flexibility.
    'Funded' is the only terminal successful state in LoanStage enum.
    """
    inactive_statuses = {"funded"}
    return status.lower() not in inactive_statuses


def get_sla_for_stage(stage: str) -> int:
    """
    Get SLA target days for a loan stage.

    Maps both old-style (lowercase) and new-style (title case) stage names.
    """
    # Normalize stage name for lookup
    stage_lower = stage.lower().replace(" ", "_").replace("-", "_")

    # Map to SLA targets (keys are normalized versions of LoanStatus enum values)
    stage_sla_map = {
        "application": 1,
        "disclosed": 3,
        "processing": 5,
        "submitted": 2,
        "underwriting": 3,
        "uw_received": 3,
        "conditional_approval": 5,
        "approved": 2,
        "suspended": 7,
        "ctc": 2,
        "clear_to_close": 2,
        "closing": 3,
        "docs_out": 3,
        "funded": 0,
    }
    return stage_sla_map.get(stage_lower, 5)  # Default 5 days


# =============================================================================
# Singleton Registry Instance and Convenience Functions
# =============================================================================

# Global singleton instance
tool_registry = ToolRegistry()


def get_tools_for_agent(agent_role: str) -> List[ToolDefinition]:
    """Get all tools available for a specific agent role."""
    return tool_registry.get_for_agent(agent_role)


def execute_tool(tool_name: str, **kwargs) -> ToolResult:
    """
    Execute a tool by name with given parameters.

    Args:
        tool_name: Name of the tool to execute
        **kwargs: Parameters to pass to the tool

    Returns:
        ToolResult from tool execution
    """
    tool_def = tool_registry.get(tool_name)
    if not tool_def:
        return ToolResult.error(f"Tool '{tool_name}' not found")

    try:
        return tool_def.func(**kwargs)
    except Exception as e:
        return ToolResult.error(f"Error executing {tool_name}: {str(e)}")
