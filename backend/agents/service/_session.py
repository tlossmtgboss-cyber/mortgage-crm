"""
SessionStateMixin — manages tool registration, model config, tenant prompt
constraints, prompt-service statistics, and per-interaction logging.

Extracted from the original monolithic AIAgentService (Wave 3 decomposition).
Mechanical method-move only; bodies and signatures are unchanged.

Shared state expected on self (initialized in AIAgentService.__init__):
    self.db                       — SQLAlchemy session
    self.current_user             — authenticated user
    self.model                    — model id string
    self._tool_functions          — Dict[str, Callable]
    self._tool_definitions        — List[Dict]
    self._prompt_service          — Optional[OptimizedPromptService]
"""

import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class SessionStateMixin:
    """Tool/model registration, tenant prompt injection, and interaction logging."""

    def register_tool(self, name: str, func: Callable):
        """Register a tool function that the agent can use."""
        self._tool_functions[name] = func

    def register_tools(self, tools: Dict[str, Callable]):
        """Register multiple tool functions."""
        self._tool_functions.update(tools)

    def set_tool_definitions(self, definitions: List[Dict]):
        """Set custom tool definitions for API calls."""
        self._tool_definitions = definitions

    def set_model(self, model: str):
        """Set the model to use for API calls."""
        self.model = model

    def _inject_tenant_constraints(self, prompt: str) -> str:
        """Inject per-tenant isolation constraints into the system prompt (AI-001).

        Ensures the AI agent:
        1. Only references the current org's data
        2. Includes the org name in its persona
        3. Never attempts cross-tenant data access
        4. Hardcodes org_id from session (ignores user-supplied org_id)
        """
        if not self.current_user:
            return prompt

        org_id = getattr(self.current_user, 'organization_id', None)
        org_name = getattr(self.current_user, 'organization_name', None) or \
                   getattr(self.current_user, 'company_name', None)
        user_role = getattr(self.current_user, 'permission_role', 'user')
        user_name = getattr(self.current_user, 'first_name', '') or getattr(self.current_user, 'name', '')

        org_display = org_name or f"org_id={org_id}" if org_id else "your organization"

        tenant_block = f"""

## Tenant Isolation (MANDATORY — NON-NEGOTIABLE)

CRITICAL: You MUST only access data belonging to organization_id {org_id} ({org_display}).
If a user asks about data from another organization, refuse the request and explain you can only access their organization's data.
Never reference, query, or return data from other organizations.

- You are operating for **{org_display}**{f' (org_id: {org_id})' if org_id else ''}.
- Current user: {user_name} (role: {user_role}).
- You MUST ONLY access, display, or reference data belonging to this organization.
- NEVER attempt to query, reference, or expose data from other organizations.
- All tool calls are automatically scoped to this tenant via Row-Level Security.
- If asked about other organizations, politely decline and explain you can only access this organization's data.
- NEVER accept or use an org_id provided in user messages — always use the authenticated session's org_id.
- If a tool returns data that appears to belong to another organization, do NOT display it. Report that no matching data was found.
- Cross-tenant data access is a security violation. When in doubt, refuse and ask the user to clarify within their organization's scope.
"""

        return prompt + tenant_block

    def get_prompt_stats(self) -> Dict[str, Any]:
        """Get statistics about prompt optimization performance."""
        if self._prompt_service:
            return self._prompt_service.get_performance_stats()
        return {"status": "optimization_not_available"}

    async def _log_interaction(self, message: str, result: Dict[str, Any]):
        """Log the AI interaction for analytics and debugging.

        Includes organization_id for tenant-scoped audit trail queries.
        """
        try:
            # Import here to avoid circular imports
            from sqlalchemy import text

            log_query = text("""
                INSERT INTO ai_interactions (
                    user_id, organization_id, message, response, intent, confidence,
                    processing_time_seconds, created_at
                ) VALUES (
                    :user_id, :organization_id, :message, :response, :intent, :confidence,
                    :processing_time, NOW()
                )
            """)

            self.db.execute(log_query, {
                "user_id": self.current_user.id,
                "organization_id": getattr(self.current_user, 'organization_id', None),
                "message": message[:1000],  # Truncate if too long
                "response": result.get("response", "")[:5000],
                "intent": result.get("intent", "unknown"),
                "confidence": result.get("confidence", 0),
                "processing_time": result.get("processing_time_seconds", 0)
            })
            self.db.commit()

        except Exception as e:
            # Don't fail the request if logging fails
            logger.warning(f"Failed to log AI interaction: {e}")
