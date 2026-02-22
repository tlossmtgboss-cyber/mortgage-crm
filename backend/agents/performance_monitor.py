# Perennia AI - Agent Performance Monitor & Benchmarks
# Track and optimize agent performance over time

"""
PERFORMANCE MONITORING SYSTEM
=============================
This module provides:
1. Real-time performance metrics collection
2. Tool execution benchmarking
3. Agent efficiency scoring
4. Bottleneck identification
5. Trend analysis

Save as: backend/agents/performance_monitor.py
"""

import time
import asyncio
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import json
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# PERFORMANCE METRICS
# =============================================================================

@dataclass
class ToolMetrics:
    """Metrics for a single tool."""
    tool_name: str
    agent: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    max_time_ms: float = 0.0
    times: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    last_called: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return (self.successful_calls / self.total_calls) * 100

    @property
    def avg_time_ms(self) -> float:
        if not self.times:
            return 0.0
        return statistics.mean(self.times)

    @property
    def p95_time_ms(self) -> float:
        if len(self.times) < 20:
            return self.max_time_ms
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]

    @property
    def p99_time_ms(self) -> float:
        if len(self.times) < 100:
            return self.max_time_ms
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[idx]

    def record_call(self, duration_ms: float, success: bool, error: str = None):
        self.total_calls += 1
        self.total_time_ms += duration_ms
        self.times.append(duration_ms)
        self.last_called = datetime.now()

        if duration_ms < self.min_time_ms:
            self.min_time_ms = duration_ms
        if duration_ms > self.max_time_ms:
            self.max_time_ms = duration_ms

        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
            if error:
                self.errors.append(error)

        # Keep only last 1000 times for memory efficiency
        if len(self.times) > 1000:
            self.times = self.times[-1000:]

    def to_dict(self) -> Dict:
        return {
            "tool_name": self.tool_name,
            "agent": self.agent,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 2),
            "avg_time_ms": round(self.avg_time_ms, 2),
            "min_time_ms": round(self.min_time_ms, 2) if self.min_time_ms != float('inf') else 0,
            "max_time_ms": round(self.max_time_ms, 2),
            "p95_time_ms": round(self.p95_time_ms, 2),
            "p99_time_ms": round(self.p99_time_ms, 2),
            "last_called": self.last_called.isoformat() if self.last_called else None,
            "recent_errors": self.errors[-5:] if self.errors else [],
        }


@dataclass
class AgentMetrics:
    """Aggregate metrics for an agent."""
    agent_name: str
    tool_metrics: Dict[str, ToolMetrics] = field(default_factory=dict)

    @property
    def total_calls(self) -> int:
        return sum(t.total_calls for t in self.tool_metrics.values())

    @property
    def success_rate(self) -> float:
        total = sum(t.total_calls for t in self.tool_metrics.values())
        successful = sum(t.successful_calls for t in self.tool_metrics.values())
        return (successful / total * 100) if total > 0 else 0.0

    @property
    def avg_time_ms(self) -> float:
        all_times = []
        for t in self.tool_metrics.values():
            all_times.extend(t.times)
        return statistics.mean(all_times) if all_times else 0.0

    def get_slowest_tools(self, n: int = 3) -> List[ToolMetrics]:
        """Get the N slowest tools by average time."""
        sorted_tools = sorted(
            self.tool_metrics.values(),
            key=lambda t: t.avg_time_ms,
            reverse=True
        )
        return sorted_tools[:n]

    def get_most_failing_tools(self, n: int = 3) -> List[ToolMetrics]:
        """Get the N tools with lowest success rate."""
        sorted_tools = sorted(
            [t for t in self.tool_metrics.values() if t.total_calls > 0],
            key=lambda t: t.success_rate
        )
        return sorted_tools[:n]

    def to_dict(self) -> Dict:
        return {
            "agent_name": self.agent_name,
            "total_calls": self.total_calls,
            "success_rate": round(self.success_rate, 2),
            "avg_time_ms": round(self.avg_time_ms, 2),
            "tool_count": len(self.tool_metrics),
            "slowest_tools": [t.tool_name for t in self.get_slowest_tools()],
            "failing_tools": [t.tool_name for t in self.get_most_failing_tools()],
        }


