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


class LoanStatus(str, Enum):
    LEAD = "lead"
    APPLICATION = "application"
    PROCESSING = "processing"
    SUBMITTED = "submitted"
    UNDERWRITING = "underwriting"
    APPROVED = "approved"
    CLEAR_TO_CLOSE = "clear_to_close"
    DOCS_OUT = "docs_out"
    DOCS_BACK = "docs_back"
    FUNDED = "funded"
    CANCELLED = "cancelled"
    DENIED = "denied"


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

SLA_TARGETS = {
    "application_to_disclosure": 3,
    "disclosure_to_submission": 7,
    "submission_to_approval": 5,
    "approval_to_ctc": 3,
    "ctc_to_funding": 5,
}

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
    description="Get pipeline metrics including count, volume, and velocity for a loan officer or branch",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def get_pipeline_metrics(
    lo_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    days: int = 30,
) -> ToolResult:
    """Get pipeline metrics."""
    params = {"days": days}
    filters = ["l.status NOT IN ('funded', 'cancelled', 'denied')"]
    
    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id
    
    where_sql = " AND ".join(filters)
    
    result = execute_single(f"""
        SELECT 
            COUNT(*) as total_count,
            COALESCE(SUM(l.loan_amount), 0) as total_volume,
            COUNT(CASE WHEN l.status IN ('clear_to_close', 'docs_out', 'docs_back') THEN 1 END) as closing_soon,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.status_changed_at)) / 86400) as avg_days_in_status
        FROM loans l
        WHERE {where_sql}
    """, params)
    
    # Get velocity (funded in period)
    velocity = execute_single(f"""
        SELECT COUNT(*) as funded_count, COALESCE(SUM(loan_amount), 0) as funded_volume
        FROM loans l
        WHERE l.funded_at >= CURRENT_DATE - :days
        {"AND l.loan_officer_id = :lo_id" if lo_id else ""}
        {"AND l.branch_id = :branch_id" if branch_id else ""}
    """, params)
    
    data = {
        "total_count": result["total_count"] or 0,
        "total_volume": float(result["total_volume"] or 0),
        "total_volume_formatted": format_currency(result["total_volume"]),
        "closing_soon": result["closing_soon"] or 0,
        "avg_days_in_status": round(float(result["avg_days_in_status"] or 0), 1),
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
    name="get_loans_by_status",
    description="Get loans filtered by status with details",
    agent_roles=["pipeline_analyst"],
    risk_level="LOW",
)
def get_loans_by_status(
    status: str,
    lo_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    limit: int = 50,
) -> ToolResult:
    """Get loans by status."""
    params = {"status": status, "limit": limit}
    filters = ["l.status = :status"]
    
    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id
    
    where_sql = " AND ".join(filters)
    
    loans = execute_query(f"""
        SELECT 
            l.id, l.loan_number, l.loan_amount, l.status,
            l.borrower_name, l.property_address, l.loan_type,
            l.status_changed_at, l.expected_close_date, l.lock_expiration_date,
            u.name as lo_name
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE {where_sql}
        ORDER BY l.status_changed_at DESC
        LIMIT :limit
    """, params)
    
    if not loans:
        return ToolResult.no_data(f"No loans found with status '{status}'")
    
    data = {
        "status": status,
        "count": len(loans),
        "loans": [
            {
                "id": loan["id"],
                "loan_number": loan["loan_number"],
                "borrower": loan["borrower_name"],
                "amount": float(loan["loan_amount"] or 0),
                "amount_formatted": format_currency(loan["loan_amount"]),
                "loan_type": loan["loan_type"],
                "property": loan["property_address"],
                "lo_name": loan["lo_name"],
                "days_in_status": days_between(loan["status_changed_at"], datetime.now()),
                "expected_close": format_date(loan["expected_close_date"]),
                "lock_expires": format_date(loan["lock_expiration_date"]),
            }
            for loan in loans
        ],
    }
    
    return ToolResult.success(
        data=data,
        message=f"{len(loans)} loans in {status}",
    )


