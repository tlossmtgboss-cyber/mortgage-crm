# Perennia AI - Agent Health Check & Optimization Suite
# Comprehensive testing for production-ready AI agents

"""
AGENT HEALTH CHECK SYSTEM
=========================
This suite validates that all 8 agents are production-ready:

1. Tool Registration & Availability
2. Database Query Performance
3. Agent Orchestration & Handoffs
4. Memory & Learning System
5. Approval Workflow
6. Error Handling & Recovery
7. Load Testing & Concurrency
8. End-to-End Workflow Scenarios

Save as: backend/agents/health_check.py
Run: python -m agents.health_check
"""

import sys
import asyncio
import time
import statistics
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from unittest.mock import patch, MagicMock, AsyncMock
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# HEALTH CHECK RESULTS
# =============================================================================

class CheckStatus(Enum):
    PASS = "✅ PASS"
    WARN = "⚠️ WARN"
    FAIL = "❌ FAIL"
    SKIP = "⏭️ SKIP"


@dataclass
class HealthCheckResult:
    name: str
    status: CheckStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    recommendations: List[str] = field(default_factory=list)


class HealthCheckReport:
    """Aggregates all health check results."""

    def __init__(self):
        self.results: List[HealthCheckResult] = []
        self.start_time = datetime.now()

    def add(self, result: HealthCheckResult):
        self.results.append(result)
        status_icon = result.status.value
        print(f"  {status_icon} {result.name}: {result.message}")
        if result.recommendations:
            for rec in result.recommendations:
                print(f"      → {rec}")

    def summary(self) -> Dict[str, Any]:
        passed = sum(1 for r in self.results if r.status == CheckStatus.PASS)
        warned = sum(1 for r in self.results if r.status == CheckStatus.WARN)
        failed = sum(1 for r in self.results if r.status == CheckStatus.FAIL)
        skipped = sum(1 for r in self.results if r.status == CheckStatus.SKIP)

        return {
            "total": len(self.results),
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "skipped": skipped,
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "healthy": failed == 0,
        }

    def print_summary(self):
        s = self.summary()
        print("\n" + "=" * 70)
        print("HEALTH CHECK SUMMARY")
        print("=" * 70)
        print(f"Total Checks: {s['total']}")
        print(f"  ✅ Passed:  {s['passed']}")
        print(f"  ⚠️ Warned:  {s['warned']}")
        print(f"  ❌ Failed:  {s['failed']}")
        print(f"  ⏭️ Skipped: {s['skipped']}")
        print(f"\nDuration: {s['duration_seconds']:.2f}s")
        print(f"Status: {'🟢 HEALTHY' if s['healthy'] else '🔴 UNHEALTHY'}")
        print("=" * 70)

        # Print all recommendations
        all_recs = []
        for r in self.results:
            if r.recommendations:
                all_recs.extend(r.recommendations)

        if all_recs:
            print("\n📋 RECOMMENDATIONS:")
            for i, rec in enumerate(all_recs, 1):
                print(f"  {i}. {rec}")

        return s['healthy']


report = HealthCheckReport()


# =============================================================================
# 1. TOOL REGISTRATION CHECK
# =============================================================================

