- """
================================================================================
PERENNIA AI - PART 1 OF 5
================================================================================
Base Infrastructure + Core CRM Agents (Pipeline, Compliance, Leads, Documents)
32 Tools

INSTALLATION:
1. Save all 5 parts to: backend/agents/tools/
2. Rename: part1_base.py, part2_crm.py, part3_comm.py, part4_ops.py, part5_business.py
3. Set DATABASE_URL environment variable
4. pip install sqlalchemy pydantic

================================================================================
"""

from __future__ import annotations
import os
import functools
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Callable, TypeVar, Union
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    NO_DATA = "no_data"
    PENDING_APPROVAL = "pending_approval"


class LoanStage(str, Enum):
    """Real loan stages (stored UPPERCASE in DB as plain String column)."""
    APPLICATION = "APPLICATION"
    DISCLOSED = "DISCLOSED"
    PROCESSING = "PROCESSING"
    SUBMITTED = "SUBMITTED"
    UNDERWRITING = "UNDERWRITING"
    UW_RECEIVED = "UW_RECEIVED"
    CONDITIONAL_APPROVAL = "CONDITIONAL_APPROVAL"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    CTC = "CTC"
    CLEAR_TO_CLOSE = "CLEAR_TO_CLOSE"
    CLOSING = "CLOSING"
    DOCS = "DOCS"
    DOCS_OUT = "DOCS_OUT"
    FUNDED = "FUNDED"
    CANCELLED = "CANCELLED"
    DENIED = "DENIED"
    DEAD = "DEAD"
    NURTURE = "NURTURE"
    WITHDRAWN = "WITHDRAWN"
    DOES_NOT_QUALIFY = "DOES_NOT_QUALIFY"


class LoanType(str, Enum):
    CONVENTIONAL = "conventional"
    FHA = "fha"
    VA = "va"
    USDA = "usda"
    JUMBO = "jumbo"
    NON_QM = "non_qm"


class PropertyType(str, Enum):
    SINGLE_FAMILY = "single_family"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    MULTI_FAMILY = "multi_family"
    MANUFACTURED = "manufactured"


class OccupancyType(str, Enum):
    PRIMARY = "primary"
    SECOND_HOME = "second_home"
    INVESTMENT = "investment"


# =============================================================================
# CONSTANTS
# =============================================================================

# SLA targets in days for stage-to-stage transitions (based on real SLA date fields on Loan model)
SLA_TARGETS = {
    "APPLICATION_to_DISCLOSED": 3,
    "DISCLOSED_to_SUBMITTED": 7,
    "SUBMITTED_to_UW_RECEIVED": 2,
    "UW_RECEIVED_to_APPROVED": 5,
    "APPROVED_to_CLEAR_TO_CLOSE": 3,
    "CLEAR_TO_CLOSE_to_DOCS_OUT": 3,
    "DOCS_OUT_to_FUNDED": 5,
}

# Closed/terminal stages that are excluded from active pipeline queries
TERMINAL_STAGES = ("FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY")

DOCUMENT_CATEGORIES = {
    "income": ["paystubs", "w2", "tax_returns", "1099", "profit_loss"],
    "assets": ["bank_statements", "investment_statements", "gift_letter"],
    "property": ["purchase_contract", "appraisal", "title", "insurance", "hoa"],
    "identity": ["drivers_license", "ssn_card", "passport"],
    "credit": ["credit_report", "credit_explanation", "bankruptcy_docs"],
}


# =============================================================================
# TOOL RESULT
# =============================================================================

@dataclass
class ToolResult:
    """Standardized result from any tool execution."""
    status: ToolStatus
    data: Optional[Dict[str, Any]] = None
    message: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False

    @classmethod
    def success(cls, data: Dict[str, Any], message: str = "", requires_approval: bool = False) -> "ToolResult":
        return cls(status=ToolStatus.SUCCESS, data=data, message=message, requires_approval=requires_approval)

    @classmethod
    def error(cls, error: str, message: str = "") -> "ToolResult":
        return cls(status=ToolStatus.ERROR, error=error, message=message or error)

    @classmethod
    def no_data(cls, message: str = "No data found") -> "ToolResult":
        return cls(status=ToolStatus.NO_DATA, message=message, data={})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "data": self.data,
            "message": self.message,
            "error": self.error,
            "metadata": self.metadata,
            "requires_approval": self.requires_approval,
        }


class ToolError(Exception):
    """Custom exception for tool errors."""
    def __init__(self, message: str, code: str = "TOOL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create SQLAlchemy engine."""
    global _engine
    if _engine is None:
        database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
        _engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )
    return _engine


def get_session() -> Session:
    """Get database session."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


@contextmanager
def db_session():
    """Context manager for database sessions."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def execute_query(query: str, params: Dict = None) -> List[Dict]:
    """Execute a query and return results as list of dicts."""
    with db_session() as session:
        result = session.execute(text(query), params or {})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]


def execute_single(query: str, params: Dict = None) -> Optional[Dict]:
    """Execute a query and return single result."""
    results = execute_query(query, params)
    return results[0] if results else None


# =============================================================================
# TOOL REGISTRY
# =============================================================================