# =============================================================================
# PERFORMANCE MONITOR
# =============================================================================

class PerformanceMonitor:
    """Central performance monitoring system."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.agents: Dict[str, AgentMetrics] = {}
        self.start_time = datetime.now()
        self.benchmarks: Dict[str, Dict] = {}
        self._initialized = True

    def record_tool_call(
        self,
        agent: str,
        tool_name: str,
        duration_ms: float,
        success: bool,
        error: str = None
    ):
        """Record a tool execution."""
        if agent not in self.agents:
            self.agents[agent] = AgentMetrics(agent_name=agent)

        if tool_name not in self.agents[agent].tool_metrics:
            self.agents[agent].tool_metrics[tool_name] = ToolMetrics(
                tool_name=tool_name,
                agent=agent
            )

        self.agents[agent].tool_metrics[tool_name].record_call(
            duration_ms, success, error
        )

    def get_agent_metrics(self, agent: str) -> Optional[AgentMetrics]:
        """Get metrics for a specific agent."""
        return self.agents.get(agent)

    def get_tool_metrics(self, agent: str, tool_name: str) -> Optional[ToolMetrics]:
        """Get metrics for a specific tool."""
        agent_metrics = self.agents.get(agent)
        if agent_metrics:
            return agent_metrics.tool_metrics.get(tool_name)
        return None

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get complete metrics summary."""
        total_calls = sum(a.total_calls for a in self.agents.values())
        total_successful = sum(
            sum(t.successful_calls for t in a.tool_metrics.values())
            for a in self.agents.values()
        )

        all_times = []
        for agent in self.agents.values():
            for tool in agent.tool_metrics.values():
                all_times.extend(tool.times)

        return {
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "total_calls": total_calls,
            "total_successful": total_successful,
            "overall_success_rate": round((total_successful / total_calls * 100) if total_calls > 0 else 0, 2),
            "overall_avg_time_ms": round(statistics.mean(all_times) if all_times else 0, 2),
            "agents": {name: agent.to_dict() for name, agent in self.agents.items()},
        }

    def get_performance_report(self) -> str:
        """Generate human-readable performance report."""
        metrics = self.get_all_metrics()

        lines = [
            "=" * 70,
            "AGENT PERFORMANCE REPORT",
            "=" * 70,
            f"Uptime: {metrics['uptime_seconds']:.0f} seconds",
            f"Total Calls: {metrics['total_calls']}",
            f"Success Rate: {metrics['overall_success_rate']}%",
            f"Avg Response Time: {metrics['overall_avg_time_ms']:.2f}ms",
            "",
            "BY AGENT:",
            "-" * 50,
        ]

        for agent_name, agent_data in metrics['agents'].items():
            lines.append(f"\n📊 {agent_name.upper()}")
            lines.append(f"   Calls: {agent_data['total_calls']}")
            lines.append(f"   Success: {agent_data['success_rate']}%")
            lines.append(f"   Avg Time: {agent_data['avg_time_ms']:.2f}ms")

            if agent_data['slowest_tools']:
                lines.append(f"   Slowest: {', '.join(agent_data['slowest_tools'])}")
            if agent_data['failing_tools']:
                lines.append(f"   Failing: {', '.join(agent_data['failing_tools'])}")

        lines.append("")
        lines.append("=" * 70)

        return "\n".join(lines)

    def identify_bottlenecks(self) -> List[Dict]:
        """Identify performance bottlenecks."""
        bottlenecks = []

        for agent in self.agents.values():
            for tool in agent.tool_metrics.values():
                # Slow tools (>500ms avg)
                if tool.avg_time_ms > 500 and tool.total_calls >= 5:
                    bottlenecks.append({
                        "type": "slow_tool",
                        "agent": agent.agent_name,
                        "tool": tool.tool_name,
                        "avg_time_ms": round(tool.avg_time_ms, 2),
                        "recommendation": "Optimize database queries or add caching"
                    })

                # Failing tools (<90% success with significant calls)
                if tool.success_rate < 90 and tool.total_calls >= 10:
                    bottlenecks.append({
                        "type": "failing_tool",
                        "agent": agent.agent_name,
                        "tool": tool.tool_name,
                        "success_rate": round(tool.success_rate, 2),
                        "recent_errors": tool.errors[-3:],
                        "recommendation": "Review error handling and input validation"
                    })

                # High variance (p99 > 3x avg)
                if tool.p99_time_ms > tool.avg_time_ms * 3 and tool.total_calls >= 20:
                    bottlenecks.append({
                        "type": "high_variance",
                        "agent": agent.agent_name,
                        "tool": tool.tool_name,
                        "avg_time_ms": round(tool.avg_time_ms, 2),
                        "p99_time_ms": round(tool.p99_time_ms, 2),
                        "recommendation": "Investigate intermittent slowdowns"
                    })

        return bottlenecks

    def set_benchmark(self, tool_name: str, target_ms: float, max_ms: float):
        """Set performance benchmarks for a tool."""
        self.benchmarks[tool_name] = {
            "target_ms": target_ms,
            "max_ms": max_ms,
        }

    def check_benchmarks(self) -> List[Dict]:
        """Check if tools meet their benchmarks."""
        violations = []

        for agent in self.agents.values():
            for tool in agent.tool_metrics.values():
                if tool.tool_name in self.benchmarks:
                    bench = self.benchmarks[tool.tool_name]

                    if tool.avg_time_ms > bench["target_ms"]:
                        violations.append({
                            "tool": tool.tool_name,
                            "agent": agent.agent_name,
                            "benchmark": "target",
                            "target_ms": bench["target_ms"],
                            "actual_ms": round(tool.avg_time_ms, 2),
                            "exceeded_by": round(tool.avg_time_ms - bench["target_ms"], 2),
                        })

                    if tool.max_time_ms > bench["max_ms"]:
                        violations.append({
                            "tool": tool.tool_name,
                            "agent": agent.agent_name,
                            "benchmark": "max",
                            "max_ms": bench["max_ms"],
                            "actual_ms": round(tool.max_time_ms, 2),
                            "exceeded_by": round(tool.max_time_ms - bench["max_ms"], 2),
                        })

        return violations

    def reset(self):
        """Reset all metrics."""
        self.agents = {}
        self.start_time = datetime.now()