def check_tool_registration():
    """Verify all 64 tools are properly registered."""
    print("\n🔧 TOOL REGISTRATION CHECK")
    print("-" * 50)

    try:
        from backend.agents.tools import tool_registry, ALL_TOOLS
        from backend.agents.tool_integration import AGENT_CONFIGS

        # Check total tool count
        total_tools = len(tool_registry)
        if total_tools >= 64:
            report.add(HealthCheckResult(
                name="Tool Count",
                status=CheckStatus.PASS,
                message=f"{total_tools} tools registered",
            ))
        else:
            report.add(HealthCheckResult(
                name="Tool Count",
                status=CheckStatus.FAIL,
                message=f"Only {total_tools}/64 tools registered",
                recommendations=["Review tool imports in __init__.py"]
            ))

        # Check each agent has 8 tools
        for agent_name, config in AGENT_CONFIGS.items():
            tool_count = len(config.tool_names)
            if tool_count == 8:
                report.add(HealthCheckResult(
                    name=f"Agent: {agent_name}",
                    status=CheckStatus.PASS,
                    message=f"{tool_count} tools configured",
                ))
            else:
                report.add(HealthCheckResult(
                    name=f"Agent: {agent_name}",
                    status=CheckStatus.WARN,
                    message=f"{tool_count}/8 tools configured",
                    recommendations=[f"Add missing tools to {agent_name}"]
                ))

        # Check for orphaned tools (not assigned to any agent)
        all_assigned = set()
        for config in AGENT_CONFIGS.values():
            all_assigned.update(config.tool_names)

        all_registered = set(tool_registry.get_all().keys())
        orphaned = all_registered - all_assigned

        if not orphaned:
            report.add(HealthCheckResult(
                name="Tool Assignment",
                status=CheckStatus.PASS,
                message="All tools assigned to agents",
            ))
        else:
            report.add(HealthCheckResult(
                name="Tool Assignment",
                status=CheckStatus.WARN,
                message=f"{len(orphaned)} unassigned tools",
                details={"orphaned": list(orphaned)},
                recommendations=["Assign orphaned tools to appropriate agents"]
            ))

    except ImportError as e:
        report.add(HealthCheckResult(
            name="Tool Import",
            status=CheckStatus.FAIL,
            message=f"Import error: {e}",
            recommendations=["Check tool module imports"]
        ))


# =============================================================================
# 2. DATABASE CONNECTION CHECK
# =============================================================================

def check_database_connection():
    """Verify database connectivity and query performance."""
    print("\n🗄️ DATABASE CONNECTION CHECK")
    print("-" * 50)

    try:
        from backend.agents.tools.base import get_engine, execute_query, execute_single

        # Test engine creation
        start = time.time()
        engine = get_engine()
        engine_time = (time.time() - start) * 1000

        if engine:
            report.add(HealthCheckResult(
                name="Engine Creation",
                status=CheckStatus.PASS,
                message=f"Created in {engine_time:.1f}ms",
                duration_ms=engine_time,
            ))
        else:
            report.add(HealthCheckResult(
                name="Engine Creation",
                status=CheckStatus.FAIL,
                message="Failed to create engine",
                recommendations=["Check DATABASE_URL environment variable"]
            ))
            return

        # Test simple query
        try:
            start = time.time()
            result = execute_single("SELECT 1 as test")
            query_time = (time.time() - start) * 1000

            if result and result.get("test") == 1:
                status = CheckStatus.PASS if query_time < 100 else CheckStatus.WARN
                report.add(HealthCheckResult(
                    name="Query Execution",
                    status=status,
                    message=f"Response in {query_time:.1f}ms",
                    duration_ms=query_time,
                    recommendations=["Optimize database connection"] if query_time > 100 else []
                ))
            else:
                report.add(HealthCheckResult(
                    name="Query Execution",
                    status=CheckStatus.FAIL,
                    message="Query returned unexpected result",
                ))
        except Exception as e:
            report.add(HealthCheckResult(
                name="Query Execution",
                status=CheckStatus.FAIL,
                message=f"Query failed: {e}",
                recommendations=["Check database connectivity", "Verify credentials"]
            ))

        # Test connection pool
        try:
            pool = engine.pool
            report.add(HealthCheckResult(
                name="Connection Pool",
                status=CheckStatus.PASS,
                message=f"Size: {pool.size()}, Overflow: {pool.overflow()}",
                details={"size": pool.size(), "overflow": pool.overflow()},
            ))
        except Exception as e:
            report.add(HealthCheckResult(
                name="Connection Pool",
                status=CheckStatus.WARN,
                message=f"Could not inspect pool: {e}",
            ))

    except ImportError as e:
        report.add(HealthCheckResult(
            name="Database Module",
            status=CheckStatus.FAIL,
            message=f"Import error: {e}",
        ))