class ToolRegistry:
    """Registry for all mortgage tools."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._metadata = {}
        return cls._instance

    def register(self, name: str, func: Callable, metadata: Dict):
        """Register a tool."""
        self._tools[name] = func
        self._metadata[name] = metadata

    def get(self, name: str) -> Optional[Callable]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_metadata(self, name: str) -> Optional[Dict]:
        """Get tool metadata."""
        return self._metadata.get(name)

    def get_tools(self, agent_role: str = None) -> Dict[str, Callable]:
        """Get tools, optionally filtered by agent role."""
        if agent_role is None:
            return self._tools.copy()
        return {
            name: func for name, func in self._tools.items()
            if agent_role in self._metadata.get(name, {}).get("agent_roles", [])
        }

    def get_langchain_tools(self, agent_role: str = None) -> List:
        """Get tools formatted for LangChain."""
        from langchain.tools import StructuredTool
        tools = []
        for name, func in self.get_tools(agent_role).items():
            meta = self._metadata.get(name, {})
            tools.append(StructuredTool.from_function(
                func=func,
                name=name,
                description=meta.get("description", ""),
            ))
        return tools

    def __len__(self):
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.items())


tool_registry = ToolRegistry()


# =============================================================================
# DECORATORS
# =============================================================================

F = TypeVar('F', bound=Callable)


def mortgage_tool(
    name: str,
    description: str,
    agent_roles: List[str],
    risk_level: str = "LOW",
    requires_approval: bool = None,
) -> Callable[[F], F]:
    """Decorator to register a function as a mortgage tool."""
    if requires_approval is None:
        requires_approval = risk_level == "HIGH"

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> ToolResult:
            try:
                result = func(*args, **kwargs)
                if isinstance(result, ToolResult):
                    if requires_approval and not result.requires_approval:
                        result.requires_approval = True
                    return result
                return ToolResult.success(data=result if isinstance(result, dict) else {"result": result})
            except ToolError as e:
                return ToolResult.error(error=e.message, message=e.message)
            except Exception as e:
                logger.exception(f"Tool {name} failed")
                return ToolResult.error(error=str(e), message=f"Tool execution failed: {str(e)}")

        tool_registry.register(name, wrapper, {
            "name": name,
            "description": description,
            "agent_roles": agent_roles,
            "risk_level": risk_level,
            "requires_approval": requires_approval,
            "function": func.__name__,
        })

        return wrapper
    return decorator


# =============================================================================
# UTILITIES
# =============================================================================

def format_currency(amount: Union[Decimal, float, int, None]) -> str:
    """Format amount as currency."""
    if amount is None:
        return "$0.00"
    return f"${float(amount):,.2f}"


def format_percentage(value: Union[Decimal, float, None], decimals: int = 2) -> str:
    """Format value as percentage."""
    if value is None:
        return "0%"
    return f"{float(value):.{decimals}f}%"


def format_date(dt: Union[datetime, date, None], fmt: str = "%m/%d/%Y") -> str:
    """Format date."""
    if dt is None:
        return ""
    return dt.strftime(fmt)


def days_between(start: Union[datetime, date, None], end: Union[datetime, date, None]) -> int:
    """Calculate days between two dates."""
    if start is None or end is None:
        return 0
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()
    return (end - start).days


# =============================================================================
# PIPELINE ANALYST TOOLS (8 tools)
# =============================================================================

@mortgage_tool(
    name="get_pipeline_metrics",
    description="Get pipeline metrics including count, volume, and velocity for a loan officer or organization",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def get_pipeline_metrics(
    lo_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    days: int = 30,
) -> ToolResult:
    """Get pipeline metrics."""
    params = {"days": days}
    filters = ["l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')"]

    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if organization_id:
        filters.append("l.organization_id = :organization_id")
        params["organization_id"] = organization_id

    where_sql = " AND ".join(filters)

    result = execute_single(f"""
        SELECT
            COUNT(*) as total_count,
            COALESCE(SUM(l.amount), 0) as total_volume,
            COUNT(CASE WHEN l.stage IN ('CTC', 'CLEAR_TO_CLOSE', 'DOCS', 'DOCS_OUT', 'CLOSING') THEN 1 END) as closing_soon,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400) as avg_days_in_stage
        FROM loans l
        WHERE {where_sql}
    """, params)

    # Get velocity (funded in period)
    velocity = execute_single(f"""
        SELECT COUNT(*) as funded_count, COALESCE(SUM(amount), 0) as funded_volume
        FROM loans l
        WHERE l.funded_date >= CURRENT_DATE - :days
        {"AND l.loan_officer_id = :lo_id" if lo_id else ""}
        {"AND l.organization_id = :organization_id" if organization_id else ""}
    """, params)

    data = {
        "total_count": result["total_count"] or 0,
        "total_volume": float(result["total_volume"] or 0),
        "total_volume_formatted": format_currency(result["total_volume"]),
        "closing_soon": result["closing_soon"] or 0,
        "avg_days_in_stage": round(float(result["avg_days_in_stage"] or 0), 1),
        "velocity": {
            "period_days": days,
            "funded_count": velocity["funded_count"] or 0,
            "funded_volume": float(velocity["funded_volume"] or 0),
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Pipeline: {data['total_count']} loans, {data['total_volume_formatted']}",
    )


@mortgage_tool(
    name="get_loans_by_stage",
    description="Get loans filtered by stage with details",
    agent_roles=["pipeline_analyst"],
    risk_level="LOW",
)
def get_loans_by_stage(
    stage: str,
    lo_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    limit: int = 50,
) -> ToolResult:
    """Get loans by stage."""
    params = {"stage": stage, "limit": limit}
    filters = ["l.stage = :stage"]

    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if organization_id:
        filters.append("l.organization_id = :organization_id")
        params["organization_id"] = organization_id

    where_sql = " AND ".join(filters)

    loans = execute_query(f"""
        SELECT
            l.id, l.loan_number, l.amount, l.stage,
            l.borrower_name, l.property_address, l.loan_type,
            l.stage_changed_at, l.closing_date, l.lock_expiration_date,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE {where_sql}
        ORDER BY l.stage_changed_at DESC
        LIMIT :limit
    """, params)

    if not loans:
        return ToolResult.no_data(f"No loans found with stage '{stage}'")

    data = {
        "stage": stage,
        "count": len(loans),
        "loans": [
            {
                "id": loan["id"],
                "loan_number": loan["loan_number"],
                "borrower": loan["borrower_name"],
                "amount": float(loan["amount"] or 0),
                "amount_formatted": format_currency(loan["amount"]),
                "loan_type": loan["loan_type"],
                "property": loan["property_address"],
                "lo_name": loan["lo_name"],
                "days_in_stage": days_between(loan["stage_changed_at"], datetime.now()),
                "closing_date": format_date(loan["closing_date"]),
                "lock_expires": format_date(loan["lock_expiration_date"]),
            }
            for loan in loans
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"{len(loans)} loans in {stage}",
    )


@mortgage_tool(
    name="get_loan_aging_report",
    description="Get aging report showing how long loans have been in each stage",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def get_loan_aging_report(
    lo_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    threshold_days: int = 7,
) -> ToolResult:
    """Get loan aging report."""
    params = {"threshold": threshold_days}
    filters = ["l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')"]

    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if organization_id:
        filters.append("l.organization_id = :organization_id")
        params["organization_id"] = organization_id

    where_sql = " AND ".join(filters)

    aging = execute_query(f"""
        SELECT
            l.stage,
            COUNT(*) as count,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400) as avg_days,
            MAX(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400) as max_days,
            COUNT(CASE WHEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 > :threshold THEN 1 END) as over_threshold
        FROM loans l
        WHERE {where_sql}
        GROUP BY l.stage
        ORDER BY avg_days DESC
    """, params)

    if not aging:
        return ToolResult.no_data("No active loans found")

    total_over_threshold = sum(row["over_threshold"] or 0 for row in aging)

    data = {
        "threshold_days": threshold_days,
        "total_over_threshold": total_over_threshold,
        "by_stage": [
            {
                "stage": row["stage"],
                "count": row["count"],
                "avg_days": round(float(row["avg_days"] or 0), 1),
                "max_days": round(float(row["max_days"] or 0), 1),
                "over_threshold": row["over_threshold"] or 0,
            }
            for row in aging
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"{total_over_threshold} loans over {threshold_days} day threshold",
    )


@mortgage_tool(
    name="calculate_conversion_rates",
    description="Calculate stage-to-stage conversion rates",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def calculate_conversion_rates(
    lo_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    days: int = 90,
) -> ToolResult:
    """Calculate conversion rates between pipeline stages."""
    params = {"days": days}
    filters = ["l.created_at >= CURRENT_DATE - :days"]

    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if organization_id:
        filters.append("l.organization_id = :organization_id")
        params["organization_id"] = organization_id

    where_sql = " AND ".join(filters)

    funnel = execute_single(f"""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN application_date IS NOT NULL THEN 1 END) as applications,
            COUNT(CASE WHEN uw_received_date IS NOT NULL THEN 1 END) as submitted,
            COUNT(CASE WHEN loan_approved_date IS NOT NULL THEN 1 END) as approved,
            COUNT(CASE WHEN clear_to_close_date IS NOT NULL THEN 1 END) as ctc,
            COUNT(CASE WHEN funded_date IS NOT NULL THEN 1 END) as funded,
            COUNT(CASE WHEN stage IN ('CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY') THEN 1 END) as fallout
        FROM loans l
        WHERE {where_sql}
    """, params)

    def calc_rate(num, denom):
        return round((num / denom) * 100, 1) if denom > 0 else 0

    data = {
        "period_days": days,
        "funnel": {
            "total_leads": funnel["total"],
            "applications": funnel["applications"],
            "submitted": funnel["submitted"],
            "approved": funnel["approved"],
            "clear_to_close": funnel["ctc"],
            "funded": funnel["funded"],
            "fallout": funnel["fallout"],
        },
        "conversion_rates": {
            "lead_to_app": calc_rate(funnel["applications"], funnel["total"]),
            "app_to_submit": calc_rate(funnel["submitted"], funnel["applications"]),
            "submit_to_approve": calc_rate(funnel["approved"], funnel["submitted"]),
            "approve_to_ctc": calc_rate(funnel["ctc"], funnel["approved"]),
            "ctc_to_fund": calc_rate(funnel["funded"], funnel["ctc"]),
            "overall_pull_through": calc_rate(funnel["funded"], funnel["applications"]),
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Pull-through: {data['conversion_rates']['overall_pull_through']}%",
    )


@mortgage_tool(
    name="predict_closing_timeline",
    description="Predict closing timeline based on current stage and historical data",
    agent_roles=["pipeline_analyst"],
    risk_level="LOW",
)
def predict_closing_timeline(
    loan_id: str,
) -> ToolResult:
    """Predict closing timeline for a loan."""
    loan = execute_single("""
        SELECT
            l.id, l.loan_number, l.stage, l.loan_type,
            l.application_date, l.uw_received_date, l.loan_approved_date,
            l.clear_to_close_date, l.closing_date
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Get historical averages for this loan type
    historical = execute_single("""
        SELECT
            AVG(EXTRACT(EPOCH FROM (uw_received_date - application_date)) / 86400) as avg_app_to_submit,
            AVG(EXTRACT(EPOCH FROM (loan_approved_date - uw_received_date)) / 86400) as avg_submit_to_approve,
            AVG(EXTRACT(EPOCH FROM (clear_to_close_date - loan_approved_date)) / 86400) as avg_approve_to_ctc,
            AVG(EXTRACT(EPOCH FROM (funded_date - clear_to_close_date)) / 86400) as avg_ctc_to_fund
        FROM loans
        WHERE loan_type = :loan_type AND funded_date >= CURRENT_DATE - 180
    """, {"loan_type": loan["loan_type"]})

    # Calculate predicted close based on current stage
    now = datetime.now()
    remaining_days = 0
    stages_remaining = []

    stage_order = ["APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED", "CLEAR_TO_CLOSE"]
    current_idx = stage_order.index(loan["stage"]) if loan["stage"] in stage_order else 0

    if current_idx < 5:  # Before UW_RECEIVED (submission)
        remaining_days += float(historical["avg_app_to_submit"] or 5)
        stages_remaining.append(("submission", float(historical["avg_app_to_submit"] or 5)))
    if current_idx < 7:  # Before APPROVED
        remaining_days += float(historical["avg_submit_to_approve"] or 7)
        stages_remaining.append(("approval", float(historical["avg_submit_to_approve"] or 7)))
    if current_idx < 8:  # Before CLEAR_TO_CLOSE
        remaining_days += float(historical["avg_approve_to_ctc"] or 3)
        stages_remaining.append(("clear_to_close", float(historical["avg_approve_to_ctc"] or 3)))

    remaining_days += float(historical["avg_ctc_to_fund"] or 5)
    stages_remaining.append(("funding", float(historical["avg_ctc_to_fund"] or 5)))

    predicted_close = now + timedelta(days=remaining_days)

    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "current_stage": loan["stage"],
        "closing_date": format_date(loan["closing_date"]),
        "predicted_close_date": format_date(predicted_close),
        "remaining_days": round(remaining_days, 0),
        "stages_remaining": [{"stage": s[0], "days": round(s[1], 1)} for s in stages_remaining],
        "confidence": "high" if len(stages_remaining) <= 2 else "medium",
    }

    return ToolResult.success(
        data=data,
        message=f"Predicted close: {format_date(predicted_close)} ({round(remaining_days)} days)",
    )


