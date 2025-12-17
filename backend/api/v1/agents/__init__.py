"""
Agent Orchestration API Routes

Provides endpoints for:
- Agent execution (with token optimization)
- Performance metrics
- A/B testing
- Quality analysis
- Agent configuration management
"""

from .routes import router

__all__ = ["router"]