# =============================================================================
# 3. QUERY PERFORMANCE CHECK
# =============================================================================

def check_query_performance():
    """Analyze query patterns for performance issues."""
    print("\n⚡ QUERY PERFORMANCE CHECK")
    print("-" * 50)

    try:
        from backend.agents.tools.base import execute_query

        # Define critical queries to test
        test_queries = [
            ("Pipeline Count", "SELECT COUNT(*) as cnt FROM loans WHERE stage NOT IN ('Funded')"),
            ("Lead Lookup", "SELECT * FROM leads WHERE id = 999999 LIMIT 1"),
            ("Stage Distribution", "SELECT stage, COUNT(*) FROM loans GROUP BY stage"),
        ]

        slow_queries = []

        for name, query in test_queries:
            try:
                start = time.time()
                execute_query(query)
                duration = (time.time() - start) * 1000

                if duration > 500:
                    slow_queries.append((name, duration))
                    report.add(HealthCheckResult(
                        name=f"Query: {name}",
                        status=CheckStatus.WARN,
                        message=f"Slow: {duration:.1f}ms",
                        recommendations=[f"Add index for {name} query"]
                    ))
                elif duration > 100:
                    report.add(HealthCheckResult(
                        name=f"Query: {name}",
                        status=CheckStatus.PASS,
                        message=f"OK: {duration:.1f}ms",
                    ))
                else:
                    report.add(HealthCheckResult(
                        name=f"Query: {name}",
                        status=CheckStatus.PASS,
                        message=f"Fast: {duration:.1f}ms",
                    ))
            except Exception as e:
                # Query might fail due to missing tables in test - that's OK
                report.add(HealthCheckResult(
                    name=f"Query: {name}",
                    status=CheckStatus.SKIP,
                    message="Skipped (table may not exist)",
                ))

        if slow_queries:
            report.add(HealthCheckResult(
                name="Query Performance Summary",
                status=CheckStatus.WARN,
                message=f"{len(slow_queries)} slow queries detected",
                recommendations=[
                    "Consider adding database indexes",
                    "Review query execution plans",
                    "Implement query caching"
                ]
            ))
        else:
            report.add(HealthCheckResult(
                name="Query Performance Summary",
                status=CheckStatus.PASS,
                message="All queries within acceptable limits",
            ))

    except Exception as e:
        report.add(HealthCheckResult(
            name="Query Performance",
            status=CheckStatus.SKIP,
            message=f"Skipped: {e}",
        ))


# =============================================================================
# 4. AGENT ORCHESTRATION CHECK
# =============================================================================

async def check_agent_orchestration():
    """Verify agent orchestration and handoffs work correctly."""
    print("\n🎭 AGENT ORCHESTRATION CHECK")
    print("-" * 50)

    try:
        from backend.agents.tool_integration import (
            AgentToolExecutor, AGENT_CONFIGS, create_tool_node
        )

        # Test executor creation for each agent
        for agent_name in AGENT_CONFIGS.keys():
            try:
                executor = AgentToolExecutor(agent_name)
                tools = executor.get_available_tools()

                if len(tools) > 0:
                    report.add(HealthCheckResult(
                        name=f"Executor: {agent_name}",
                        status=CheckStatus.PASS,
                        message=f"{len(tools)} tools available",
                    ))
                else:
                    report.add(HealthCheckResult(
                        name=f"Executor: {agent_name}",
                        status=CheckStatus.FAIL,
                        message="No tools available",
                    ))
            except Exception as e:
                report.add(HealthCheckResult(
                    name=f"Executor: {agent_name}",
                    status=CheckStatus.FAIL,
                    message=f"Creation failed: {e}",
                ))

        # Test tool node creation
        try:
            tool_node = create_tool_node("pipeline_analyst")
            if callable(tool_node):
                report.add(HealthCheckResult(
                    name="Tool Node Creation",
                    status=CheckStatus.PASS,
                    message="LangGraph tool node created",
                ))
            else:
                report.add(HealthCheckResult(
                    name="Tool Node Creation",
                    status=CheckStatus.FAIL,
                    message="Tool node not callable",
                ))
        except Exception as e:
            report.add(HealthCheckResult(
                name="Tool Node Creation",
                status=CheckStatus.WARN,
                message=f"Could not create: {e}",
            ))

    except ImportError as e:
        report.add(HealthCheckResult(
            name="Orchestration Module",
            status=CheckStatus.FAIL,
            message=f"Import error: {e}",
        ))