@mortgage_tool(
    name="get_bottleneck_analysis",
    description="Identify bottlenecks in the pipeline",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def get_bottleneck_analysis(
    lo_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> ToolResult:
    """Identify pipeline bottlenecks."""
    params = {}
    filters = ["l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')"]

    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if organization_id:
        filters.append("l.organization_id = :organization_id")
        params["organization_id"] = organization_id

    where_sql = " AND ".join(filters)

    bottlenecks = execute_query(f"""
        SELECT
            l.stage,
            COUNT(*) as count,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400) as avg_days
        FROM loans l
        WHERE {where_sql}
        GROUP BY l.stage
        HAVING AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400) > 5
        ORDER BY avg_days DESC
    """, params)

    sla_comparison = []
    for row in bottlenecks:
        stage = row["stage"]
        avg_days = float(row["avg_days"] or 0)
        # Look up SLA target for this stage's transition
        target = 5  # default
        for key, val in SLA_TARGETS.items():
            if key.startswith(stage + "_to_"):
                target = val
                break
        sla_comparison.append({
            "stage": stage,
            "count": row["count"],
            "avg_days": round(avg_days, 1),
            "target_days": target,
            "over_sla": avg_days > target,
            "severity": "critical" if avg_days > target * 2 else "warning" if avg_days > target else "normal",
        })

    data = {
        "bottlenecks": sla_comparison,
        "critical_count": len([b for b in sla_comparison if b["severity"] == "critical"]),
        "recommendations": [],
    }

    for b in sla_comparison:
        if b["severity"] == "critical":
            data["recommendations"].append(f"Review {b['count']} loans stuck in {b['stage']} (avg {b['avg_days']} days)")

    return ToolResult.success(
        data=data,
        message=f"{data['critical_count']} critical bottlenecks identified",
    )


@mortgage_tool(
    name="compare_to_benchmark",
    description="Compare pipeline metrics to company benchmarks (averages across all LOs)",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def compare_to_benchmark(
    lo_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> ToolResult:
    """Compare to company benchmarks."""
    params = {}
    filters = ["l.funded_date >= CURRENT_DATE - 90"]

    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if organization_id:
        filters.append("l.organization_id = :organization_id")
        params["organization_id"] = organization_id

    where_sql = " AND ".join(filters)

    # Get current metrics
    current = execute_single(f"""
        SELECT
            COUNT(*) as funded_units,
            COALESCE(SUM(amount), 0) as funded_volume,
            AVG(EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400) as avg_cycle_time
        FROM loans l
        WHERE {where_sql}
    """, params)

    # Get company benchmark (average across all LOs)
    benchmark = execute_single("""
        SELECT
            AVG(units) as avg_units,
            AVG(volume) as avg_volume,
            AVG(cycle_time) as avg_cycle_time
        FROM (
            SELECT
                loan_officer_id,
                COUNT(*) as units,
                SUM(amount) as volume,
                AVG(EXTRACT(EPOCH FROM (funded_date - application_date)) / 86400) as cycle_time
            FROM loans
            WHERE funded_date >= CURRENT_DATE - 90
            GROUP BY loan_officer_id
        ) lo_stats
    """)

    def calc_diff(current_val, benchmark_val):
        if benchmark_val == 0:
            return 0
        return round(((current_val - benchmark_val) / benchmark_val) * 100, 1)

    data = {
        "benchmark_type": "company",
        "period_days": 90,
        "current": {
            "funded_units": current["funded_units"] or 0,
            "funded_volume": float(current["funded_volume"] or 0),
            "avg_cycle_time": round(float(current["avg_cycle_time"] or 0), 1),
        },
        "benchmark": {
            "avg_units": round(float(benchmark["avg_units"] or 0), 1),
            "avg_volume": float(benchmark["avg_volume"] or 0),
            "avg_cycle_time": round(float(benchmark["avg_cycle_time"] or 0), 1),
        },
        "comparison": {
            "units_diff_pct": calc_diff(current["funded_units"] or 0, benchmark["avg_units"] or 1),
            "volume_diff_pct": calc_diff(current["funded_volume"] or 0, benchmark["avg_volume"] or 1),
            "cycle_time_diff_pct": calc_diff(current["avg_cycle_time"] or 0, benchmark["avg_cycle_time"] or 1),
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Units: {data['comparison']['units_diff_pct']}% vs benchmark",
    )


@mortgage_tool(
    name="get_lo_pipeline_breakdown",
    description="Get pipeline breakdown by loan officer",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def get_lo_pipeline_breakdown(
    organization_id: Optional[str] = None,
    include_closed: bool = False,
) -> ToolResult:
    """Get pipeline breakdown by LO."""
    params = {}
    filters = []

    if not include_closed:
        filters.append("l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')")
    if organization_id:
        filters.append("l.organization_id = :organization_id")
        params["organization_id"] = organization_id

    where_sql = " AND ".join(filters) if filters else "1=1"

    breakdown = execute_query(f"""
        SELECT
            u.id as lo_id,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name,
            COUNT(*) as count,
            SUM(l.amount) as volume,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400) as avg_days
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE {where_sql}
        GROUP BY u.id, u.first_name, u.last_name
        ORDER BY volume DESC
    """, params)

    if not breakdown:
        return ToolResult.no_data("No pipeline data found")

    total_volume = sum(float(row["volume"] or 0) for row in breakdown)

    data = {
        "total_volume": total_volume,
        "total_volume_formatted": format_currency(total_volume),
        "lo_count": len(breakdown),
        "breakdown": [
            {
                "lo_id": row["lo_id"],
                "lo_name": row["lo_name"],
                "count": row["count"],
                "volume": float(row["volume"] or 0),
                "volume_formatted": format_currency(row["volume"]),
                "pct_of_total": round((float(row["volume"] or 0) / total_volume) * 100, 1) if total_volume > 0 else 0,
                "avg_days_in_stage": round(float(row["avg_days"] or 0), 1),
            }
            for row in breakdown
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"{len(breakdown)} LOs, {format_currency(total_volume)} total pipeline",
    )


# =============================================================================
# COMPLIANCE CHECKER TOOLS (8 tools)
# =============================================================================

@mortgage_tool(
    name="check_trid_compliance",
    description="Check TILA-RESPA Integrated Disclosure compliance for a loan",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def check_trid_compliance(
    loan_id: str,
) -> ToolResult:
    """Check TRID compliance using real Loan date columns and disclosure_events table."""
    loan = execute_single("""
        SELECT
            l.id, l.loan_number, l.application_date,
            l.initial_disclosures_sent_date,
            l.initial_disclosures_signed_date,
            l.cd_sent_to_borrower_date,
            l.cd_acknowledged_date,
            l.funded_date
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    issues = []
    warnings = []

    # LE timing - must be within 3 business days of application
    # Note: this checks calendar days as an approximation; real compliance uses business days
    if loan["application_date"] and loan["initial_disclosures_sent_date"]:
        le_days = days_between(loan["application_date"], loan["initial_disclosures_sent_date"])
        if le_days > 3:
            issues.append({
                "type": "LE_TIMING",
                "message": f"LE sent {le_days} days after application (max 3 business days)",
                "severity": "high",
            })
    elif loan["application_date"] and not loan["initial_disclosures_sent_date"]:
        days_since_app = days_between(loan["application_date"], datetime.now())
        if days_since_app > 2:
            issues.append({
                "type": "LE_NOT_SENT",
                "message": f"LE not sent - {days_since_app} days since application",
                "severity": "critical",
            })

    # CD timing - must be 3 business days before closing
    if loan["cd_sent_to_borrower_date"] and loan["funded_date"]:
        cd_days = days_between(loan["cd_sent_to_borrower_date"], loan["funded_date"])
        if cd_days < 3:
            issues.append({
                "type": "CD_TIMING",
                "message": f"CD sent only {cd_days} days before closing (min 3 business days)",
                "severity": "critical",
            })

    # Check revision count from disclosure_events table
    revision_counts = execute_single("""
        SELECT
            COUNT(CASE WHEN disclosure_type = 'revised_le' THEN 1 END) as le_revisions,
            COUNT(CASE WHEN disclosure_type = 'revised_cd' THEN 1 END) as cd_revisions
        FROM disclosure_events
        WHERE loan_id = :loan_id
    """, {"loan_id": loan_id})

    le_revisions = revision_counts["le_revisions"] if revision_counts else 0
    cd_revisions = revision_counts["cd_revisions"] if revision_counts else 0

    if le_revisions > 2:
        warnings.append({
            "type": "EXCESSIVE_LE_REVISIONS",
            "message": f"{le_revisions} LE revisions - review for valid change circumstances",
        })

    is_compliant = len([i for i in issues if i["severity"] in ["high", "critical"]]) == 0

    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "is_compliant": is_compliant,
        "issues": issues,
        "warnings": warnings,
        "timeline": {
            "application_date": format_date(loan["application_date"]),
            "le_sent": format_date(loan["initial_disclosures_sent_date"]),
            "le_signed": format_date(loan["initial_disclosures_signed_date"]),
            "cd_sent": format_date(loan["cd_sent_to_borrower_date"]),
            "cd_acknowledged": format_date(loan["cd_acknowledged_date"]),
            "funded_date": format_date(loan["funded_date"]),
        },
        "revisions": {
            "le_revisions": le_revisions,
            "cd_revisions": cd_revisions,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"TRID {'Compliant' if is_compliant else 'NON-COMPLIANT'}: {len(issues)} issues",
    )


@mortgage_tool(
    name="check_respa_compliance",
    description="Check RESPA compliance for affiliated business arrangements using available loan data",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def check_respa_compliance(
    loan_id: str,
) -> ToolResult:
    """Check RESPA compliance using available Loan string columns."""
    loan = execute_single("""
        SELECT
            l.id, l.loan_number, l.title_company, l.lender,
            l.realtor_agent, l.loan_officer_name, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    issues = []

    # Check for affiliated business arrangements by examining service providers
    # In the real schema, title_company, lender, and realtor_agent are plain string columns.
    # Flag these for manual AfBA disclosure verification.
    providers = []
    if loan["title_company"]:
        providers.append({"name": loan["title_company"], "role": "title_company"})
    if loan["lender"]:
        providers.append({"name": loan["lender"], "role": "lender"})
    if loan["realtor_agent"]:
        providers.append({"name": loan["realtor_agent"], "role": "realtor"})

    for provider in providers:
        issues.append({
            "type": "AFFILIATED_BUSINESS_CHECK",
            "message": f"Verify AfBA disclosure for {provider['role']}: {provider['name']}",
            "severity": "low",
        })

    # No automated way to detect referral fees in current schema;
    # flag for manual review if loan has a referral partner via lead
    referral_check = execute_single("""
        SELECT ld.referral_partner_id, rp.name as partner_name
        FROM leads ld
        JOIN loans l ON l.loan_number = ld.loan_number
        LEFT JOIN referral_partners rp ON rp.id = ld.referral_partner_id
        WHERE l.id = :loan_id AND ld.referral_partner_id IS NOT NULL
        LIMIT 1
    """, {"loan_id": loan_id})

    if referral_check and referral_check["partner_name"]:
        issues.append({
            "type": "REFERRAL_PARTNER",
            "message": f"Referral partner: {referral_check['partner_name']} - verify no prohibited referral fees",
            "severity": "medium",
        })

    high_severity = len([i for i in issues if i["severity"] in ["high", "critical"]])
    is_compliant = high_severity == 0

    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "is_compliant": is_compliant,
        "issues": issues,
        "service_providers": len(providers),
    }

    return ToolResult.success(
        data=data,
        message=f"RESPA {'Compliant' if is_compliant else 'Review Required'}: {len(issues)} items to review",
    )


@mortgage_tool(
    name="check_pricing_consistency",
    description="Check pricing consistency across similar loans to identify rate outliers",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def check_pricing_consistency(
    loan_id: Optional[str] = None,
    lo_id: Optional[str] = None,
    days: int = 90,
) -> ToolResult:
    """Check pricing consistency (rate variance analysis)."""
    if loan_id:
        loan = execute_single("""
            SELECT
                l.id, l.loan_number, l.rate, l.loan_type
            FROM loans l
            WHERE l.id = :loan_id
        """, {"loan_id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        # Compare to similar loans of same type
        comparable = execute_single("""
            SELECT
                AVG(rate) as avg_rate,
                MIN(rate) as min_rate,
                MAX(rate) as max_rate,
                COUNT(*) as count
            FROM loans
            WHERE loan_type = :loan_type
                AND rate IS NOT NULL
                AND funded_date >= CURRENT_DATE - 90
        """, {
            "loan_type": loan["loan_type"],
        })

        rate_variance = 0
        if comparable["avg_rate"]:
            rate_variance = float(loan["rate"] or 0) - float(comparable["avg_rate"])

        flags = []
        if abs(rate_variance) > 0.25:
            flags.append({
                "type": "RATE_VARIANCE",
                "message": f"Rate is {rate_variance:+.3f}% from comparable average",
                "severity": "medium" if abs(rate_variance) < 0.5 else "high",
            })

        data = {
            "loan_id": loan_id,
            "loan_number": loan["loan_number"],
            "flags": flags,
            "rate_analysis": {
                "loan_rate": float(loan["rate"] or 0),
                "comparable_avg": float(comparable["avg_rate"] or 0),
                "variance": round(rate_variance, 3),
                "comparable_count": comparable["count"],
            },
        }
    else:
        # Aggregate analysis by loan type
        analysis = execute_query("""
            SELECT
                loan_type,
                COUNT(*) as count,
                AVG(rate) as avg_rate,
                STDDEV(rate) as rate_stddev
            FROM loans
            WHERE funded_date >= CURRENT_DATE - :days
                AND rate IS NOT NULL
            GROUP BY loan_type
        """, {"days": days})

        data = {
            "period_days": days,
            "by_loan_type": [
                {
                    "loan_type": row["loan_type"],
                    "count": row["count"],
                    "avg_rate": round(float(row["avg_rate"] or 0), 3),
                    "rate_stddev": round(float(row["rate_stddev"] or 0), 3),
                }
                for row in analysis
            ],
        }

    return ToolResult.success(
        data=data,
        message="Pricing consistency analysis complete",
    )


@mortgage_tool(
    name="get_state_requirements",
    description="Get state-specific compliance requirements",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def get_state_requirements(
    state_code: str,
    loan_type: Optional[str] = None,
) -> ToolResult:
    """Get state-specific requirements."""
    # State requirements lookup
    state_reqs = {
        "CA": {
            "licensing": ["DBO License", "NMLS Registration"],
            "disclosures": ["MLDS Required", "Fair Lending Notice"],
            "max_fees": {"origination": 3.0, "total_points": 5.0},
            "prepayment_rules": "No prepayment penalties on primary residence",
            "cooling_off": None,
        },
        "TX": {
            "licensing": ["OCCC License", "NMLS Registration"],
            "disclosures": ["Texas Home Equity Disclosure"],
            "max_fees": {"cash_out_ltv": 80.0, "total_fees": 3.0},
            "prepayment_rules": "12-month seasoning for cash-out",
            "cooling_off": "12 days for home equity",
        },
        "NY": {
            "licensing": ["DFS License", "NMLS Registration"],
            "disclosures": ["NYCRR Disclosure", "Subprime Warning"],
            "max_fees": {"origination": 3.0},
            "prepayment_rules": "Limits on prepayment penalties",
            "cooling_off": None,
        },
        "FL": {
            "licensing": ["OFR License", "NMLS Registration"],
            "disclosures": ["Standard Federal"],
            "max_fees": {},
            "prepayment_rules": "No specific restrictions",
            "cooling_off": None,
        },
    }

    if state_code.upper() not in state_reqs:
        return ToolResult.success(
            data={
                "state": state_code.upper(),
                "requirements": "Standard federal requirements apply",
                "specific_rules": [],
            },
            message=f"No specific state rules found for {state_code}",
        )

    reqs = state_reqs[state_code.upper()]

    data = {
        "state": state_code.upper(),
        "licensing": reqs["licensing"],
        "required_disclosures": reqs["disclosures"],
        "fee_limits": reqs["max_fees"],
        "prepayment_rules": reqs["prepayment_rules"],
        "cooling_off_period": reqs["cooling_off"],
    }

    if loan_type:
        data["loan_type_specific"] = f"Review {loan_type} specific rules for {state_code}"

    return ToolResult.success(
        data=data,
        message=f"Requirements for {state_code.upper()}: {len(reqs['disclosures'])} disclosures required",
    )


@mortgage_tool(
    name="audit_loan_file",
    description="Perform comprehensive compliance audit on a loan file",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def audit_loan_file(
    loan_id: str,
) -> ToolResult:
    """Audit loan file for compliance."""
    loan = execute_single("""
        SELECT
            l.*,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name,
            u.nmls_number as lo_nmls
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    audit_results = {
        "passed": [],
        "failed": [],
        "warnings": [],
    }

    # NMLS check
    if loan["lo_nmls"]:
        audit_results["passed"].append({"check": "LO_NMLS", "message": f"NMLS #{loan['lo_nmls']} on file"})
    else:
        audit_results["failed"].append({"check": "LO_NMLS", "message": "LO NMLS ID missing"})

    # Disclosure timing
    if loan["application_date"] and loan["initial_disclosures_sent_date"]:
        le_days = days_between(loan["application_date"], loan["initial_disclosures_sent_date"])
        if le_days <= 3:
            audit_results["passed"].append({"check": "LE_TIMING", "message": f"LE sent in {le_days} days"})
        else:
            audit_results["failed"].append({"check": "LE_TIMING", "message": f"LE sent in {le_days} days (max 3)"})

    # Document checklist — query the real documents table
    docs = execute_query("""
        SELECT doc_type, status FROM documents WHERE loan_id = :loan_id
    """, {"loan_id": loan_id})

    required_docs = ["paystubs", "w2", "bank_statements", "credit_report", "appraisal"]
    for req_doc in required_docs:
        found = any(d["doc_type"] == req_doc and d["status"] == "active" for d in docs)
        if found:
            audit_results["passed"].append({"check": f"DOC_{req_doc.upper()}", "message": f"{req_doc} on file"})
        else:
            audit_results["warnings"].append({"check": f"DOC_{req_doc.upper()}", "message": f"{req_doc} not found"})

    total_checks = len(audit_results["passed"]) + len(audit_results["failed"]) + len(audit_results["warnings"])
    pass_rate = len(audit_results["passed"]) / total_checks * 100 if total_checks > 0 else 0

    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "audit_date": datetime.now().isoformat(),
        "summary": {
            "passed": len(audit_results["passed"]),
            "failed": len(audit_results["failed"]),
            "warnings": len(audit_results["warnings"]),
            "pass_rate": round(pass_rate, 1),
        },
        "results": audit_results,
        "recommendation": "Review required" if audit_results["failed"] else "File compliant",
    }

    return ToolResult.success(
        data=data,
        message=f"Audit: {len(audit_results['failed'])} failures, {len(audit_results['warnings'])} warnings",
    )


@mortgage_tool(
    name="get_disclosure_timeline",
    description="Get disclosure timeline and status for a loan",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def get_disclosure_timeline(
    loan_id: str,
) -> ToolResult:
    """Get disclosure timeline from Loan date columns and disclosure_events table."""
    loan = execute_single("""
        SELECT
            l.id, l.loan_number, l.application_date,
            l.initial_disclosures_sent_date,
            l.initial_disclosures_signed_date,
            l.loan_estimate_sent_date,
            l.cd_sent_to_borrower_date,
            l.cd_acknowledged_date,
            l.cd_received_signed_date,
            l.funded_date
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    timeline = []

    if loan["application_date"]:
        timeline.append({"event": "Application", "date": format_date(loan["application_date"]), "status": "complete"})

    if loan["initial_disclosures_sent_date"]:
        timeline.append({"event": "Initial Disclosures Sent", "date": format_date(loan["initial_disclosures_sent_date"]), "status": "complete"})
    else:
        timeline.append({"event": "Initial Disclosures Sent", "date": None, "status": "pending"})

    if loan["initial_disclosures_signed_date"]:
        timeline.append({"event": "Initial Disclosures Signed", "date": format_date(loan["initial_disclosures_signed_date"]), "status": "complete"})

    if loan["cd_sent_to_borrower_date"]:
        timeline.append({"event": "CD Sent", "date": format_date(loan["cd_sent_to_borrower_date"]), "status": "complete"})

    if loan["cd_acknowledged_date"]:
        timeline.append({"event": "CD Acknowledged", "date": format_date(loan["cd_acknowledged_date"]), "status": "complete"})

    if loan["funded_date"]:
        timeline.append({"event": "Funded", "date": format_date(loan["funded_date"]), "status": "complete"})

    # Get revision counts from disclosure_events
    revision_counts = execute_single("""
        SELECT
            COUNT(CASE WHEN disclosure_type = 'revised_le' THEN 1 END) as le_revisions,
            COUNT(CASE WHEN disclosure_type = 'revised_cd' THEN 1 END) as cd_revisions
        FROM disclosure_events
        WHERE loan_id = :loan_id
    """, {"loan_id": loan_id})

    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "timeline": timeline,
        "revisions": {
            "le_revisions": revision_counts["le_revisions"] if revision_counts else 0,
            "cd_revisions": revision_counts["cd_revisions"] if revision_counts else 0,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Timeline: {len([t for t in timeline if t['status'] == 'complete'])}/{len(timeline)} complete",
    )


@mortgage_tool(
    name="check_tolerance_violations",
    description="Check for fee tolerance violations between LE and CD",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def check_tolerance_violations(
    loan_id: str,
) -> ToolResult:
    """Check tolerance violations using the loan_fees table."""
    fees = execute_query("""
        SELECT
            fee_name, fee_category, le_amount, cd_amount, tolerance_category
        FROM loan_fees
        WHERE loan_id = :loan_id
    """, {"loan_id": loan_id})

    if not fees:
        return ToolResult.no_data(f"No fee data for loan {loan_id}")

    violations = []
    zero_tolerance_total = {"le": 0, "cd": 0}
    ten_percent_total = {"le": 0, "cd": 0}

    for fee in fees:
        le_amt = float(fee["le_amount"] or 0)
        cd_amt = float(fee["cd_amount"] or 0)
        diff = cd_amt - le_amt

        if fee["tolerance_category"] == "zero":
            zero_tolerance_total["le"] += le_amt
            zero_tolerance_total["cd"] += cd_amt
            if diff > 0:
                violations.append({
                    "fee": fee["fee_name"],
                    "tolerance": "zero",
                    "le_amount": le_amt,
                    "cd_amount": cd_amt,
                    "difference": diff,
                    "cure_amount": diff,
                })

        elif fee["tolerance_category"] == "ten_percent":
            ten_percent_total["le"] += le_amt
            ten_percent_total["cd"] += cd_amt

    # Check 10% category
    ten_pct_diff = ten_percent_total["cd"] - ten_percent_total["le"]
    ten_pct_allowed = ten_percent_total["le"] * 0.10
    if ten_pct_diff > ten_pct_allowed:
        violations.append({
            "fee": "10% Tolerance Category Total",
            "tolerance": "ten_percent",
            "le_amount": ten_percent_total["le"],
            "cd_amount": ten_percent_total["cd"],
            "difference": ten_pct_diff,
            "allowed": ten_pct_allowed,
            "cure_amount": ten_pct_diff - ten_pct_allowed,
        })

    total_cure = sum(v.get("cure_amount", 0) for v in violations)

    data = {
        "loan_id": loan_id,
        "violations": violations,
        "violation_count": len(violations),
        "total_cure_amount": total_cure,
        "total_cure_formatted": format_currency(total_cure),
        "is_compliant": len(violations) == 0,
    }

    return ToolResult.success(
        data=data,
        message=f"{len(violations)} tolerance violations, cure: {format_currency(total_cure)}",
    )


@mortgage_tool(
    name="get_compliance_history",
    description="Get compliance alert history for loan or LO",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def get_compliance_history(
    loan_id: Optional[str] = None,
    lo_id: Optional[str] = None,
    days: int = 365,
) -> ToolResult:
    """Get compliance history from compliance_alerts table."""
    params = {"days": days}

    if loan_id:
        history = execute_query("""
            SELECT
                alert_type, severity, title, description, status,
                created_at, resolved_at, resolution_notes
            FROM compliance_alerts
            WHERE loan_id = :loan_id
            ORDER BY created_at DESC
        """, {"loan_id": loan_id})

        data = {
            "loan_id": loan_id,
            "alerts": [
                {
                    "type": h["alert_type"],
                    "severity": h["severity"],
                    "title": h["title"],
                    "description": h["description"],
                    "status": h["status"],
                    "created": format_date(h["created_at"]),
                    "resolved": format_date(h["resolved_at"]),
                }
                for h in history
            ],
            "total_alerts": len(history),
            "open_alerts": len([h for h in history if h["status"] == "open"]),
        }
    else:
        # LO or aggregate history
        params["lo_id"] = lo_id

        summary = execute_query(f"""
            SELECT
                ca.alert_type,
                COUNT(*) as count,
                COUNT(CASE WHEN ca.status = 'open' THEN 1 END) as open_count
            FROM compliance_alerts ca
            JOIN loans l ON l.id = ca.loan_id
            WHERE ca.created_at >= CURRENT_DATE - :days
            {"AND l.loan_officer_id = :lo_id" if lo_id else ""}
            GROUP BY ca.alert_type
            ORDER BY count DESC
        """, params)

        data = {
            "period_days": days,
            "lo_id": lo_id,
            "by_type": [
                {
                    "type": s["alert_type"],
                    "count": s["count"],
                    "open": s["open_count"],
                }
                for s in summary
            ],
            "total_alerts": sum(s["count"] for s in summary),
        }

    return ToolResult.success(
        data=data,
        message=f"Compliance history: {data.get('total_alerts', 0)} alerts found",
    )


# =============================================================================
# LEAD NURTURER TOOLS (8 tools)
# =============================================================================

@mortgage_tool(
    name="get_lead_details",
    description="Get complete lead profile and current status",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def get_lead_details(
    lead_id: str,
) -> ToolResult:
    """Get lead details."""
    lead = execute_single("""
        SELECT
            l.id, l.first_name, l.last_name, l.email, l.phone,
            l.stage, l.source, l.created_at,
            l.owner_id, l.ai_score, l.last_contact,
            l.property_type, l.loan_purpose, l.loan_amount,
            l.credit_score, l.preapproval_amount,
            CONCAT(u.first_name, ' ', u.last_name) as assigned_to_name
        FROM leads l
        LEFT JOIN users u ON u.id = l.owner_id
        WHERE l.id = :lead_id
    """, {"lead_id": lead_id})

    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")

    # Get recent activities
    activities = execute_query("""
        SELECT type, content, created_at
        FROM activities
        WHERE lead_id = :lead_id
        ORDER BY created_at DESC
        LIMIT 5
    """, {"lead_id": lead_id})

    data = {
        "id": lead["id"],
        "name": f"{lead['first_name'] or ''} {lead['last_name'] or ''}".strip(),
        "email": lead["email"],
        "phone": lead["phone"],
        "stage": lead["stage"],
        "score": lead["ai_score"],
        "source": lead["source"],
        "assigned_to": lead["assigned_to_name"],
        "created_at": format_date(lead["created_at"]),
        "last_contact": format_date(lead["last_contact"]),
        "loan_interest": {
            "purpose": lead["loan_purpose"],
            "property_type": lead["property_type"],
            "loan_amount": float(lead["loan_amount"] or 0),
            "credit_score": lead["credit_score"],
            "preapproval_amount": float(lead["preapproval_amount"] or 0),
        },
        "recent_activities": [
            {
                "type": a["type"],
                "content": (a["content"] or "")[:200],
                "date": format_date(a["created_at"]),
            }
            for a in activities
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"Lead: {data['name']} - Score: {data['score']}",
    )


@mortgage_tool(
    name="get_engagement_history",
    description="Get activity/engagement history for a lead",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def get_engagement_history(
    lead_id: str,
    limit: int = 50,
) -> ToolResult:
    """Get engagement history from the activities table."""
    activities = execute_query("""
        SELECT
            a.type, a.content, a.duration, a.sentiment,
            a.created_at, a.user_id,
            CONCAT(u.first_name, ' ', u.last_name) as user_name
        FROM activities a
        LEFT JOIN users u ON u.id = a.user_id
        WHERE a.lead_id = :lead_id
        ORDER BY a.created_at DESC
        LIMIT :limit
    """, {"lead_id": lead_id, "limit": limit})

    if not activities:
        return ToolResult.no_data(f"No activity history for lead {lead_id}")

    # Aggregate stats by activity type
    by_type = {}
    for a in activities:
        atype = a["type"]
        if atype not in by_type:
            by_type[atype] = {"count": 0}
        by_type[atype]["count"] += 1

    data = {
        "lead_id": lead_id,
        "total_activities": len(activities),
        "by_type": by_type,
        "activities": [
            {
                "type": a["type"],
                "content": (a["content"] or "")[:200],
                "duration": a["duration"],
                "sentiment": a["sentiment"],
                "user": a["user_name"],
                "date": format_date(a["created_at"]),
            }
            for a in activities
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"{len(activities)} activities found",
    )


@mortgage_tool(
    name="score_lead",
    description="Calculate or update lead score based on behavior and profile",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def score_lead(
    lead_id: str,
) -> ToolResult:
    """Score a lead."""
    lead = execute_single("""
        SELECT
            l.id, l.ai_score, l.credit_score,
            l.loan_amount, l.preapproval_amount, l.source,
            l.created_at, l.last_contact
        FROM leads l
        WHERE l.id = :lead_id
    """, {"lead_id": lead_id})

    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")

    # Get activity stats from the activities table
    activity_stats = execute_single("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN type = 'Email' THEN 1 END) as emails,
            COUNT(CASE WHEN type = 'Call' THEN 1 END) as calls,
            COUNT(CASE WHEN type = 'Meeting' THEN 1 END) as meetings
        FROM activities
        WHERE lead_id = :lead_id AND created_at >= CURRENT_DATE - 30
    """, {"lead_id": lead_id})

    # Calculate score components
    score_breakdown = {
        "profile": 0,
        "engagement": 0,
        "recency": 0,
        "intent": 0,
    }

    # Profile score (max 25)
    if lead["credit_score"] and lead["credit_score"] >= 700:
        score_breakdown["profile"] += 10
    if lead["loan_amount"] and lead["loan_amount"] >= 300000:
        score_breakdown["profile"] += 10
    if lead["preapproval_amount"] and lead["preapproval_amount"] > 0:
        score_breakdown["profile"] += 5

    # Engagement score (max 25)
    total_activities = activity_stats["total"] or 0
    if total_activities >= 5:
        score_breakdown["engagement"] += 15
    elif total_activities >= 2:
        score_breakdown["engagement"] += 10
    if activity_stats["calls"] and activity_stats["calls"] >= 1:
        score_breakdown["engagement"] += 5
    if activity_stats["meetings"] and activity_stats["meetings"] >= 1:
        score_breakdown["engagement"] += 5

    # Recency score (max 25)
    if lead["last_contact"]:
        days_since = days_between(lead["last_contact"], datetime.now())
        if days_since <= 3:
            score_breakdown["recency"] = 25
        elif days_since <= 7:
            score_breakdown["recency"] = 20
        elif days_since <= 14:
            score_breakdown["recency"] = 15
        elif days_since <= 30:
            score_breakdown["recency"] = 10

    # Intent score (max 25)
    high_intent_sources = ["rate_quote", "application_started", "referral"]
    if lead["source"] in high_intent_sources:
        score_breakdown["intent"] = 25
    elif lead["source"] in ["website", "landing_page"]:
        score_breakdown["intent"] = 15
    else:
        score_breakdown["intent"] = 10

    total_score = sum(score_breakdown.values())

    # Determine grade
    if total_score >= 80:
        grade = "A"
    elif total_score >= 60:
        grade = "B"
    elif total_score >= 40:
        grade = "C"
    else:
        grade = "D"

    data = {
        "lead_id": lead_id,
        "previous_score": lead["ai_score"],
        "new_score": total_score,
        "grade": grade,
        "breakdown": score_breakdown,
        "activity_stats": {
            "total": activity_stats["total"] or 0,
            "emails": activity_stats["emails"] or 0,
            "calls": activity_stats["calls"] or 0,
            "meetings": activity_stats["meetings"] or 0,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Lead score: {total_score} (Grade {grade})",
    )


@mortgage_tool(
    name="suggest_followup",
    description="Suggest next best action for lead follow-up",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def suggest_followup(
    lead_id: str,
) -> ToolResult:
    """Suggest follow-up action."""
    lead = execute_single("""
        SELECT
            l.id, l.first_name, l.stage, l.ai_score,
            l.last_contact, l.preferred_communication,
            l.loan_purpose, l.loan_amount
        FROM leads l
        WHERE l.id = :lead_id
    """, {"lead_id": lead_id})

    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")

    # Get last activity
    last_activity = execute_single("""
        SELECT type, content, sentiment, created_at
        FROM activities
        WHERE lead_id = :lead_id
        ORDER BY created_at DESC
        LIMIT 1
    """, {"lead_id": lead_id})

    days_since_contact = days_between(lead["last_contact"], datetime.now()) if lead["last_contact"] else 999

    # Determine recommendation
    suggestions = []

    if days_since_contact > 7:
        suggestions.append({
            "action": "call",
            "priority": "high",
            "reason": f"No contact in {days_since_contact} days",
            "script_hint": f"Check in on {lead['loan_purpose'] or 'loan'} interest",
        })

    if lead["ai_score"] and lead["ai_score"] >= 70:
        suggestions.append({
            "action": "schedule_meeting",
            "priority": "high",
            "reason": "High lead score indicates strong interest",
            "script_hint": "Offer consultation to discuss options",
        })

    if last_activity:
        last_type = last_activity["type"]
        # Suggest alternate channel
        if last_type == "Call":
            suggestions.append({
                "action": "send_email",
                "priority": "medium",
                "reason": f"Last contact was a call - try email follow-up",
                "script_hint": "Follow up via email with details discussed",
            })
        elif last_type == "Email":
            suggestions.append({
                "action": "make_call",
                "priority": "medium",
                "reason": "Last contact was email - try phone",
                "script_hint": "Follow up via phone",
            })

    if not suggestions:
        suggestions.append({
            "action": "nurture_email",
            "priority": "low",
            "reason": "Keep engaged with valuable content",
            "script_hint": "Send rate update or market info",
        })

    data = {
        "lead_id": lead_id,
        "lead_name": lead["first_name"],
        "current_stage": lead["stage"],
        "days_since_contact": days_since_contact,
        "suggestions": suggestions,
        "preferred_channel": lead["preferred_communication"],
    }

    return ToolResult.success(
        data=data,
        message=f"Suggested: {suggestions[0]['action']} ({suggestions[0]['priority']} priority)",
    )


@mortgage_tool(
    name="draft_message",
    description="Draft personalized message for lead outreach",
    agent_roles=["lead_nurturer"],
    risk_level="HIGH",
)
def draft_message(
    lead_id: str,
    message_type: str,  # email, sms, voicemail_script
    context: Optional[str] = None,
) -> ToolResult:
    """Draft outreach message."""
    lead = execute_single("""
        SELECT
            l.id, l.first_name, l.last_name, l.email,
            l.loan_purpose, l.property_type, l.loan_amount,
            l.source
        FROM leads l
        WHERE l.id = :lead_id
    """, {"lead_id": lead_id})

    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")

    # Template based on type and context
    templates = {
        "email": {
            "initial": {
                "subject": f"Your {lead['loan_purpose'] or 'Home Loan'} Options",
                "body": f"""Hi {lead['first_name']},

Thank you for your interest in exploring mortgage options. I'd love to help you find the best solution for your {lead['loan_purpose'] or 'home financing'} needs.

Based on current rates and your situation, I can help you:
- Compare multiple loan options
- Lock in competitive rates
- Streamline the approval process

Would you have 15 minutes this week for a quick call?

Best regards""",
            },
            "followup": {
                "subject": f"Following up on your mortgage inquiry",
                "body": f"""Hi {lead['first_name']},

I wanted to follow up on my previous message about your mortgage options. Rates have been moving, and I wanted to make sure you have the latest information.

I'm available for a quick call whenever works for you.

Best regards""",
            },
        },
        "sms": {
            "initial": f"Hi {lead['first_name']}, this is from [Company]. Thanks for your mortgage inquiry! Would you have time for a quick call about your options?",
            "followup": f"Hi {lead['first_name']}, following up on your mortgage inquiry. Rates are looking good - let me know if you'd like to chat!",
        },
    }

    template_context = context or "initial"

    if message_type == "email":
        template = templates["email"].get(template_context, templates["email"]["initial"])
        draft = {
            "type": "email",
            "subject": template["subject"],
            "body": template["body"],
            "to": lead["email"],
        }
    else:
        template = templates.get("sms", {}).get(template_context, templates["sms"]["initial"])
        draft = {
            "type": message_type,
            "content": template,
        }

    data = {
        "lead_id": lead_id,
        "lead_name": f"{lead['first_name']} {lead['last_name']}",
        "draft": draft,
        "personalization_used": ["first_name", "loan_purpose"],
        "requires_review": True,
    }

    return ToolResult.success(
        data=data,
        message=f"Draft {message_type} created for {lead['first_name']}",
        requires_approval=True,
    )


@mortgage_tool(
    name="schedule_outreach",
    description="Schedule automated outreach sequence",
    agent_roles=["lead_nurturer"],
    risk_level="HIGH",
)
def schedule_outreach(
    lead_id: str,
    sequence_type: str,  # initial, followup, nurture
    start_date: Optional[str] = None,
) -> ToolResult:
    """Schedule outreach sequence."""
    lead = execute_single("""
        SELECT id, first_name, email, phone FROM leads WHERE id = :lead_id
    """, {"lead_id": lead_id})

    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")

    sequences = {
        "initial": [
            {"day": 0, "channel": "email", "template": "welcome"},
            {"day": 1, "channel": "sms", "template": "intro_sms"},
            {"day": 3, "channel": "call", "template": "intro_call"},
            {"day": 5, "channel": "email", "template": "value_prop"},
        ],
        "followup": [
            {"day": 0, "channel": "email", "template": "followup_1"},
            {"day": 2, "channel": "call", "template": "followup_call"},
            {"day": 4, "channel": "sms", "template": "followup_sms"},
        ],
        "nurture": [
            {"day": 0, "channel": "email", "template": "market_update"},
            {"day": 7, "channel": "email", "template": "rate_alert"},
            {"day": 14, "channel": "email", "template": "tips"},
            {"day": 21, "channel": "email", "template": "check_in"},
        ],
    }

    sequence = sequences.get(sequence_type, sequences["initial"])
    start = datetime.fromisoformat(start_date) if start_date else datetime.now()

    scheduled = []
    for step in sequence:
        scheduled.append({
            "day": step["day"],
            "date": (start + timedelta(days=step["day"])).strftime("%Y-%m-%d"),
            "channel": step["channel"],
            "template": step["template"],
            "status": "scheduled",
        })

    import uuid
    sequence_id = str(uuid.uuid4())[:8].upper()

    data = {
        "sequence_id": sequence_id,
        "lead_id": lead_id,
        "lead_name": lead["first_name"],
        "sequence_type": sequence_type,
        "start_date": start.strftime("%Y-%m-%d"),
        "steps": scheduled,
        "total_touchpoints": len(scheduled),
    }

    return ToolResult.success(
        data=data,
        message=f"Scheduled {len(scheduled)} touchpoints starting {start.strftime('%m/%d')}",
        requires_approval=True,
    )


@mortgage_tool(
    name="get_similar_converted_leads",
    description="Find similar leads that converted to loans to understand success patterns",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def get_similar_converted_leads(
    lead_id: str,
    limit: int = 5,
) -> ToolResult:
    """Find similar converted leads by matching via loan_number."""
    lead = execute_single("""
        SELECT
            id, source, loan_purpose, property_type,
            loan_amount, credit_score
        FROM leads
        WHERE id = :lead_id
    """, {"lead_id": lead_id})

    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")

    # Find leads that have a matching funded loan (via loan_number match)
    similar = execute_query("""
        SELECT
            ld.id, ld.first_name, ld.source, ld.loan_purpose,
            ld.loan_amount as lead_loan_amount,
            lo.loan_number, lo.amount as funded_amount, lo.funded_date
        FROM leads ld
        JOIN loans lo ON lo.loan_number = ld.loan_number
        WHERE lo.stage = 'FUNDED'
            AND ld.id != :lead_id
            AND (ld.source = :source OR ld.loan_purpose = :purpose)
        ORDER BY lo.funded_date DESC
        LIMIT :limit
    """, {
        "lead_id": lead_id,
        "source": lead["source"],
        "purpose": lead["loan_purpose"],
        "limit": limit,
    })

    if not similar:
        return ToolResult.no_data("No similar converted leads found")

    # Analyze patterns
    common_sources = {}
    for s in similar:
        if s["source"]:
            common_sources[s["source"]] = common_sources.get(s["source"], 0) + 1

    data = {
        "lead_id": lead_id,
        "similar_converted": [
            {
                "id": s["id"],
                "source": s["source"],
                "loan_purpose": s["loan_purpose"],
                "funded_amount": float(s["funded_amount"] or 0),
                "funded_date": format_date(s["funded_date"]),
            }
            for s in similar
        ],
        "patterns": {
            "common_sources": common_sources,
            "avg_loan_amount": sum(float(s["funded_amount"] or 0) for s in similar) / len(similar),
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Found {len(similar)} similar converted leads",
    )


@mortgage_tool(
    name="get_optimal_contact_time",
    description="Determine optimal time to contact lead based on activity history",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def get_optimal_contact_time(
    lead_id: str,
) -> ToolResult:
    """Get optimal contact time based on activity patterns."""
    # Get inbound activity patterns (when the lead was most responsive)
    activities = execute_query("""
        SELECT
            EXTRACT(DOW FROM created_at) as day_of_week,
            EXTRACT(HOUR FROM created_at) as hour
        FROM activities
        WHERE lead_id = :lead_id
            AND type IN ('Call', 'Email', 'SMS')
    """, {"lead_id": lead_id})

    lead = execute_single("""
        SELECT preferred_communication FROM leads WHERE id = :lead_id
    """, {"lead_id": lead_id})

    # Analyze patterns or use defaults
    if activities:
        hours = [int(a["hour"]) for a in activities]
        preferred_hour = max(set(hours), key=hours.count) if hours else 10
        preferred = f"{preferred_hour:02d}:00"
    else:
        preferred = "10:00"  # Default

    # Determine best days
    if activities:
        days = [int(a["day_of_week"]) for a in activities]
        best_days = list(set(days))[:3] if days else [1, 2, 3]  # Mon, Tue, Wed default
    else:
        best_days = [1, 2, 3, 4]  # Weekdays

    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    data = {
        "lead_id": lead_id,
        "optimal_time": preferred,
        "best_days": [day_names[d] for d in best_days],
        "preferred_channel": lead["preferred_communication"] if lead else None,
        "based_on_activities": len(activities),
        "recommendation": f"Contact on {day_names[best_days[0]]} around {preferred}",
    }

    return ToolResult.success(
        data=data,
        message=data["recommendation"],
    )


# =============================================================================
# DOCUMENT TRACKER TOOLS (8 tools)
# =============================================================================

@mortgage_tool(
    name="get_missing_documents",
    description="Get list of missing or pending documents for a loan",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def get_missing_documents(
    loan_id: str,
) -> ToolResult:
    """Get missing documents by comparing required doc types against documents table."""
    loan = execute_single("""
        SELECT id, loan_number, loan_type, stage FROM loans WHERE id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Get all documents currently on file for this loan
    existing_docs = execute_query("""
        SELECT doc_type, doc_category, status, uploaded_at
        FROM documents
        WHERE loan_id = :loan_id
    """, {"loan_id": loan_id})

    existing_types = {d["doc_type"] for d in existing_docs}

    # Build requirements from DOCUMENT_CATEGORIES constant
    missing = []
    received = []

    for category, doc_types in DOCUMENT_CATEGORIES.items():
        for doc_type in doc_types:
            if doc_type in existing_types:
                received.append({
                    "type": doc_type,
                    "category": category,
                    "status": next((d["status"] for d in existing_docs if d["doc_type"] == doc_type), "unknown"),
                })
            else:
                # Income and assets are generally required; others depend on stage
                is_required = category in ("income", "assets", "credit")
                missing.append({
                    "type": doc_type,
                    "category": category,
                    "required": is_required,
                })

    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "missing": missing,
        "received_count": len(received),
        "missing_required": len([m for m in missing if m["required"]]),
        "total_on_file": len(existing_docs),
    }

    return ToolResult.success(
        data=data,
        message=f"{len(missing)} missing, {len(received)} on file",
    )


@mortgage_tool(
    name="get_loan_conditions",
    description="Get outstanding compliance alerts/conditions for a loan",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def get_loan_conditions(
    loan_id: str,
    status: Optional[str] = None,  # open, acknowledged, resolved, expired
) -> ToolResult:
    """Get loan conditions from compliance_alerts table."""
    params = {"loan_id": loan_id}
    filters = ["ca.loan_id = :loan_id"]

    if status:
        filters.append("ca.status = :status")
        params["status"] = status

    where_sql = " AND ".join(filters)

    conditions = execute_query(f"""
        SELECT
            ca.id, ca.alert_type, ca.severity, ca.title,
            ca.description, ca.status, ca.deadline_date,
            ca.days_remaining, ca.created_at, ca.resolved_at,
            ca.resolution_notes
        FROM compliance_alerts ca
        WHERE {where_sql}
        ORDER BY
            CASE ca.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
            ca.deadline_date ASC NULLS LAST
    """, params)

    if not conditions:
        return ToolResult.no_data("No conditions/alerts found")

    open_count = len([c for c in conditions if c["status"] == "open"])
    past_due = len([c for c in conditions if c["deadline_date"] and c["deadline_date"] < date.today() and c["status"] == "open"])

    data = {
        "loan_id": loan_id,
        "total": len(conditions),
        "open": open_count,
        "past_due": past_due,
        "conditions": [
            {
                "id": c["id"],
                "type": c["alert_type"],
                "severity": c["severity"],
                "title": c["title"],
                "description": c["description"],
                "status": c["status"],
                "deadline": format_date(c["deadline_date"]),
                "is_past_due": bool(c["deadline_date"] and c["deadline_date"] < date.today() and c["status"] == "open"),
            }
            for c in conditions
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"{open_count} open conditions ({past_due} past due)",
    )


@mortgage_tool(
    name="track_document_status",
    description="Track status of documents for a loan",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def track_document_status(
    document_id: Optional[str] = None,
    loan_id: Optional[str] = None,
) -> ToolResult:
    """Track document status from documents table."""
    if document_id:
        doc = execute_single("""
            SELECT
                d.id, d.loan_id, d.doc_type, d.doc_category, d.status,
                d.filename, d.uploaded_at, d.source,
                l.loan_number, l.borrower_name, l.borrower_email
            FROM documents d
            JOIN loans l ON l.id = d.loan_id
            WHERE d.id = :document_id
        """, {"document_id": document_id})

        if not doc:
            return ToolResult.no_data(f"Document {document_id} not found")

        data = {
            "document_id": doc["id"],
            "loan_number": doc["loan_number"],
            "doc_type": doc["doc_type"],
            "doc_category": doc["doc_category"],
            "status": doc["status"],
            "filename": doc["filename"],
            "borrower": doc["borrower_name"],
            "borrower_email": doc["borrower_email"],
            "uploaded_at": format_date(doc["uploaded_at"]),
            "source": doc["source"],
        }
    else:
        # Get all documents for loan
        docs = execute_query("""
            SELECT
                d.id, d.doc_type, d.doc_category, d.status,
                d.filename, d.uploaded_at
            FROM documents d
            WHERE d.loan_id = :loan_id
            ORDER BY d.uploaded_at DESC
        """, {"loan_id": loan_id})

        data = {
            "loan_id": loan_id,
            "documents": [
                {
                    "id": d["id"],
                    "doc_type": d["doc_type"],
                    "doc_category": d["doc_category"],
                    "status": d["status"],
                    "filename": d["filename"],
                    "uploaded": format_date(d["uploaded_at"]),
                }
                for d in docs
            ],
            "total_count": len(docs),
            "active_count": len([d for d in docs if d["status"] == "active"]),
        }

    return ToolResult.success(
        data=data,
        message="Document status retrieved",
    )


@mortgage_tool(
    name="send_document_reminder",
    description="Send reminder for outstanding documents",
    agent_roles=["document_tracker"],
    risk_level="HIGH",
)
def send_document_reminder(
    loan_id: str,
    document_types: Optional[List[str]] = None,
    channel: str = "email",  # email, sms, both
) -> ToolResult:
    """Send document reminder using borrower info from loan."""
    loan = execute_single("""
        SELECT
            l.id, l.loan_number, l.borrower_name,
            l.borrower_email, l.borrower_phone
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Get missing document types
    if document_types:
        missing = document_types
    else:
        # Find required doc types not yet on file
        existing = execute_query("""
            SELECT doc_type FROM documents
            WHERE loan_id = :loan_id AND status = 'active'
        """, {"loan_id": loan_id})
        existing_types = {d["doc_type"] for d in existing}

        all_required = []
        for category in ("income", "assets", "credit"):
            all_required.extend(DOCUMENT_CATEGORIES.get(category, []))

        missing = [dt for dt in all_required if dt not in existing_types]

    if not missing:
        return ToolResult.no_data("No missing documents to remind about")

    import uuid
    reminder_id = str(uuid.uuid4())[:8].upper()

    data = {
        "reminder_id": reminder_id,
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "borrower": loan["borrower_name"],
        "documents": missing,
        "channel": channel,
        "sent_to": {
            "email": loan["borrower_email"] if channel in ["email", "both"] else None,
            "phone": loan["borrower_phone"] if channel in ["sms", "both"] else None,
        },
        "status": "pending_approval",
    }

    return ToolResult.success(
        data=data,
        message=f"Reminder ready for {len(missing)} documents",
        requires_approval=True,
    )


@mortgage_tool(
    name="escalate_issue",
    description="Escalate a document or condition issue",
    agent_roles=["document_tracker"],
    risk_level="MEDIUM",
)
def escalate_issue(
    loan_id: str,
    issue_type: str,  # missing_document, expired_document, condition_past_due
    description: str,
    escalate_to: Optional[str] = None,
) -> ToolResult:
    """Escalate document issue to LO or specified user."""
    loan = execute_single("""
        SELECT
            l.id, l.loan_number, l.loan_officer_id,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    import uuid
    escalation_id = str(uuid.uuid4())[:8].upper()

    # Default escalation goes to the loan officer
    escalate_to_name = escalate_to or loan["lo_name"]

    data = {
        "escalation_id": escalation_id,
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "issue_type": issue_type,
        "description": description,
        "lo_name": loan["lo_name"],
        "escalated_to": escalate_to_name,
        "escalated_at": datetime.now().isoformat(),
        "status": "open",
    }

    return ToolResult.success(
        data=data,
        message=f"Issue escalated to {escalate_to_name}",
    )


@mortgage_tool(
    name="get_document_timeline",
    description="Get document collection timeline for a loan",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def get_document_timeline(
    loan_id: str,
) -> ToolResult:
    """Get document timeline from the documents table."""
    docs = execute_query("""
        SELECT
            d.doc_type, d.doc_category, d.status,
            d.uploaded_at, d.source,
            CONCAT(u.first_name, ' ', u.last_name) as uploaded_by
        FROM documents d
        LEFT JOIN users u ON u.id = d.uploaded_by_user_id
        WHERE d.loan_id = :loan_id
        ORDER BY d.uploaded_at DESC NULLS LAST
    """, {"loan_id": loan_id})

    if not docs:
        return ToolResult.no_data(f"No documents for loan {loan_id}")

    # Build timeline
    timeline = []
    for doc in docs:
        events = []
        if doc["uploaded_at"]:
            events.append({"event": "uploaded", "date": format_date(doc["uploaded_at"])})

        timeline.append({
            "doc_type": doc["doc_type"],
            "doc_category": doc["doc_category"],
            "current_status": doc["status"],
            "source": doc["source"],
            "uploaded_by": doc["uploaded_by"],
            "events": events,
        })

    data = {
        "loan_id": loan_id,
        "total_documents": len(docs),
        "active": len([d for d in docs if d["status"] == "active"]),
        "timeline": timeline,
    }

    return ToolResult.success(
        data=data,
        message=f"{data['active']}/{data['total_documents']} documents active",
    )


@mortgage_tool(
    name="check_document_expiration",
    description="Check for expiring documents using loan-level expiration date columns",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def check_document_expiration(
    loan_id: Optional[str] = None,
    days_ahead: int = 30,
) -> ToolResult:
    """Check document expiration using loan-level date columns (credit_docs_expire_date, appraisal_docs_expire_date)."""
    params = {"days_ahead": days_ahead}

    if loan_id:
        params["loan_id"] = loan_id
        loan_filter = "l.id = :loan_id AND"
    else:
        loan_filter = ""

    # Check loan-level expiration dates for credit docs and appraisal docs
    expiring = execute_query(f"""
        SELECT
            l.id as loan_id, l.loan_number, l.borrower_name,
            l.credit_docs_expire_date,
            l.appraisal_docs_expire_date
        FROM loans l
        WHERE {loan_filter}
            l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
            AND (
                (l.credit_docs_expire_date IS NOT NULL AND l.credit_docs_expire_date <= CURRENT_DATE + :days_ahead)
                OR
                (l.appraisal_docs_expire_date IS NOT NULL AND l.appraisal_docs_expire_date <= CURRENT_DATE + :days_ahead)
            )
        ORDER BY LEAST(COALESCE(l.credit_docs_expire_date, '9999-12-31'), COALESCE(l.appraisal_docs_expire_date, '9999-12-31')) ASC
    """, params)

    if not expiring:
        return ToolResult.no_data("No expiring documents found")

    expired = []
    expiring_soon = []
    today = date.today()

    for loan in expiring:
        for doc_type, expire_col in [("credit_docs", "credit_docs_expire_date"), ("appraisal_docs", "appraisal_docs_expire_date")]:
            expire_date = loan[expire_col]
            if expire_date is None:
                continue
            if isinstance(expire_date, datetime):
                expire_date = expire_date.date()
            if expire_date > today + timedelta(days=days_ahead):
                continue

            doc_info = {
                "loan_id": loan["loan_id"],
                "loan_number": loan["loan_number"],
                "document_type": doc_type,
                "expires_at": format_date(expire_date),
                "borrower": loan["borrower_name"],
            }

            if expire_date < today:
                doc_info["days_expired"] = (today - expire_date).days
                expired.append(doc_info)
            else:
                doc_info["days_until_expiry"] = (expire_date - today).days
                expiring_soon.append(doc_info)

    data = {
        "days_ahead": days_ahead,
        "expired": expired,
        "expiring_soon": expiring_soon,
        "expired_count": len(expired),
        "expiring_count": len(expiring_soon),
    }

    return ToolResult.success(
        data=data,
        message=f"{len(expired)} expired, {len(expiring_soon)} expiring within {days_ahead} days",
    )


@mortgage_tool(
    name="get_third_party_status",
    description="Get status of third-party orders (appraisal, title, insurance) from loan date columns",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def get_third_party_status(
    loan_id: str,
) -> ToolResult:
    """Get third-party order status from loan date columns (no separate orders table)."""
    loan = execute_single("""
        SELECT
            l.id, l.loan_number,
            l.appraisal_ordered_date, l.appraisal_scheduled_date,
            l.appraisal_completed_date, l.appraisal_received_date,
            l.appraisal_value,
            l.title_ordered_date, l.title_received_date,
            l.insurance_ordered_date, l.insurance_received_date
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    orders = []

    # Appraisal
    appraisal_status = "not_ordered"
    if loan["appraisal_received_date"]:
        appraisal_status = "completed"
    elif loan["appraisal_completed_date"]:
        appraisal_status = "completed_awaiting_receipt"
    elif loan["appraisal_scheduled_date"]:
        appraisal_status = "scheduled"
    elif loan["appraisal_ordered_date"]:
        appraisal_status = "ordered"

    orders.append({
        "type": "appraisal",
        "status": appraisal_status,
        "ordered": format_date(loan["appraisal_ordered_date"]),
        "scheduled": format_date(loan["appraisal_scheduled_date"]),
        "completed": format_date(loan["appraisal_completed_date"]),
        "received": format_date(loan["appraisal_received_date"]),
        "value": float(loan["appraisal_value"] or 0) if loan["appraisal_value"] else None,
    })

    # Title
    title_status = "not_ordered"
    if loan["title_received_date"]:
        title_status = "completed"
    elif loan["title_ordered_date"]:
        title_status = "ordered"

    orders.append({
        "type": "title",
        "status": title_status,
        "ordered": format_date(loan["title_ordered_date"]),
        "received": format_date(loan["title_received_date"]),
    })

    # Insurance
    insurance_status = "not_ordered"
    if loan["insurance_received_date"]:
        insurance_status = "completed"
    elif loan["insurance_ordered_date"]:
        insurance_status = "ordered"

    orders.append({
        "type": "insurance",
        "status": insurance_status,
        "ordered": format_date(loan["insurance_ordered_date"]),
        "received": format_date(loan["insurance_received_date"]),
    })

    pending = [o for o in orders if o["status"] not in ("completed", "not_ordered")]
    completed = [o for o in orders if o["status"] == "completed"]

    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "total_orders": len([o for o in orders if o["status"] != "not_ordered"]),
        "pending_count": len(pending),
        "completed_count": len(completed),
        "orders": orders,
    }

    return ToolResult.success(
        data=data,
        message=f"{len(pending)} pending, {len(completed)} completed orders",
    )


# =============================================================================
# END OF PART 1
# =============================================================================

print(f"Part 1 loaded: {len(tool_registry)} tools registered")