# Global monitor instance
monitor = PerformanceMonitor()


# =============================================================================
# MONITORING DECORATORS
# =============================================================================

def monitored_tool(agent: str):
    """Decorator to automatically monitor tool execution."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            success = True
            error = None

            try:
                result = await func(*args, **kwargs)
                if hasattr(result, 'status'):
                    from backend.agents.tools.base import ToolStatus
                    success = result.status == ToolStatus.SUCCESS
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                duration = (time.time() - start) * 1000
                monitor.record_tool_call(
                    agent=agent,
                    tool_name=func.__name__,
                    duration_ms=duration,
                    success=success,
                    error=error
                )

        def sync_wrapper(*args, **kwargs):
            start = time.time()
            success = True
            error = None

            try:
                result = func(*args, **kwargs)
                if hasattr(result, 'status'):
                    from backend.agents.tools.base import ToolStatus
                    success = result.status == ToolStatus.SUCCESS
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                duration = (time.time() - start) * 1000
                monitor.record_tool_call(
                    agent=agent,
                    tool_name=func.__name__,
                    duration_ms=duration,
                    success=success,
                    error=error
                )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================

async def run_benchmarks(iterations: int = 10) -> Dict[str, Any]:
    """Run performance benchmarks for all tools."""
    print("=" * 70)
    print("RUNNING PERFORMANCE BENCHMARKS")
    print(f"Iterations per tool: {iterations}")
    print("=" * 70)

    from backend.agents.tools import tool_registry, execute_tool
    from backend.agents.tool_integration import AGENT_CONFIGS

    results = {}

    for agent_name, config in AGENT_CONFIGS.items():
        print(f"\n📊 Benchmarking {agent_name}...")
        results[agent_name] = {}

        for tool_name in config.tool_names:
            times = []
            successes = 0

            for i in range(iterations):
                start = time.time()
                try:
                    # Call with minimal params
                    result = execute_tool(tool_name)
                    if hasattr(result, 'status'):
                        from backend.agents.tools.base import ToolStatus
                        if result.status in [ToolStatus.SUCCESS, ToolStatus.NO_DATA]:
                            successes += 1
                    else:
                        successes += 1
                except Exception as e:
                    logger.error(f"Error executing tool {tool_name}: {e}")

                duration = (time.time() - start) * 1000
                times.append(duration)

            if times:
                results[agent_name][tool_name] = {
                    "iterations": iterations,
                    "success_rate": round((successes / iterations) * 100, 1),
                    "avg_ms": round(statistics.mean(times), 2),
                    "min_ms": round(min(times), 2),
                    "max_ms": round(max(times), 2),
                    "stdev_ms": round(statistics.stdev(times), 2) if len(times) > 1 else 0,
                }

                status = "✅" if results[agent_name][tool_name]["avg_ms"] < 200 else "⚠️"
                print(f"  {status} {tool_name}: {results[agent_name][tool_name]['avg_ms']}ms avg")

    # Summary
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)

    all_avgs = []
    for agent_results in results.values():
        for tool_results in agent_results.values():
            all_avgs.append(tool_results["avg_ms"])

    if all_avgs:
        print(f"Overall Average: {statistics.mean(all_avgs):.2f}ms")
        print(f"Fastest Tool: {min(all_avgs):.2f}ms")
        print(f"Slowest Tool: {max(all_avgs):.2f}ms")

    return results


# =============================================================================
# MONITORING API ENDPOINTS
# =============================================================================

def get_monitoring_routes():
    """Return FastAPI routes for monitoring endpoints."""
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

    @router.get("/metrics")
    async def get_metrics():
        """Get current performance metrics."""
        return monitor.get_all_metrics()

    @router.get("/metrics/{agent}")
    async def get_agent_metrics(agent: str):
        """Get metrics for specific agent."""
        metrics = monitor.get_agent_metrics(agent)
        if metrics:
            return metrics.to_dict()
        return {"error": "Agent not found"}

    @router.get("/bottlenecks")
    async def get_bottlenecks():
        """Identify current bottlenecks."""
        return monitor.identify_bottlenecks()

    @router.get("/report")
    async def get_report():
        """Get human-readable performance report."""
        return {"report": monitor.get_performance_report()}

    @router.post("/reset")
    async def reset_metrics():
        """Reset all metrics."""
        monitor.reset()
        return {"status": "reset"}

    return router


# =============================================================================
# CLI COMMANDS
# =============================================================================

def print_dashboard():
    """Print real-time dashboard."""
    import os

    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print(monitor.get_performance_report())

        bottlenecks = monitor.identify_bottlenecks()
        if bottlenecks:
            print("\n🚨 BOTTLENECKS DETECTED:")
            for b in bottlenecks[:5]:
                print(f"  - {b['type']}: {b['agent']}/{b['tool']}")
                print(f"    {b['recommendation']}")

        print("\nRefreshing in 5 seconds... (Ctrl+C to exit)")
        time.sleep(5)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "dashboard":
            print_dashboard()
        elif sys.argv[1] == "benchmark":
            iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            asyncio.run(run_benchmarks(iterations))
        elif sys.argv[1] == "report":
            print(monitor.get_performance_report())
    else:
        print("Usage:")
        print("  python performance_monitor.py dashboard  - Live dashboard")
        print("  python performance_monitor.py benchmark [n] - Run benchmarks")
        print("  python performance_monitor.py report - Print report")