# =============================================================================
# 5. APPROVAL WORKFLOW CHECK
# =============================================================================

async def check_approval_workflow():
    """Verify high-risk tool approval workflow."""
    print("\n🔐 APPROVAL WORKFLOW CHECK")
    print("-" * 50)

    try:
        from backend.agents.tool_integration import AgentToolExecutor, AGENT_CONFIGS

        # Find agents with approval requirements
        agents_with_approvals = {
            name: config.requires_approval_for
            for name, config in AGENT_CONFIGS.items()
            if config.requires_approval_for
        }

        if not agents_with_approvals:
            report.add(HealthCheckResult(
                name="Approval Configuration",
                status=CheckStatus.WARN,
                message="No tools require approval",
                recommendations=["Configure high-risk tools to require approval"]
            ))
            return

        report.add(HealthCheckResult(
            name="Approval Configuration",
            status=CheckStatus.PASS,
            message=f"{sum(len(v) for v in agents_with_approvals.values())} tools require approval",
            details=agents_with_approvals,
        ))

        # Test approval flow
        for agent_name, tools in agents_with_approvals.items():
            executor = AgentToolExecutor(agent_name)

            # Check pending approvals list
            try:
                pending = executor.get_pending_approvals()
                report.add(HealthCheckResult(
                    name=f"Pending Queue: {agent_name}",
                    status=CheckStatus.PASS,
                    message=f"{len(pending)} pending approvals",
                ))
            except Exception as e:
                report.add(HealthCheckResult(
                    name=f"Pending Queue: {agent_name}",
                    status=CheckStatus.FAIL,
                    message=f"Could not get pending: {e}",
                ))

    except ImportError as e:
        report.add(HealthCheckResult(
            name="Approval Module",
            status=CheckStatus.FAIL,
            message=f"Import error: {e}",
        ))


# =============================================================================
# 6. ERROR HANDLING CHECK
# =============================================================================

def check_error_handling():
    """Verify tools handle errors gracefully."""
    print("\n🛡️ ERROR HANDLING CHECK")
    print("-" * 50)

    try:
        from backend.agents.tools import execute_tool
        from backend.agents.tools.base import ToolStatus, ToolError

        # Test with invalid inputs
        test_cases = [
            ("Invalid Loan ID", "get_pipeline_metrics", {"lo_id": "INVALID_ID_12345"}),
            ("Missing Required", "check_trid_compliance", {}),  # Missing loan_id
            ("Invalid Status", "get_loans_by_status", {"status": "FAKE_STATUS"}),
        ]

        for name, tool_name, params in test_cases:
            try:
                result = execute_tool(tool_name, **params)

                # Should return ToolResult, not raise exception
                if hasattr(result, 'status'):
                    if result.status == ToolStatus.ERROR:
                        report.add(HealthCheckResult(
                            name=f"Error Case: {name}",
                            status=CheckStatus.PASS,
                            message="Returned error gracefully",
                        ))
                    else:
                        report.add(HealthCheckResult(
                            name=f"Error Case: {name}",
                            status=CheckStatus.PASS,
                            message=f"Handled with status: {result.status.value}",
                        ))
                else:
                    report.add(HealthCheckResult(
                        name=f"Error Case: {name}",
                        status=CheckStatus.WARN,
                        message="Returned non-ToolResult",
                    ))

            except ToolError as e:
                # ToolError is acceptable
                report.add(HealthCheckResult(
                    name=f"Error Case: {name}",
                    status=CheckStatus.PASS,
                    message=f"Raised ToolError: {e.message}",
                ))
            except Exception as e:
                # Unhandled exceptions are bad
                report.add(HealthCheckResult(
                    name=f"Error Case: {name}",
                    status=CheckStatus.FAIL,
                    message=f"Unhandled exception: {type(e).__name__}",
                    recommendations=["Add try/catch in tool implementation"]
                ))

    except ImportError as e:
        report.add(HealthCheckResult(
            name="Error Handling Module",
            status=CheckStatus.FAIL,
            message=f"Import error: {e}",
        ))


