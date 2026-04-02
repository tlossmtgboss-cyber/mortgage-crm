"""
Cache performance metrics for AI Agent tools

Tracks cache hit/miss rates and response times to measure
the effectiveness of Redis caching.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict
import threading


@dataclass
class CacheMetric:
    """Track cache hit/miss for analytics"""
    tool_name: str
    hit: bool
    execution_time_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CacheMetrics:
    """
    Track cache performance metrics.

    Thread-safe metrics collection for cache hit/miss tracking.
    Provides real-time statistics on cache effectiveness.
    """

    def __init__(self, max_metrics: int = 1000):
        self.metrics: List[CacheMetric] = []
        self.max_metrics = max_metrics
        self._lock = threading.Lock()

    def record(self, tool_name: str, hit: bool, execution_time_ms: float):
        """
        Record a cache hit/miss.

        Args:
            tool_name: Name of the tool that was called
            hit: True if cache hit, False if cache miss
            execution_time_ms: How long the operation took
        """
        with self._lock:
            self.metrics.append(CacheMetric(
                tool_name=tool_name,
                hit=hit,
                execution_time_ms=execution_time_ms
            ))

            # Keep only last N metrics to prevent memory growth
            if len(self.metrics) > self.max_metrics:
                self.metrics = self.metrics[-self.max_metrics:]

    def get_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache performance metrics
        """
        with self._lock:
            if not self.metrics:
                return {
                    "total_queries": 0,
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "hit_rate": 0.0,
                    "avg_hit_time_ms": 0.0,
                    "avg_miss_time_ms": 0.0,
                    "speedup": 0.0
                }

            total = len(self.metrics)
            hits = sum(1 for m in self.metrics if m.hit)
            misses = total - hits
            hit_rate = (hits / total * 100) if total > 0 else 0

            # Calculate average times
            hit_times = [m.execution_time_ms for m in self.metrics if m.hit]
            miss_times = [m.execution_time_ms for m in self.metrics if not m.hit]

            avg_hit_time = sum(hit_times) / len(hit_times) if hit_times else 0
            avg_miss_time = sum(miss_times) / len(miss_times) if miss_times else 0

            # Calculate speedup factor
            speedup = (avg_miss_time / avg_hit_time) if avg_hit_time > 0 else 0

            return {
                "total_queries": total,
                "cache_hits": hits,
                "cache_misses": misses,
                "hit_rate": round(hit_rate, 1),
                "avg_hit_time_ms": round(avg_hit_time, 2),
                "avg_miss_time_ms": round(avg_miss_time, 2),
                "speedup": round(speedup, 1)
            }

    def get_stats_by_tool(self) -> Dict[str, Dict]:
        """
        Get cache statistics broken down by tool.

        Returns:
            Dictionary mapping tool names to their stats
        """
        with self._lock:
            if not self.metrics:
                return {}

            # Group metrics by tool
            tool_metrics: Dict[str, List[CacheMetric]] = {}
            for m in self.metrics:
                if m.tool_name not in tool_metrics:
                    tool_metrics[m.tool_name] = []
                tool_metrics[m.tool_name].append(m)

            # Calculate stats per tool
            results = {}
            for tool_name, metrics in tool_metrics.items():
                total = len(metrics)
                hits = sum(1 for m in metrics if m.hit)
                hit_rate = (hits / total * 100) if total > 0 else 0

                hit_times = [m.execution_time_ms for m in metrics if m.hit]
                miss_times = [m.execution_time_ms for m in metrics if not m.hit]

                avg_hit = sum(hit_times) / len(hit_times) if hit_times else 0
                avg_miss = sum(miss_times) / len(miss_times) if miss_times else 0

                results[tool_name] = {
                    "total": total,
                    "hits": hits,
                    "hit_rate": round(hit_rate, 1),
                    "avg_hit_ms": round(avg_hit, 2),
                    "avg_miss_ms": round(avg_miss, 2)
                }

            return results

    def clear(self):
        """Clear all metrics."""
        with self._lock:
            self.metrics.clear()


# Global metrics tracker
cache_metrics = CacheMetrics()