@mortgage_tool(
    name="get_loan_aging_report",
    description="Get aging report showing how long loans have been in each stage",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def get_loan_aging_report(
    lo_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    threshold_days: int = 7,
) -> ToolResult:
    """Get loan aging report."""
    params = {"threshold": threshold_days}
    filters = ["l.status NOT IN ('funded', 'cancelled', 'denied')"]
    
    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id
    
    where_sql = " AND ".join(filters)
    
    aging = execute_query(f"""
        SELECT 
            l.status,
            COUNT(*) as count,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.status_changed_at)) / 86400) as avg_days,
            MAX(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.status_changed_at)) / 86400) as max_days,
            COUNT(CASE WHEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.status_changed_at)) / 86400 > :threshold THEN 1 END) as over_threshold
        FROM loans l
        WHERE {where_sql}
        GROUP BY l.status
        ORDER BY avg_days DESC
    """, params)
    
    if not aging:
        return ToolResult.no_data("No active loans found")
    
    total_over_threshold = sum(row["over_threshold"] or 0 for row in aging)
    
    data = {
        "threshold_days": threshold_days,
        "total_over_threshold": total_over_threshold,
        "by_status": [
            {
                "status": row["status"],
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
    branch_id: Optional[str] = None,
    days: int = 90,
) -> ToolResult:
    """Calculate conversion rates between pipeline stages."""
    params = {"days": days}
    filters = ["l.created_at >= CURRENT_DATE - :days"]
    
    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id
    
    where_sql = " AND ".join(filters)
    
    funnel = execute_single(f"""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN application_date IS NOT NULL THEN 1 END) as applications,
            COUNT(CASE WHEN submitted_to_uw_at IS NOT NULL THEN 1 END) as submitted,
            COUNT(CASE WHEN approval_date IS NOT NULL THEN 1 END) as approved,
            COUNT(CASE WHEN clear_to_close_at IS NOT NULL THEN 1 END) as ctc,
            COUNT(CASE WHEN funded_at IS NOT NULL THEN 1 END) as funded,
            COUNT(CASE WHEN status IN ('cancelled', 'denied') THEN 1 END) as fallout
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
            l.id, l.loan_number, l.status, l.loan_type,
            l.application_date, l.submitted_to_uw_at, l.approval_date,
            l.clear_to_close_at, l.expected_close_date
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})
    
    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")
    
    # Get historical averages for this loan type
    historical = execute_single("""
        SELECT 
            AVG(EXTRACT(EPOCH FROM (submitted_to_uw_at - application_date)) / 86400) as avg_app_to_submit,
            AVG(EXTRACT(EPOCH FROM (approval_date - submitted_to_uw_at)) / 86400) as avg_submit_to_approve,
            AVG(EXTRACT(EPOCH FROM (clear_to_close_at - approval_date)) / 86400) as avg_approve_to_ctc,
            AVG(EXTRACT(EPOCH FROM (funded_at - clear_to_close_at)) / 86400) as avg_ctc_to_fund
        FROM loans
        WHERE loan_type = :loan_type AND funded_at >= CURRENT_DATE - 180
    """, {"loan_type": loan["loan_type"]})
    
    # Calculate predicted close based on current stage
    now = datetime.now()
    remaining_days = 0
    stages_remaining = []
    
    status_order = ["application", "processing", "submitted", "underwriting", "approved", "clear_to_close"]
    current_idx = status_order.index(loan["status"]) if loan["status"] in status_order else 0
    
    if current_idx < 2:  # Before submission
        remaining_days += float(historical["avg_app_to_submit"] or 5)
        stages_remaining.append(("submission", float(historical["avg_app_to_submit"] or 5)))
    if current_idx < 4:  # Before approval
        remaining_days += float(historical["avg_submit_to_approve"] or 7)
        stages_remaining.append(("approval", float(historical["avg_submit_to_approve"] or 7)))
    if current_idx < 5:  # Before CTC
        remaining_days += float(historical["avg_approve_to_ctc"] or 3)
        stages_remaining.append(("clear_to_close", float(historical["avg_approve_to_ctc"] or 3)))
    
    remaining_days += float(historical["avg_ctc_to_fund"] or 5)
    stages_remaining.append(("funding", float(historical["avg_ctc_to_fund"] or 5)))
    
    predicted_close = now + timedelta(days=remaining_days)
    
    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "current_status": loan["status"],
        "expected_close_date": format_date(loan["expected_close_date"]),
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
    branch_id: Optional[str] = None,
) -> ToolResult:
    """Identify pipeline bottlenecks."""
    params = {}
    filters = ["l.status NOT IN ('funded', 'cancelled', 'denied')"]
    
    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id
    
    where_sql = " AND ".join(filters)
    
    bottlenecks = execute_query(f"""
        SELECT 
            l.status,
            COUNT(*) as count,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.status_changed_at)) / 86400) as avg_days
        FROM loans l
        WHERE {where_sql}
        GROUP BY l.status
        HAVING AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.status_changed_at)) / 86400) > 5
        ORDER BY avg_days DESC
    """, params)
    
    sla_comparison = []
    for row in bottlenecks:
        status = row["status"]
        avg_days = float(row["avg_days"] or 0)
        target = SLA_TARGETS.get(f"{status}_to_next", 5)
        sla_comparison.append({
            "status": status,
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
            data["recommendations"].append(f"Review {b['count']} loans stuck in {b['status']} (avg {b['avg_days']} days)")
    
    return ToolResult.success(
        data=data,
        message=f"{data['critical_count']} critical bottlenecks identified",
    )


@mortgage_tool(
    name="compare_to_benchmark",
    description="Compare pipeline metrics to company or industry benchmarks",
    agent_roles=["pipeline_analyst", "team_coach"],
    risk_level="LOW",
)
def compare_to_benchmark(
    lo_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    benchmark_type: str = "company",
) -> ToolResult:
    """Compare to benchmarks."""
    params = {}
    filters = ["l.funded_at >= CURRENT_DATE - 90"]
    
    if lo_id:
        filters.append("l.loan_officer_id = :lo_id")
        params["lo_id"] = lo_id
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id
    
    where_sql = " AND ".join(filters)
    
    # Get current metrics
    current = execute_single(f"""
        SELECT 
            COUNT(*) as funded_units,
            COALESCE(SUM(loan_amount), 0) as funded_volume,
            AVG(EXTRACT(EPOCH FROM (funded_at - application_date)) / 86400) as avg_cycle_time
        FROM loans l
        WHERE {where_sql}
    """, params)
    
    # Get company benchmark
    benchmark = execute_single("""
        SELECT 
            AVG(units) as avg_units,
            AVG(volume) as avg_volume,
            AVG(cycle_time) as avg_cycle_time
        FROM (
            SELECT 
                loan_officer_id,
                COUNT(*) as units,
                SUM(loan_amount) as volume,
                AVG(EXTRACT(EPOCH FROM (funded_at - application_date)) / 86400) as cycle_time
            FROM loans
            WHERE funded_at >= CURRENT_DATE - 90
            GROUP BY loan_officer_id
        ) lo_stats
    """)
    
    def calc_diff(current_val, benchmark_val):
        if benchmark_val == 0:
            return 0
        return round(((current_val - benchmark_val) / benchmark_val) * 100, 1)
    
    data = {
        "benchmark_type": benchmark_type,
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
    branch_id: Optional[str] = None,
    include_closed: bool = False,
) -> ToolResult:
    """Get pipeline breakdown by LO."""
    params = {}
    filters = []
    
    if not include_closed:
        filters.append("l.status NOT IN ('funded', 'cancelled', 'denied')")
    if branch_id:
        filters.append("l.branch_id = :branch_id")
        params["branch_id"] = branch_id
    
    where_sql = " AND ".join(filters) if filters else "1=1"
    
    breakdown = execute_query(f"""
        SELECT 
            u.id as lo_id,
            u.name as lo_name,
            COUNT(*) as count,
            SUM(l.loan_amount) as volume,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.status_changed_at)) / 86400) as avg_days
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE {where_sql}
        GROUP BY u.id, u.name
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
    """Check TRID compliance."""
    loan = execute_single("""
        SELECT 
            l.id, l.loan_number, l.application_date, l.disclosure_sent_at,
            l.closing_disclosure_sent_at, l.consummation_date,
            l.le_revision_count, l.cd_revision_count
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})
    
    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")
    
    issues = []
    warnings = []
    
    # LE timing - must be within 3 business days of application
    if loan["application_date"] and loan["disclosure_sent_at"]:
        le_days = days_between(loan["application_date"], loan["disclosure_sent_at"])
        if le_days > 3:
            issues.append({
                "type": "LE_TIMING",
                "message": f"LE sent {le_days} days after application (max 3 business days)",
                "severity": "high",
            })
    elif loan["application_date"] and not loan["disclosure_sent_at"]:
        days_since_app = days_between(loan["application_date"], datetime.now())
        if days_since_app > 2:
            issues.append({
                "type": "LE_NOT_SENT",
                "message": f"LE not sent - {days_since_app} days since application",
                "severity": "critical",
            })
    
    # CD timing - must be 3 business days before closing
    if loan["closing_disclosure_sent_at"] and loan["consummation_date"]:
        cd_days = days_between(loan["closing_disclosure_sent_at"], loan["consummation_date"])
        if cd_days < 3:
            issues.append({
                "type": "CD_TIMING",
                "message": f"CD sent only {cd_days} days before closing (min 3 business days)",
                "severity": "critical",
            })
    
    # Revision warnings
    if loan["le_revision_count"] and loan["le_revision_count"] > 2:
        warnings.append({
            "type": "EXCESSIVE_LE_REVISIONS",
            "message": f"{loan['le_revision_count']} LE revisions - review for valid change circumstances",
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
            "le_sent": format_date(loan["disclosure_sent_at"]),
            "cd_sent": format_date(loan["closing_disclosure_sent_at"]),
            "closing_date": format_date(loan["consummation_date"]),
        },
    }
    
    return ToolResult.success(
        data=data,
        message=f"TRID {'Compliant' if is_compliant else 'NON-COMPLIANT'}: {len(issues)} issues",
    )


@mortgage_tool(
    name="check_respa_compliance",
    description="Check RESPA Section 8 compliance for kickback/fee splitting violations",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def check_respa_compliance(
    loan_id: str,
) -> ToolResult:
    """Check RESPA compliance."""
    loan = execute_single("""
        SELECT 
            l.id, l.loan_number, l.referral_source, l.referral_fee_paid,
            l.title_company_id, l.title_fee, l.appraisal_company_id, l.appraisal_fee
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})
    
    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")
    
    issues = []
    
    # Check for referral fees
    if loan["referral_fee_paid"] and float(loan["referral_fee_paid"]) > 0:
        issues.append({
            "type": "REFERRAL_FEE",
            "message": f"Referral fee of {format_currency(loan['referral_fee_paid'])} paid - verify not for referral of business",
            "severity": "high",
        })
    
    # Check affiliated business arrangements
    affiliated = execute_query("""
        SELECT provider_name, relationship_type, fee_amount
        FROM loan_service_providers
        WHERE loan_id = :loan_id AND is_affiliated = true
    """, {"loan_id": loan_id})
    
    for aff in affiliated:
        issues.append({
            "type": "AFFILIATED_BUSINESS",
            "message": f"Affiliated provider: {aff['provider_name']} - verify AfBA disclosure provided",
            "severity": "medium",
        })
    
    is_compliant = len([i for i in issues if i["severity"] == "high"]) == 0
    
    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "is_compliant": is_compliant,
        "issues": issues,
        "affiliated_providers": len(affiliated),
    }
    
    return ToolResult.success(
        data=data,
        message=f"RESPA {'Compliant' if is_compliant else 'Review Required'}: {len(issues)} items to review",
    )