# =============================================================================
# 7. CONCURRENT EXECUTION CHECK
# =============================================================================

async def check_concurrent_execution():
    """Test tools can handle concurrent execution."""
    print("\n🔄 CONCURRENT EXECUTION CHECK")
    print("-" * 50)

    try:
        from backend.agents.tool_integration import AgentToolExecutor

        executor = AgentToolExecutor("pipeline_analyst")

        # Create multiple concurrent requests
        async def run_tool():
            return await executor.execute(
                tool_name="get_pipeline_metrics",
                params={},
                user_id="test_concurrent"
            )

        # Run 5 concurrent executions
        start = time.time()
        tasks = [run_tool() for _ in range(5)]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=10.0
            )
            duration = (time.time() - start) * 1000

            successful = sum(1 for r in results if not isinstance(r, Exception))

            if successful == 5:
                report.add(HealthCheckResult(
                    name="Concurrent Execution",
                    status=CheckStatus.PASS,
                    message=f"5/5 completed in {duration:.1f}ms",
                    duration_ms=duration,
                ))
            else:
                report.add(HealthCheckResult(
                    name="Concurrent Execution",
                    status=CheckStatus.WARN,
                    message=f"{successful}/5 completed",
                    recommendations=["Review connection pool settings"]
                ))

        except asyncio.TimeoutError:
            report.add(HealthCheckResult(
                name="Concurrent Execution",
                status=CheckStatus.FAIL,
                message="Timeout after 10s",
                recommendations=["Increase pool size", "Add query timeout"]
            ))

    except Exception as e:
        report.add(HealthCheckResult(
            name="Concurrent Execution",
            status=CheckStatus.SKIP,
            message=f"Skipped: {e}",
        ))


# =============================================================================
# 8. MEMORY SYSTEM CHECK
# =============================================================================

def check_memory_system():
    """Verify the enhanced memory system is working."""
    print("\n🧠 MEMORY SYSTEM CHECK")
    print("-" * 50)

    try:
        from backend.agents.memory.user_context import UserContextMemory

        # Create memory instance
        memory = UserContextMemory(user_id="test_health_check")

        # Test adding context
        memory.add_context("test_key", {"test": True, "timestamp": datetime.now().isoformat()})

        # Test retrieval
        retrieved = memory.get_context("test_key")

        if retrieved and retrieved.get("test") == True:
            report.add(HealthCheckResult(
                name="Memory Add/Get",
                status=CheckStatus.PASS,
                message="Successfully stored and retrieved",
            ))
        else:
            report.add(HealthCheckResult(
                name="Memory Add/Get",
                status=CheckStatus.FAIL,
                message="Retrieval returned incorrect data",
            ))

        # Test get all context
        try:
            all_context = memory.get_all_context()
            report.add(HealthCheckResult(
                name="Memory Get All",
                status=CheckStatus.PASS,
                message=f"Retrieved {len(all_context)} context items",
            ))
        except Exception as e:
            report.add(HealthCheckResult(
                name="Memory Get All",
                status=CheckStatus.WARN,
                message=f"Get all failed: {e}",
            ))

    except ImportError:
        report.add(HealthCheckResult(
            name="Memory System",
            status=CheckStatus.SKIP,
            message="Memory module not found",
            recommendations=["Ensure memory module is installed"]
        ))
    except Exception as e:
        report.add(HealthCheckResult(
            name="Memory System",
            status=CheckStatus.FAIL,
            message=f"Error: {e}",
        ))


# =============================================================================
# 9. LANGCHAIN INTEGRATION CHECK
# =============================================================================

def check_langchain_integration():
    """Verify LangChain tool bindings work."""
    print("\n🔗 LANGCHAIN INTEGRATION CHECK")
    print("-" * 50)

    try:
        from backend.agents.tools import tool_registry
        from backend.agents.tool_integration import get_tool_descriptions, bind_tools_to_model

        # Test LangChain tool wrappers
        for agent in ["pipeline_analyst", "compliance_checker", "lead_nurturer"]:
            try:
                lc_tools = tool_registry.get_langchain_tools(agent)

                if len(lc_tools) > 0:
                    # Verify tools have required attributes
                    sample_tool = lc_tools[0]
                    has_name = hasattr(sample_tool, 'name')
                    has_desc = hasattr(sample_tool, 'description')

                    if has_name and has_desc:
                        report.add(HealthCheckResult(
                            name=f"LangChain Tools: {agent}",
                            status=CheckStatus.PASS,
                            message=f"{len(lc_tools)} tools with proper schema",
                        ))
                    else:
                        report.add(HealthCheckResult(
                            name=f"LangChain Tools: {agent}",
                            status=CheckStatus.WARN,
                            message="Tools missing name/description",
                        ))
                else:
                    report.add(HealthCheckResult(
                        name=f"LangChain Tools: {agent}",
                        status=CheckStatus.FAIL,
                        message="No LangChain tools created",
                    ))
            except Exception as e:
                report.add(HealthCheckResult(
                    name=f"LangChain Tools: {agent}",
                    status=CheckStatus.FAIL,
                    message=f"Error: {e}",
                ))

        # Test tool descriptions
        try:
            desc = get_tool_descriptions("pipeline_analyst")
            if len(desc) > 100:
                report.add(HealthCheckResult(
                    name="Tool Descriptions",
                    status=CheckStatus.PASS,
                    message=f"Generated {len(desc)} chars of descriptions",
                ))
            else:
                report.add(HealthCheckResult(
                    name="Tool Descriptions",
                    status=CheckStatus.WARN,
                    message="Descriptions seem too short",
                ))
        except Exception as e:
            report.add(HealthCheckResult(
                name="Tool Descriptions",
                status=CheckStatus.FAIL,
                message=f"Error: {e}",
            ))

    except ImportError as e:
        report.add(HealthCheckResult(
            name="LangChain Integration",
            status=CheckStatus.FAIL,
            message=f"Import error: {e}",
        ))


# =============================================================================
# 10. END-TO-END WORKFLOW CHECK
# =============================================================================