@mortgage_tool(
    name="check_fair_lending",
    description="Check fair lending compliance and identify potential disparities",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def check_fair_lending(
    loan_id: Optional[str] = None,
    lo_id: Optional[str] = None,
    days: int = 90,
) -> ToolResult:
    """Check fair lending compliance."""
    if loan_id:
        loan = execute_single("""
            SELECT 
                l.id, l.loan_number, l.interest_rate, l.loan_type,
                l.borrower_credit_score, l.pricing_exception,
                l.pricing_exception_reason
            FROM loans l
            WHERE l.id = :loan_id
        """, {"loan_id": loan_id})
        
        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")
        
        # Compare to similar loans
        comparable = execute_single("""
            SELECT 
                AVG(interest_rate) as avg_rate,
                MIN(interest_rate) as min_rate,
                MAX(interest_rate) as max_rate,
                COUNT(*) as count
            FROM loans
            WHERE loan_type = :loan_type
                AND borrower_credit_score BETWEEN :min_score AND :max_score
                AND funded_at >= CURRENT_DATE - 90
        """, {
            "loan_type": loan["loan_type"],
            "min_score": (loan["borrower_credit_score"] or 700) - 20,
            "max_score": (loan["borrower_credit_score"] or 700) + 20,
        })
        
        rate_variance = 0
        if comparable["avg_rate"]:
            rate_variance = float(loan["interest_rate"] or 0) - float(comparable["avg_rate"])
        
        flags = []
        if abs(rate_variance) > 0.25:
            flags.append({
                "type": "RATE_VARIANCE",
                "message": f"Rate is {rate_variance:+.3f}% from comparable average",
                "severity": "medium" if abs(rate_variance) < 0.5 else "high",
            })
        
        if loan["pricing_exception"] and not loan["pricing_exception_reason"]:
            flags.append({
                "type": "UNDOCUMENTED_EXCEPTION",
                "message": "Pricing exception without documented reason",
                "severity": "high",
            })
        
        data = {
            "loan_id": loan_id,
            "loan_number": loan["loan_number"],
            "flags": flags,
            "rate_analysis": {
                "loan_rate": float(loan["interest_rate"] or 0),
                "comparable_avg": float(comparable["avg_rate"] or 0),
                "variance": round(rate_variance, 3),
                "comparable_count": comparable["count"],
            },
        }
    else:
        # Aggregate analysis
        analysis = execute_query("""
            SELECT 
                loan_type,
                COUNT(*) as count,
                AVG(interest_rate) as avg_rate,
                STDDEV(interest_rate) as rate_stddev,
                COUNT(CASE WHEN pricing_exception THEN 1 END) as exceptions
            FROM loans
            WHERE funded_at >= CURRENT_DATE - :days
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
                    "exception_rate": round((row["exceptions"] / row["count"]) * 100, 1) if row["count"] > 0 else 0,
                }
                for row in analysis
            ],
        }
    
    return ToolResult.success(
        data=data,
        message="Fair lending analysis complete",
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
            l.*, u.name as lo_name, u.nmls_id as lo_nmls
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
    if loan["application_date"] and loan["disclosure_sent_at"]:
        le_days = days_between(loan["application_date"], loan["disclosure_sent_at"])
        if le_days <= 3:
            audit_results["passed"].append({"check": "LE_TIMING", "message": f"LE sent in {le_days} days"})
        else:
            audit_results["failed"].append({"check": "LE_TIMING", "message": f"LE sent in {le_days} days (max 3)"})
    
    # Document checklist
    docs = execute_query("""
        SELECT document_type, status FROM loan_documents WHERE loan_id = :loan_id
    """, {"loan_id": loan_id})
    
    required_docs = ["income_verification", "asset_verification", "credit_report", "appraisal", "title"]
    for req_doc in required_docs:
        found = any(d["document_type"] == req_doc and d["status"] == "approved" for d in docs)
        if found:
            audit_results["passed"].append({"check": f"DOC_{req_doc.upper()}", "message": f"{req_doc} verified"})
        else:
            audit_results["warnings"].append({"check": f"DOC_{req_doc.upper()}", "message": f"{req_doc} not verified"})
    
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
    """Get disclosure timeline."""
    loan = execute_single("""
        SELECT 
            l.id, l.loan_number, l.application_date,
            l.disclosure_sent_at, l.disclosure_received_at,
            l.closing_disclosure_sent_at, l.closing_disclosure_received_at,
            l.consummation_date, l.le_revision_count, l.cd_revision_count
        FROM loans l
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})
    
    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")
    
    timeline = []
    
    if loan["application_date"]:
        timeline.append({"event": "Application", "date": format_date(loan["application_date"]), "status": "complete"})
    
    if loan["disclosure_sent_at"]:
        timeline.append({"event": "LE Sent", "date": format_date(loan["disclosure_sent_at"]), "status": "complete"})
    else:
        timeline.append({"event": "LE Sent", "date": None, "status": "pending"})
    
    if loan["disclosure_received_at"]:
        timeline.append({"event": "LE Received", "date": format_date(loan["disclosure_received_at"]), "status": "complete"})
    
    if loan["closing_disclosure_sent_at"]:
        timeline.append({"event": "CD Sent", "date": format_date(loan["closing_disclosure_sent_at"]), "status": "complete"})
    
    if loan["closing_disclosure_received_at"]:
        timeline.append({"event": "CD Received", "date": format_date(loan["closing_disclosure_received_at"]), "status": "complete"})
    
    if loan["consummation_date"]:
        timeline.append({"event": "Closing", "date": format_date(loan["consummation_date"]), "status": "complete"})
    
    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "timeline": timeline,
        "revisions": {
            "le_revisions": loan["le_revision_count"] or 0,
            "cd_revisions": loan["cd_revision_count"] or 0,
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
    """Check tolerance violations."""
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
    description="Get compliance history and past issues for loan or LO",
    agent_roles=["compliance_checker"],
    risk_level="LOW",
)
def get_compliance_history(
    loan_id: Optional[str] = None,
    lo_id: Optional[str] = None,
    days: int = 365,
) -> ToolResult:
    """Get compliance history."""
    params = {"days": days}
    
    if loan_id:
        history = execute_query("""
            SELECT 
                issue_type, severity, description, status,
                identified_at, resolved_at, resolution_notes
            FROM compliance_issues
            WHERE loan_id = :loan_id
            ORDER BY identified_at DESC
        """, {"loan_id": loan_id})
        
        data = {
            "loan_id": loan_id,
            "issues": [
                {
                    "type": h["issue_type"],
                    "severity": h["severity"],
                    "description": h["description"],
                    "status": h["status"],
                    "identified": format_date(h["identified_at"]),
                    "resolved": format_date(h["resolved_at"]),
                }
                for h in history
            ],
            "total_issues": len(history),
            "open_issues": len([h for h in history if h["status"] == "open"]),
        }
    else:
        # LO or aggregate history
        params["lo_id"] = lo_id
        
        summary = execute_query(f"""
            SELECT 
                issue_type,
                COUNT(*) as count,
                COUNT(CASE WHEN status = 'open' THEN 1 END) as open_count
            FROM compliance_issues ci
            JOIN loans l ON l.id = ci.loan_id
            WHERE ci.identified_at >= CURRENT_DATE - :days
            {"AND l.loan_officer_id = :lo_id" if lo_id else ""}
            GROUP BY issue_type
            ORDER BY count DESC
        """, params)
        
        data = {
            "period_days": days,
            "lo_id": lo_id,
            "by_type": [
                {
                    "type": s["issue_type"],
                    "count": s["count"],
                    "open": s["open_count"],
                }
                for s in summary
            ],
            "total_issues": sum(s["count"] for s in summary),
        }
    
    return ToolResult.success(
        data=data,
        message=f"Compliance history: {data.get('total_issues', 0)} issues found",
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
            l.status, l.source, l.campaign, l.created_at,
            l.assigned_to, l.lead_score, l.last_contact_at,
            l.property_type, l.loan_purpose, l.estimated_amount,
            l.estimated_credit_score, l.pre_approved,
            u.name as assigned_to_name
        FROM leads l
        LEFT JOIN users u ON u.id = l.assigned_to
        WHERE l.id = :lead_id
    """, {"lead_id": lead_id})
    
    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")
    
    # Get recent activities
    activities = execute_query("""
        SELECT activity_type, description, created_at
        FROM lead_activities
        WHERE lead_id = :lead_id
        ORDER BY created_at DESC
        LIMIT 5
    """, {"lead_id": lead_id})
    
    data = {
        "id": lead["id"],
        "name": f"{lead['first_name']} {lead['last_name']}",
        "email": lead["email"],
        "phone": lead["phone"],
        "status": lead["status"],
        "score": lead["lead_score"],
        "source": lead["source"],
        "campaign": lead["campaign"],
        "assigned_to": lead["assigned_to_name"],
        "created_at": format_date(lead["created_at"]),
        "last_contact": format_date(lead["last_contact_at"]),
        "loan_interest": {
            "purpose": lead["loan_purpose"],
            "property_type": lead["property_type"],
            "estimated_amount": float(lead["estimated_amount"] or 0),
            "estimated_credit": lead["estimated_credit_score"],
            "pre_approved": lead["pre_approved"],
        },
        "recent_activities": [
            {
                "type": a["activity_type"],
                "description": a["description"],
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
    description="Get complete engagement history for a lead",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def get_engagement_history(
    lead_id: str,
    limit: int = 50,
) -> ToolResult:
    """Get engagement history."""
    engagements = execute_query("""
        SELECT 
            engagement_type, channel, direction,
            subject, content_preview, outcome,
            created_at, duration_seconds
        FROM lead_engagements
        WHERE lead_id = :lead_id
        ORDER BY created_at DESC
        LIMIT :limit
    """, {"lead_id": lead_id, "limit": limit})
    
    if not engagements:
        return ToolResult.no_data(f"No engagement history for lead {lead_id}")
    
    # Aggregate stats
    by_channel = {}
    for e in engagements:
        channel = e["channel"]
        if channel not in by_channel:
            by_channel[channel] = {"count": 0, "responses": 0}
        by_channel[channel]["count"] += 1
        if e["outcome"] == "responded":
            by_channel[channel]["responses"] += 1
    
    data = {
        "lead_id": lead_id,
        "total_engagements": len(engagements),
        "by_channel": by_channel,
        "engagements": [
            {
                "type": e["engagement_type"],
                "channel": e["channel"],
                "direction": e["direction"],
                "subject": e["subject"],
                "preview": e["content_preview"][:100] if e["content_preview"] else None,
                "outcome": e["outcome"],
                "date": format_date(e["created_at"]),
            }
            for e in engagements
        ],
    }
    
    return ToolResult.success(
        data=data,
        message=f"{len(engagements)} engagements found",
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
            l.id, l.lead_score, l.estimated_credit_score,
            l.estimated_amount, l.pre_approved, l.source,
            l.created_at, l.last_contact_at
        FROM leads l
        WHERE l.id = :lead_id
    """, {"lead_id": lead_id})
    
    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")
    
    # Get engagement stats
    engagement_stats = execute_single("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN outcome = 'responded' THEN 1 END) as responses,
            COUNT(CASE WHEN engagement_type = 'email_open' THEN 1 END) as opens,
            COUNT(CASE WHEN engagement_type = 'link_click' THEN 1 END) as clicks
        FROM lead_engagements
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
    if lead["estimated_credit_score"] and lead["estimated_credit_score"] >= 700:
        score_breakdown["profile"] += 10
    if lead["estimated_amount"] and lead["estimated_amount"] >= 300000:
        score_breakdown["profile"] += 10
    if lead["pre_approved"]:
        score_breakdown["profile"] += 5
    
    # Engagement score (max 25)
    if engagement_stats["responses"] >= 2:
        score_breakdown["engagement"] += 15
    elif engagement_stats["responses"] >= 1:
        score_breakdown["engagement"] += 10
    if engagement_stats["opens"] >= 3:
        score_breakdown["engagement"] += 5
    if engagement_stats["clicks"] >= 1:
        score_breakdown["engagement"] += 5
    
    # Recency score (max 25)
    if lead["last_contact_at"]:
        days_since = days_between(lead["last_contact_at"], datetime.now())
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
        "previous_score": lead["lead_score"],
        "new_score": total_score,
        "grade": grade,
        "breakdown": score_breakdown,
        "engagement_stats": {
            "total": engagement_stats["total"],
            "responses": engagement_stats["responses"],
            "opens": engagement_stats["opens"],
            "clicks": engagement_stats["clicks"],
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
            l.id, l.first_name, l.status, l.lead_score,
            l.last_contact_at, l.preferred_contact_method,
            l.loan_purpose, l.estimated_amount
        FROM leads l
        WHERE l.id = :lead_id
    """, {"lead_id": lead_id})
    
    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")
    
    # Get last engagement
    last_engagement = execute_single("""
        SELECT engagement_type, channel, outcome, created_at
        FROM lead_engagements
        WHERE lead_id = :lead_id
        ORDER BY created_at DESC
        LIMIT 1
    """, {"lead_id": lead_id})
    
    days_since_contact = days_between(lead["last_contact_at"], datetime.now()) if lead["last_contact_at"] else 999
    
    # Determine recommendation
    suggestions = []
    
    if days_since_contact > 7:
        suggestions.append({
            "action": "call",
            "priority": "high",
            "reason": f"No contact in {days_since_contact} days",
            "script_hint": f"Check in on {lead['loan_purpose'] or 'loan'} interest",
        })
    
    if lead["lead_score"] and lead["lead_score"] >= 70:
        suggestions.append({
            "action": "schedule_meeting",
            "priority": "high",
            "reason": "High lead score indicates strong interest",
            "script_hint": "Offer consultation to discuss options",
        })
    
    if last_engagement and last_engagement["outcome"] != "responded":
        channel = "email" if last_engagement["channel"] == "phone" else "phone"
        suggestions.append({
            "action": f"try_{channel}",
            "priority": "medium",
            "reason": f"No response to last {last_engagement['channel']} attempt",
            "script_hint": f"Follow up via {channel}",
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
        "current_status": lead["status"],
        "days_since_contact": days_since_contact,
        "suggestions": suggestions,
        "preferred_channel": lead["preferred_contact_method"],
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
            l.loan_purpose, l.property_type, l.estimated_amount,
            l.source, l.campaign
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
    description="Find similar leads that converted to understand success patterns",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def get_similar_converted_leads(
    lead_id: str,
    limit: int = 5,
) -> ToolResult:
    """Find similar converted leads."""
    lead = execute_single("""
        SELECT 
            id, source, loan_purpose, property_type,
            estimated_amount, estimated_credit_score
        FROM leads
        WHERE id = :lead_id
    """, {"lead_id": lead_id})
    
    if not lead:
        return ToolResult.no_data(f"Lead {lead_id} not found")
    
    # Find similar converted leads
    similar = execute_query("""
        SELECT 
            l.id, l.first_name, l.source, l.loan_purpose,
            l.estimated_amount, l.converted_at,
            lo.loan_number, lo.loan_amount, lo.funded_at
        FROM leads l
        JOIN loans lo ON lo.lead_id = l.id
        WHERE l.status = 'converted'
            AND l.id != :lead_id
            AND (l.source = :source OR l.loan_purpose = :purpose)
        ORDER BY l.converted_at DESC
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
    avg_time_to_convert = 0
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
                "loan_amount": float(s["loan_amount"] or 0),
                "converted_date": format_date(s["converted_at"]),
            }
            for s in similar
        ],
        "patterns": {
            "common_sources": common_sources,
            "avg_loan_amount": sum(float(s["loan_amount"] or 0) for s in similar) / len(similar),
        },
    }
    
    return ToolResult.success(
        data=data,
        message=f"Found {len(similar)} similar converted leads",
    )