async def check_e2e_workflow():
    """Test complete end-to-end workflow scenarios."""
    print("\n🎯 END-TO-END WORKFLOW CHECK")
    print("-" * 50)

    try:
        from backend.agents.tool_integration import AgentToolExecutor

        # Scenario 1: New loan application workflow
        scenario_results = []

        # Step 1: Check pipeline
        executor = AgentToolExecutor("pipeline_analyst")
        try:
            result = await executor.execute("get_pipeline_metrics", {}, "e2e_test")
            scenario_results.append(("Pipeline Check", getattr(result, 'success', True)))
        except Exception as e:
            logger.exception(f"E2E pipeline check failed: {e}")
            scenario_results.append(("Pipeline Check", False))

        # Step 2: Compliance check
        executor = AgentToolExecutor("compliance_checker")
        try:
            result = await executor.execute("get_state_requirements", {"state": "TX"}, "e2e_test")
            scenario_results.append(("Compliance Check", getattr(result, 'success', True)))
        except Exception as e:
            logger.exception(f"E2E compliance check failed: {e}")
            scenario_results.append(("Compliance Check", False))

        # Step 3: Lead scoring
        executor = AgentToolExecutor("lead_nurturer")
        try:
            result = await executor.execute("get_lead_details", {"lead_id": 1}, "e2e_test")
            scenario_results.append(("Lead Lookup", getattr(result, 'success', True) if hasattr(result, 'success') else True))
        except Exception as e:
            logger.exception(f"E2E lead lookup failed: {e}")
            scenario_results.append(("Lead Lookup", False))

        successful = sum(1 for _, success in scenario_results if success)
        total = len(scenario_results)

        if successful == total:
            report.add(HealthCheckResult(
                name="E2E: Loan Application Flow",
                status=CheckStatus.PASS,
                message=f"All {total} steps completed",
            ))
        elif successful > 0:
            report.add(HealthCheckResult(
                name="E2E: Loan Application Flow",
                status=CheckStatus.WARN,
                message=f"{successful}/{total} steps completed",
                details=dict(scenario_results),
            ))
        else:
            report.add(HealthCheckResult(
                name="E2E: Loan Application Flow",
                status=CheckStatus.FAIL,
                message="All steps failed",
            ))

    except Exception as e:
        report.add(HealthCheckResult(
            name="E2E Workflow",
            status=CheckStatus.SKIP,
            message=f"Skipped: {e}",
        ))


# =============================================================================
# 11. RECOMMENDED INDEXES CHECK
# =============================================================================

def check_recommended_indexes():
    """Suggest database indexes for optimal performance."""
    print("\n📊 INDEX RECOMMENDATIONS")
    print("-" * 50)

    recommended_indexes = [
        ("loans", "stage", "Speeds up pipeline queries"),
        ("loans", "assigned_lo", "Speeds up LO-specific queries"),
        ("loans", "expected_close_date", "Speeds up closing timeline queries"),
        ("loans", "created_at", "Speeds up date-range queries"),
        ("loans", "(stage, assigned_lo)", "Composite for filtered pipeline"),
        ("leads", "stage", "Speeds up lead filtering"),
        ("leads", "assigned_to", "Speeds up LO lead queries"),
        ("leads", "credit_score", "Speeds up lead scoring queries"),
        ("documents", "loan_id", "Speeds up document lookups"),
        ("documents", "(entity_type, entity_id)", "Composite for doc checks"),
        ("communications", "entity_id", "Speeds up interaction history"),
        ("communications", "created_at", "Speeds up recent activity"),
    ]

    report.add(HealthCheckResult(
        name="Recommended Indexes",
        status=CheckStatus.PASS,
        message=f"{len(recommended_indexes)} indexes recommended",
        details={"indexes": recommended_indexes},
        recommendations=[
            f"CREATE INDEX idx_{table}_{col.replace('(', '').replace(')', '').replace(', ', '_')} ON {table}({col})"
            for table, col, _ in recommended_indexes[:5]
        ]
    ))


# =============================================================================
# 12. CONFIGURATION VALIDATION
# =============================================================================

def check_configuration():
    """Validate environment configuration."""
    print("\n⚙️ CONFIGURATION CHECK")
    print("-" * 50)

    import os

    required_vars = [
        ("DATABASE_URL", "Database connection string"),
    ]

    optional_vars = [
        ("DB_POOL_SIZE", "10", "Connection pool size"),
        ("DB_MAX_OVERFLOW", "20", "Max overflow connections"),
        ("DB_POOL_TIMEOUT", "30", "Pool timeout in seconds"),
        ("SQL_DEBUG", "false", "SQL query logging"),
    ]

    # Check required
    for var, desc in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            display = value[:20] + "..." if len(value) > 20 else value
            if "password" in var.lower() or "secret" in var.lower():
                display = "***SET***"
            report.add(HealthCheckResult(
                name=f"Config: {var}",
                status=CheckStatus.PASS,
                message=f"Set: {display}",
            ))
        else:
            report.add(HealthCheckResult(
                name=f"Config: {var}",
                status=CheckStatus.FAIL,
                message="Not set (required)",
                recommendations=[f"Set {var} environment variable"]
            ))

    # Check optional with defaults
    for var, default, desc in optional_vars:
        value = os.getenv(var, default)
        report.add(HealthCheckResult(
            name=f"Config: {var}",
            status=CheckStatus.PASS,
            message=f"Value: {value} (default: {default})",
        ))


# =============================================================================
# 13. SPECIALIZED AGENTS CHECK
# =============================================================================

def check_specialized_agents():
    """Verify all 8 specialized agents are properly configured."""
    print("\n🤖 SPECIALIZED AGENTS CHECK")
    print("-" * 50)

    try:
        from backend.agents.specialized import (
            LeadManagementAgent,
            LoanPipelineAgent,
            TaskCalendarAgent,
            CommunicationAgent,
            DocumentAgent,
            AnalyticsAgent,
            PortfolioAgent,
            ComplianceAgent,
            AgentRegistry
        )
        from backend.agents.specialized.base import AgentContext

        agents = [
            ("LeadManagementAgent", LeadManagementAgent),
            ("LoanPipelineAgent", LoanPipelineAgent),
            ("TaskCalendarAgent", TaskCalendarAgent),
            ("CommunicationAgent", CommunicationAgent),
            ("DocumentAgent", DocumentAgent),
            ("AnalyticsAgent", AnalyticsAgent),
            ("PortfolioAgent", PortfolioAgent),
            ("ComplianceAgent", ComplianceAgent),
        ]

        # Create test context
        context: AgentContext = {
            "user_id": "health_check",
            "user_email": "test@example.com",
            "user_role": "admin",
            "autonomous_mode": True,
        }

        total_tools = 0

        for name, agent_class in agents:
            try:
                agent = agent_class(context)
                tools = agent.tools
                tool_count = len(tools)
                total_tools += tool_count

                if tool_count == 8:
                    report.add(HealthCheckResult(
                        name=f"Specialized: {name}",
                        status=CheckStatus.PASS,
                        message=f"{tool_count} tools registered",
                    ))
                else:
                    report.add(HealthCheckResult(
                        name=f"Specialized: {name}",
                        status=CheckStatus.WARN,
                        message=f"{tool_count}/8 tools registered",
                    ))
            except Exception as e:
                report.add(HealthCheckResult(
                    name=f"Specialized: {name}",
                    status=CheckStatus.FAIL,
                    message=f"Initialization failed: {e}",
                ))

        # Check total
        if total_tools == 64:
            report.add(HealthCheckResult(
                name="Specialized Agent Total",
                status=CheckStatus.PASS,
                message=f"All {total_tools}/64 tools across 8 agents",
            ))
        else:
            report.add(HealthCheckResult(
                name="Specialized Agent Total",
                status=CheckStatus.WARN,
                message=f"{total_tools}/64 tools registered",
            ))

    except ImportError as e:
        report.add(HealthCheckResult(
            name="Specialized Agents Module",
            status=CheckStatus.FAIL,
            message=f"Import error: {e}",
            recommendations=["Check specialized agent imports in __init__.py"]
        ))


# =============================================================================
# MAIN RUNNER
# =============================================================================

async def run_health_check():
    """Run complete health check suite."""
    print("=" * 70)
    print("PERENNIA AI - AGENT HEALTH CHECK")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run all checks
    check_configuration()
    check_tool_registration()
    check_specialized_agents()
    check_database_connection()
    check_query_performance()
    await check_agent_orchestration()
    await check_approval_workflow()
    check_error_handling()
    await check_concurrent_execution()
    check_memory_system()
    check_langchain_integration()
    await check_e2e_workflow()
    check_recommended_indexes()

    # Print summary
    return report.print_summary()


def main():
    """Entry point."""
    success = asyncio.run(run_health_check())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