@mortgage_tool(
    name="get_optimal_contact_time",
    description="Determine optimal time to contact lead based on history",
    agent_roles=["lead_nurturer"],
    risk_level="LOW",
)
def get_optimal_contact_time(
    lead_id: str,
) -> ToolResult:
    """Get optimal contact time."""
    # Get engagement history
    engagements = execute_query("""
        SELECT 
            EXTRACT(DOW FROM created_at) as day_of_week,
            EXTRACT(HOUR FROM created_at) as hour,
            outcome
        FROM lead_engagements
        WHERE lead_id = :lead_id
            AND direction = 'inbound'
            AND outcome = 'responded'
    """, {"lead_id": lead_id})
    
    lead = execute_single("""
        SELECT preferred_contact_time, timezone FROM leads WHERE id = :lead_id
    """, {"lead_id": lead_id})
    
    if lead and lead["preferred_contact_time"]:
        preferred = lead["preferred_contact_time"]
    else:
        # Analyze patterns or use defaults
        if engagements:
            # Find most common response hour
            hours = [int(e["hour"]) for e in engagements]
            preferred_hour = max(set(hours), key=hours.count) if hours else 10
            preferred = f"{preferred_hour:02d}:00"
        else:
            preferred = "10:00"  # Default
    
    # Determine best days
    if engagements:
        days = [int(e["day_of_week"]) for e in engagements]
        best_days = list(set(days))[:3] if days else [1, 2, 3]  # Mon, Tue, Wed default
    else:
        best_days = [1, 2, 3, 4]  # Weekdays
    
    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    
    data = {
        "lead_id": lead_id,
        "optimal_time": preferred,
        "best_days": [day_names[d] for d in best_days],
        "timezone": lead["timezone"] if lead else "America/New_York",
        "based_on_responses": len(engagements),
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
    """Get missing documents."""
    loan = execute_single("""
        SELECT id, loan_number, loan_type, status FROM loans WHERE id = :loan_id
    """, {"loan_id": loan_id})
    
    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")
    
    # Get document requirements and status
    docs = execute_query("""
        SELECT 
            dr.document_type, dr.category, dr.is_required,
            ld.status as doc_status, ld.uploaded_at, ld.expires_at
        FROM document_requirements dr
        LEFT JOIN loan_documents ld ON ld.loan_id = :loan_id 
            AND ld.document_type = dr.document_type
        WHERE dr.loan_type = :loan_type OR dr.loan_type IS NULL
        ORDER BY dr.is_required DESC, dr.category
    """, {"loan_id": loan_id, "loan_type": loan["loan_type"]})
    
    missing = []
    pending = []
    received = []
    
    for doc in docs:
        doc_info = {
            "type": doc["document_type"],
            "category": doc["category"],
            "required": doc["is_required"],
        }
        
        if not doc["doc_status"]:
            missing.append(doc_info)
        elif doc["doc_status"] in ["pending", "requested"]:
            doc_info["status"] = doc["doc_status"]
            doc_info["requested_at"] = format_date(doc["uploaded_at"])
            pending.append(doc_info)
        else:
            doc_info["status"] = doc["doc_status"]
            received.append(doc_info)
    
    data = {
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "missing": missing,
        "pending": pending,
        "received_count": len(received),
        "missing_required": len([m for m in missing if m["required"]]),
        "total_required": len([d for d in docs if d["is_required"]]),
    }
    
    return ToolResult.success(
        data=data,
        message=f"{len(missing)} missing, {len(pending)} pending documents",
    )


@mortgage_tool(
    name="get_loan_conditions",
    description="Get outstanding conditions for a loan",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def get_loan_conditions(
    loan_id: str,
    status: Optional[str] = None,  # open, cleared, waived
) -> ToolResult:
    """Get loan conditions."""
    params = {"loan_id": loan_id}
    filters = ["lc.loan_id = :loan_id"]
    
    if status:
        filters.append("lc.status = :status")
        params["status"] = status
    
    where_sql = " AND ".join(filters)
    
    conditions = execute_query(f"""
        SELECT 
            lc.id, lc.condition_type, lc.category, lc.description,
            lc.status, lc.priority, lc.due_date,
            lc.created_at, lc.cleared_at, lc.cleared_by
        FROM loan_conditions lc
        WHERE {where_sql}
        ORDER BY lc.priority DESC, lc.due_date ASC NULLS LAST
    """, params)
    
    if not conditions:
        return ToolResult.no_data("No conditions found")
    
    open_count = len([c for c in conditions if c["status"] == "open"])
    past_due = len([c for c in conditions if c["due_date"] and c["due_date"] < date.today() and c["status"] == "open"])
    
    data = {
        "loan_id": loan_id,
        "total": len(conditions),
        "open": open_count,
        "past_due": past_due,
        "conditions": [
            {
                "id": c["id"],
                "type": c["condition_type"],
                "category": c["category"],
                "description": c["description"],
                "status": c["status"],
                "priority": c["priority"],
                "due_date": format_date(c["due_date"]),
                "is_past_due": c["due_date"] and c["due_date"] < date.today() and c["status"] == "open",
            }
            for c in conditions
        ],
    }
    
    return ToolResult.success(
        data=data,
        message=f"{open_count} open conditions ({past_due} past due)",
    )


@mortgage_tool(
    name="track_document_request",
    description="Track status of a document request",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def track_document_request(
    request_id: Optional[str] = None,
    loan_id: Optional[str] = None,
) -> ToolResult:
    """Track document request."""
    if request_id:
        request = execute_single("""
            SELECT 
                dr.id, dr.loan_id, dr.document_type, dr.status,
                dr.requested_at, dr.due_date, dr.reminder_count,
                dr.last_reminder_at, dr.received_at,
                l.loan_number, c.first_name, c.email
            FROM document_requests dr
            JOIN loans l ON l.id = dr.loan_id
            LEFT JOIN contacts c ON c.id = l.borrower_id
            WHERE dr.id = :request_id
        """, {"request_id": request_id})
        
        if not request:
            return ToolResult.no_data(f"Request {request_id} not found")
        
        data = {
            "request_id": request["id"],
            "loan_number": request["loan_number"],
            "document_type": request["document_type"],
            "status": request["status"],
            "borrower": request["first_name"],
            "borrower_email": request["email"],
            "requested_at": format_date(request["requested_at"]),
            "due_date": format_date(request["due_date"]),
            "reminder_count": request["reminder_count"] or 0,
            "last_reminder": format_date(request["last_reminder_at"]),
            "received_at": format_date(request["received_at"]),
            "days_outstanding": days_between(request["requested_at"], datetime.now()) if request["status"] == "pending" else None,
        }
    else:
        # Get all requests for loan
        requests = execute_query("""
            SELECT 
                dr.id, dr.document_type, dr.status,
                dr.requested_at, dr.due_date, dr.received_at
            FROM document_requests dr
            WHERE dr.loan_id = :loan_id
            ORDER BY dr.requested_at DESC
        """, {"loan_id": loan_id})
        
        data = {
            "loan_id": loan_id,
            "requests": [
                {
                    "id": r["id"],
                    "document_type": r["document_type"],
                    "status": r["status"],
                    "requested": format_date(r["requested_at"]),
                    "due": format_date(r["due_date"]),
                    "received": format_date(r["received_at"]),
                }
                for r in requests
            ],
            "pending_count": len([r for r in requests if r["status"] == "pending"]),
        }
    
    return ToolResult.success(
        data=data,
        message="Document request status retrieved",
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
    """Send document reminder."""
    loan = execute_single("""
        SELECT 
            l.id, l.loan_number,
            c.first_name, c.email, c.phone
        FROM loans l
        JOIN contacts c ON c.id = l.borrower_id
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})
    
    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")
    
    # Get missing documents
    if document_types:
        missing = document_types
    else:
        missing_docs = execute_query("""
            SELECT document_type FROM document_requests
            WHERE loan_id = :loan_id AND status = 'pending'
        """, {"loan_id": loan_id})
        missing = [d["document_type"] for d in missing_docs]
    
    if not missing:
        return ToolResult.no_data("No pending documents to remind about")
    
    import uuid
    reminder_id = str(uuid.uuid4())[:8].upper()
    
    data = {
        "reminder_id": reminder_id,
        "loan_id": loan_id,
        "loan_number": loan["loan_number"],
        "borrower": loan["first_name"],
        "documents": missing,
        "channel": channel,
        "sent_to": {
            "email": loan["email"] if channel in ["email", "both"] else None,
            "phone": loan["phone"] if channel in ["sms", "both"] else None,
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
    """Escalate document issue."""
    loan = execute_single("""
        SELECT 
            l.id, l.loan_number, l.loan_officer_id,
            u.name as lo_name, u.manager_id,
            m.name as manager_name
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        LEFT JOIN users m ON m.id = u.manager_id
        WHERE l.id = :loan_id
    """, {"loan_id": loan_id})
    
    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")
    
    import uuid
    escalation_id = str(uuid.uuid4())[:8].upper()
    
    escalate_to_user = escalate_to or loan["manager_id"]
    escalate_to_name = loan["manager_name"] if not escalate_to else escalate_to
    
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
    """Get document timeline."""
    docs = execute_query("""
        SELECT 
            ld.document_type, ld.category, ld.status,
            ld.requested_at, ld.uploaded_at, ld.approved_at,
            ld.approved_by
        FROM loan_documents ld
        WHERE ld.loan_id = :loan_id
        ORDER BY ld.uploaded_at DESC NULLS LAST
    """, {"loan_id": loan_id})
    
    if not docs:
        return ToolResult.no_data(f"No documents for loan {loan_id}")
    
    # Build timeline
    timeline = []
    for doc in docs:
        events = []
        if doc["requested_at"]:
            events.append({"event": "requested", "date": doc["requested_at"]})
        if doc["uploaded_at"]:
            events.append({"event": "uploaded", "date": doc["uploaded_at"]})
        if doc["approved_at"]:
            events.append({"event": "approved", "date": doc["approved_at"]})
        
        timeline.append({
            "document_type": doc["document_type"],
            "category": doc["category"],
            "current_status": doc["status"],
            "events": [{"event": e["event"], "date": format_date(e["date"])} for e in events],
        })
    
    # Calculate average processing time
    processing_times = []
    for doc in docs:
        if doc["uploaded_at"] and doc["approved_at"]:
            processing_times.append(days_between(doc["uploaded_at"], doc["approved_at"]))
    
    avg_processing = sum(processing_times) / len(processing_times) if processing_times else 0
    
    data = {
        "loan_id": loan_id,
        "total_documents": len(docs),
        "approved": len([d for d in docs if d["status"] == "approved"]),
        "pending": len([d for d in docs if d["status"] == "pending"]),
        "avg_processing_days": round(avg_processing, 1),
        "timeline": timeline,
    }
    
    return ToolResult.success(
        data=data,
        message=f"{data['approved']}/{data['total_documents']} documents approved",
    )


@mortgage_tool(
    name="check_document_expiration",
    description="Check for expiring or expired documents",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def check_document_expiration(
    loan_id: Optional[str] = None,
    days_ahead: int = 30,
) -> ToolResult:
    """Check document expiration."""
    params = {"days_ahead": days_ahead}
    
    if loan_id:
        params["loan_id"] = loan_id
        loan_filter = "ld.loan_id = :loan_id AND"
    else:
        loan_filter = ""
    
    expiring = execute_query(f"""
        SELECT 
            ld.id, ld.loan_id, ld.document_type,
            ld.expires_at, l.loan_number,
            c.first_name as borrower
        FROM loan_documents ld
        JOIN loans l ON l.id = ld.loan_id
        LEFT JOIN contacts c ON c.id = l.borrower_id
        WHERE {loan_filter}
            ld.status = 'approved'
            AND ld.expires_at IS NOT NULL
            AND ld.expires_at <= CURRENT_DATE + :days_ahead
            AND l.status NOT IN ('funded', 'cancelled', 'denied')
        ORDER BY ld.expires_at ASC
    """, params)
    
    if not expiring:
        return ToolResult.no_data("No expiring documents found")
    
    expired = []
    expiring_soon = []
    
    today = date.today()
    for doc in expiring:
        doc_info = {
            "id": doc["id"],
            "loan_id": doc["loan_id"],
            "loan_number": doc["loan_number"],
            "document_type": doc["document_type"],
            "expires_at": format_date(doc["expires_at"]),
            "borrower": doc["borrower"],
        }
        
        if doc["expires_at"] < today:
            doc_info["days_expired"] = days_between(doc["expires_at"], today)
            expired.append(doc_info)
        else:
            doc_info["days_until_expiry"] = days_between(today, doc["expires_at"])
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
    description="Get status of third-party orders (appraisal, title, etc.)",
    agent_roles=["document_tracker"],
    risk_level="LOW",
)
def get_third_party_status(
    loan_id: str,
) -> ToolResult:
    """Get third-party order status."""
    orders = execute_query("""
        SELECT 
            tpo.id, tpo.order_type, tpo.vendor_name,
            tpo.status, tpo.ordered_at, tpo.due_date,
            tpo.received_at, tpo.amount
        FROM third_party_orders tpo
        WHERE tpo.loan_id = :loan_id
        ORDER BY tpo.ordered_at DESC
    """, {"loan_id": loan_id})
    
    if not orders:
        return ToolResult.no_data(f"No third-party orders for loan {loan_id}")
    
    pending = [o for o in orders if o["status"] in ["ordered", "in_progress"]]
    completed = [o for o in orders if o["status"] == "completed"]
    
    data = {
        "loan_id": loan_id,
        "total_orders": len(orders),
        "pending_count": len(pending),
        "completed_count": len(completed),
        "orders": [
            {
                "id": o["id"],
                "type": o["order_type"],
                "vendor": o["vendor_name"],
                "status": o["status"],
                "ordered": format_date(o["ordered_at"]),
                "due": format_date(o["due_date"]),
                "received": format_date(o["received_at"]),
                "amount": float(o["amount"] or 0),
                "is_overdue": o["due_date"] and o["due_date"] < date.today() and o["status"] != "completed",
            }
            for o in orders
        ],
    }
    
    return ToolResult.success(
        data=data,
        message=f"{len(pending)} pending, {len(completed)} completed orders",
    )


# =============================================================================
# END OF PART 1
# =============================================================================

print(f"Part 1 loaded: {len(tool_registry)} tools registered")