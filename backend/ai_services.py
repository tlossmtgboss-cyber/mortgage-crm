"""
AI Architecture Services
Core orchestration and management services for the AI system
"""

import os
import json
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable, Union
from sqlalchemy import text, Engine
from sqlalchemy.orm import Session
import openai

from ai_models import (
    AgentConfig, ToolDefinition, AgentEvent, AgentMessage,
    AgentExecution, ExecutionStatus, ToolContext, ContextPacket,
    AgentPlan, AgentPlanStep, EventStatus, MessageType, Priority
)

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")


# ============================================================================
# DATABASE HELPER
# ============================================================================

from contextlib import contextmanager

@contextmanager
def get_db_connection(db: Union[Engine, Session]):
    """Helper to work with both Engine and Session objects"""
    if hasattr(db, 'connect'):
        # It's an Engine - create a connection
        conn = db.connect()
        try:
            yield conn
        finally:
            conn.close()
    else:
        # It's a Session - just yield it directly
        yield db


# ============================================================================
# AGENT REGISTRY SERVICE
# ============================================================================

class AgentRegistry:
    """Central registry for all AI agents"""

    def __init__(self, db: Union[Engine, Session]):
        self.db = db

    async def register_agent(self, config: AgentConfig) -> str:
        """Register a new agent"""
        query = text("""
            INSERT INTO ai_agents (
                id, name, description, agent_type, status,
                goals, tools, triggers, config, version
            ) VALUES (
                :id, :name, :description, :agent_type, :status,
                :goals, :tools, :triggers, :config, :version
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                goals = EXCLUDED.goals,
                tools = EXCLUDED.tools,
                triggers = EXCLUDED.triggers,
                config = EXCLUDED.config,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """)

        with get_db_connection(self.db) as conn:
            result = conn.execute(query, {
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "agent_type": config.agent_type.value,
                "status": config.status.value,
                "goals": json.dumps(config.goals),
                "tools": json.dumps(config.tools),
                "triggers": json.dumps(config.triggers),
                "config": json.dumps(config.config),
                "version": config.version
            })
            conn.commit()
            return result.fetchone()[0]

    async def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """Get agent configuration"""
        query = text("""
            SELECT id, name, description, agent_type, status,
                   goals, tools, triggers, config, version
            FROM ai_agents
            WHERE id = :agent_id AND status = 'active'
        """)

        with get_db_connection(self.db) as conn:
            result = conn.execute(query, {"agent_id": agent_id}).fetchone()

        if not result:
            return None

        return AgentConfig(
            id=result.id,
            name=result.name,
            description=result.description,
            agent_type=result.agent_type,
            status=result.status,
            goals=result.goals if isinstance(result.goals, list) else (json.loads(result.goals) if result.goals else []),
            tools=result.tools if isinstance(result.tools, list) else (json.loads(result.tools) if result.tools else []),
            triggers=result.triggers if isinstance(result.triggers, list) else (json.loads(result.triggers) if result.triggers else []),
            config=result.config if isinstance(result.config, dict) else (json.loads(result.config) if result.config else {}),
            version=result.version
        )

    async def get_agents_for_event(self, event_type: str) -> List[AgentConfig]:
        """Get all agents that should handle this event type"""
        query = text("""
            SELECT id, name, description, agent_type, status,
                   goals, tools, triggers, config, version
            FROM ai_agents
            WHERE status = 'active'
            AND triggers::jsonb ? :event_type
        """)

        with get_db_connection(self.db) as conn:
            results = conn.execute(query, {"event_type": event_type}).fetchall()

        agents = []
        for row in results:
            agents.append(AgentConfig(
                id=row.id,
                name=row.name,
                description=row.description,
                agent_type=row.agent_type,
                status=row.status,
                goals=row.goals if isinstance(row.goals, list) else (json.loads(row.goals) if row.goals else []),
                tools=row.tools if isinstance(row.tools, list) else (json.loads(row.tools) if row.tools else []),
                triggers=row.triggers if isinstance(row.triggers, list) else (json.loads(row.triggers) if row.triggers else []),
                config=row.config if isinstance(row.config, dict) else (json.loads(row.config) if row.config else {}),
                version=row.version
            ))

        return agents


# ============================================================================
# TOOL REGISTRY SERVICE
# ============================================================================

class ToolRegistry:
    """Central registry for all tools agents can call"""

    def __init__(self, db: Union[Engine, Session]):
        self.db = db
        self.handlers: Dict[str, Callable] = {}

    async def register_tool(self, tool: ToolDefinition, handler: Callable) -> int:
        """Register a new tool"""
        query = text("""
            INSERT INTO ai_tools (
                name, description, category, input_schema, output_schema,
                handler_endpoint, allowed_agents, risk_level, requires_approval
            ) VALUES (
                :name, :description, :category, :input_schema, :output_schema,
                :handler_endpoint, :allowed_agents, :risk_level, :requires_approval
            )
            ON CONFLICT (name) DO UPDATE SET
                description = EXCLUDED.description,
                input_schema = EXCLUDED.input_schema,
                output_schema = EXCLUDED.output_schema,
                allowed_agents = EXCLUDED.allowed_agents,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """)

        with get_db_connection(self.db) as conn:
            result = conn.execute(query, {
                "name": tool.name,
                "description": tool.description,
                "category": tool.category.value,
                "input_schema": json.dumps(tool.input_schema),
                "output_schema": json.dumps(tool.output_schema),
                "handler_endpoint": tool.handler_endpoint,
                "allowed_agents": json.dumps(tool.allowed_agents),
                "risk_level": tool.risk_level.value,
                "requires_approval": tool.requires_approval
            })
            conn.commit()

            # Store handler in memory
            self.handlers[tool.name] = handler

            return result.fetchone()[0]

    async def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """Get tool definition"""
        query = text("""
            SELECT name, description, category, input_schema, output_schema,
                   handler_endpoint, allowed_agents, risk_level, requires_approval
            FROM ai_tools
            WHERE name = :tool_name AND is_active = TRUE
        """)

        with get_db_connection(self.db) as conn:
            result = conn.execute(query, {"tool_name": tool_name}).fetchone()

        if not result:
            return None

        return ToolDefinition(
            name=result.name,
            description=result.description,
            category=result.category,
            input_schema=result.input_schema if isinstance(result.input_schema, dict) else json.loads(result.input_schema),
            output_schema=result.output_schema if isinstance(result.output_schema, dict) else json.loads(result.output_schema),
            handler_endpoint=result.handler_endpoint,
            allowed_agents=result.allowed_agents if isinstance(result.allowed_agents, list) else (json.loads(result.allowed_agents) if result.allowed_agents else []),
            risk_level=result.risk_level,
            requires_approval=result.requires_approval
        )

    async def execute_tool(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        context: ToolContext
    ) -> Dict[str, Any]:
        """Execute a tool"""
        # Get tool definition
        tool = await self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")

        # Check if agent is allowed to use this tool
        if tool.allowed_agents and context.agent_id not in tool.allowed_agents:
            raise PermissionError(f"Agent {context.agent_id} not allowed to use tool {tool_name}")

        # Get handler
        handler = self.handlers.get(tool_name)
        if not handler:
            raise ValueError(f"No handler registered for tool {tool_name}")

        # Execute handler
        start_time = datetime.now()
        try:
            result = await handler(input_data, context)
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # Update tool metrics
            await self._update_tool_metrics(tool_name, duration_ms, True)

            return result
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            await self._update_tool_metrics(tool_name, duration_ms, False)
            raise

    async def _update_tool_metrics(self, tool_name: str, duration_ms: int, success: bool):
        """Update tool execution metrics"""
        query = text("""
            UPDATE ai_tools
            SET execution_count = execution_count + 1,
                avg_duration_ms = (
                    COALESCE(avg_duration_ms * execution_count, 0) + :duration_ms
                ) / (execution_count + 1),
                success_rate = (
                    (COALESCE(success_rate * execution_count, 0) + CASE WHEN :success THEN 100 ELSE 0 END)
                    / (execution_count + 1)
                )
            WHERE name = :tool_name
        """)

        self.db.execute(query, {
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "success": success
        })
        self.db.commit()


# ============================================================================
# MESSAGE BUS SERVICE
# ============================================================================

class MessageBus:
    """Inter-agent communication"""

    def __init__(self, db: Session):
        self.db = db

    async def send_message(self, message: AgentMessage) -> str:
        """Send message from one agent to another"""
        query = text("""
            INSERT INTO ai_agent_messages (
                message_id, from_agent_id, to_agent_id, message_type,
                subject, content, payload, priority, requires_human_review
            ) VALUES (
                :message_id, :from_agent_id, :to_agent_id, :message_type,
                :subject, :content, :payload, :priority, :requires_human_review
            )
            RETURNING id
        """)

        result = self.db.execute(query, {
            "message_id": message.message_id,
            "from_agent_id": message.from_agent_id,
            "to_agent_id": message.to_agent_id,
            "message_type": message.message_type.value,
            "subject": message.subject,
            "content": message.content,
            "payload": json.dumps(message.payload),
            "priority": message.priority.value,
            "requires_human_review": message.requires_human_review
        })

        self.db.commit()
        return result.fetchone()[0]

    async def broadcast_message(self, message: AgentMessage) -> int:
        """Broadcast message to all active agents"""
        message.to_agent_id = None
        return await self.send_message(message)

    async def get_pending_messages(self, agent_id: str) -> List[AgentMessage]:
        """Get pending messages for an agent"""
        query = text("""
            SELECT message_id, from_agent_id, to_agent_id, message_type,
                   subject, content, payload, priority, requires_human_review
            FROM ai_agent_messages
            WHERE (to_agent_id = :agent_id OR to_agent_id IS NULL)
            AND status = 'pending'
            ORDER BY
                CASE priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    WHEN 'low' THEN 4
                END,
                created_at
        """)

        results = self.db.execute(query, {"agent_id": agent_id}).fetchall()

        messages = []
        for row in results:
            messages.append(AgentMessage(
                message_id=row.message_id,
                from_agent_id=row.from_agent_id,
                to_agent_id=row.to_agent_id,
                message_type=row.message_type,
                subject=row.subject,
                content=row.content,
                payload=row.payload if isinstance(row.payload, dict) else (json.loads(row.payload) if row.payload else {}),
                priority=row.priority,
                requires_human_review=row.requires_human_review
            ))

        return messages

    async def mark_message_processed(self, message_id: str):
        """Mark message as processed"""
        query = text("""
            UPDATE ai_agent_messages
            SET status = 'processed'
            WHERE message_id = :message_id
        """)

        self.db.execute(query, {"message_id": message_id})
        self.db.commit()


# ============================================================================
# CONTEXT BUILDER SERVICE
# ============================================================================

class ContextBuilder:
    """Build working memory context for agents"""

    def __init__(self, db: Session):
        self.db = db

    async def build_context_for_lead(
        self,
        lead_id: int,
        goal: str
    ) -> ContextPacket:
        """Build context for lead-related task"""
        # Get lead data
        lead_query = text("SELECT * FROM leads WHERE id = :lead_id")
        lead = self.db.execute(lead_query, {"lead_id": lead_id}).fetchone()

        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Get related tasks
        tasks_query = text("""
            SELECT * FROM tasks
            WHERE lead_id = :lead_id
            AND status NOT IN ('completed', 'cancelled')
            ORDER BY due_date
            LIMIT 10
        """)
        tasks = self.db.execute(tasks_query, {"lead_id": lead_id}).fetchall()

        # Get recent communications
        comms_query = text("""
            SELECT * FROM communications
            WHERE lead_id = :lead_id
            ORDER BY created_at DESC
            LIMIT 5
        """)
        comms = self.db.execute(comms_query, {"lead_id": lead_id}).fetchall()

        # Get prior AI actions
        actions_query = text("""
            SELECT * FROM ai_agent_executions
            WHERE entity_type = 'lead'
            AND entity_id = :entity_id
            ORDER BY created_at DESC
            LIMIT 10
        """)
        actions = self.db.execute(actions_query, {"entity_id": str(lead_id)}).fetchall()

        return ContextPacket(
            goal=goal,
            entity_type="lead",
            entity_id=str(lead_id),
            entity_data=dict(lead._mapping) if lead else {},
            related_tasks=[dict(t._mapping) for t in tasks],
            recent_communications=[dict(c._mapping) for c in comms],
            prior_ai_actions=[dict(a._mapping) for a in actions],
            metadata={}
        )

    async def build_context_for_loan(
        self,
        loan_id: int,
        goal: str
    ) -> ContextPacket:
        """Build context for loan-related task"""
        # Similar implementation for loans
        loan_query = text("SELECT * FROM loans WHERE id = :loan_id")
        loan = self.db.execute(loan_query, {"loan_id": loan_id}).fetchone()

        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        # Get borrower info
        borrower_query = text("""
            SELECT * FROM borrowers
            WHERE loan_id = :loan_id
        """)
        borrowers = self.db.execute(borrower_query, {"loan_id": loan_id}).fetchall()

        # Get documents
        docs_query = text("""
            SELECT * FROM documents
            WHERE loan_id = :loan_id
            ORDER BY created_at DESC
            LIMIT 20
        """)
        docs = self.db.execute(docs_query, {"loan_id": loan_id}).fetchall()

        return ContextPacket(
            goal=goal,
            entity_type="loan",
            entity_id=str(loan_id),
            entity_data=dict(loan._mapping) if loan else {},
            related_tasks=[],
            recent_communications=[],
            metadata={
                "borrowers": [dict(b._mapping) for b in borrowers],
                "documents": [dict(d._mapping) for d in docs]
            }
        )


# ============================================================================
# AGENT ORCHESTRATOR SERVICE
# ============================================================================

class AgentOrchestrator:
    """Central orchestration service for all agents"""

    def __init__(self, db: Session):
        self.db = db
        self.agent_registry = AgentRegistry(db)
        self.tool_registry = ToolRegistry(db)
        self.message_bus = MessageBus(db)
        self.context_builder = ContextBuilder(db)

    async def dispatch_event(self, event: AgentEvent) -> List[AgentExecution]:
        """Dispatch event to relevant agents"""
        # Record event
        await self._record_event(event)

        # Find agents that subscribe to this event
        agents = await self.agent_registry.get_agents_for_event(event.event_type)

        if not agents:
            print(f"No agents found for event type: {event.event_type}")
            return []

        # Execute each agent
        executions = []
        for agent in agents:
            try:
                execution = await self.execute_agent(agent, event)
                executions.append(execution)
            except Exception as e:
                print(f"Error executing agent {agent.id}: {e}")
                continue

        return executions

    async def execute_agent(
        self,
        agent: AgentConfig,
        event: AgentEvent
    ) -> AgentExecution:
        """Execute a single agent"""
        execution_id = str(uuid.uuid4())
        start_time = datetime.now()

        try:
            # Build context
            context = await self._build_agent_context(agent, event)

            # Get agent prompt
            prompt = await self._build_agent_prompt(agent, event, context)

            # Call LLM
            response = await self._call_llm(agent, prompt, context)

            # Parse response and extract tool calls
            tool_calls = self._extract_tool_calls(response)

            # Execute tools
            tool_results = []
            for tool_call in tool_calls:
                tool_result = await self.tool_registry.execute_tool(
                    tool_call["tool_name"],
                    tool_call["input"],
                    ToolContext(
                        agent_id=agent.id,
                        execution_id=execution_id,
                        entity_type=event.payload.get("entity_type"),
                        entity_id=event.payload.get("entity_id")
                    )
                )
                tool_results.append(tool_result)

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # Create execution record
            execution = AgentExecution(
                execution_id=execution_id,
                agent_id=agent.id,
                event_id=event.event_id,
                input=event.payload,
                output={"response": response, "tool_results": tool_results},
                status=ExecutionStatus.SUCCESS,
                duration_ms=duration_ms,
                entity_type=event.payload.get("entity_type"),
                entity_id=event.payload.get("entity_id")
            )

            await self._record_execution(execution)

            return execution

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            execution = AgentExecution(
                execution_id=execution_id,
                agent_id=agent.id,
                event_id=event.event_id,
                input=event.payload,
                status=ExecutionStatus.FAILURE,
                error_message=str(e),
                duration_ms=duration_ms
            )

            await self._record_execution(execution)

            raise

    async def _build_agent_context(
        self,
        agent: AgentConfig,
        event: AgentEvent
    ) -> ContextPacket:
        """Build context for agent execution"""
        entity_type = event.payload.get("entity_type")
        entity_id = event.payload.get("entity_id")

        if entity_type == "lead":
            return await self.context_builder.build_context_for_lead(
                int(entity_id),
                event.payload.get("goal", "Process event")
            )
        elif entity_type == "loan":
            return await self.context_builder.build_context_for_loan(
                int(entity_id),
                event.payload.get("goal", "Process event")
            )
        else:
            # Generic context
            return ContextPacket(
                goal=event.payload.get("goal", "Process event"),
                entity_type=entity_type or "unknown",
                entity_id=str(entity_id) if entity_id else "unknown",
                entity_data=event.payload,
                metadata=event.metadata
            )

    async def _build_agent_prompt(
        self,
        agent: AgentConfig,
        event: AgentEvent,
        context: ContextPacket
    ) -> str:
        """Build prompt for agent"""
        # Get latest prompt version for this agent
        prompt_query = text("""
            SELECT prompt_text, system_instructions
            FROM ai_prompt_versions
            WHERE agent_id = :agent_id
            AND status = 'active'
            ORDER BY version DESC
            LIMIT 1
        """)

        result = self.db.execute(prompt_query, {"agent_id": agent.id}).fetchone()

        if result:
            base_prompt = result.prompt_text
            system_instructions = result.system_instructions or ""
        else:
            # Default prompt
            base_prompt = f"""You are {agent.name}, a specialized AI agent.

Your role: {agent.description}

Your goals:
{chr(10).join(f"- {goal}" for goal in agent.goals)}

Available tools:
{chr(10).join(f"- {tool}" for tool in agent.tools)}
"""
            system_instructions = "You are a helpful AI agent in a mortgage CRM system."

        # Add context
        full_prompt = f"""{system_instructions}

{base_prompt}

Current Task:
Event: {event.event_type}
Goal: {context.goal}

Context:
Entity Type: {context.entity_type}
Entity ID: {context.entity_id}

{json.dumps(context.entity_data, indent=2)}

Recent Actions:
{json.dumps(context.prior_ai_actions[:3], indent=2)}

What action should you take?
"""

        return full_prompt

    async def _call_llm(
        self,
        agent: AgentConfig,
        prompt: str,
        context: ContextPacket
    ) -> str:
        """Call LLM for agent reasoning"""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"You are {agent.name}."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )

            return response.choices[0].message.content
        except Exception as e:
            print(f"LLM call failed: {e}")
            return f"Error calling LLM: {e}"

    def _extract_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Extract tool calls from LLM response"""
        # This is a simplified version - in production you'd use function calling
        # or structured output from the LLM
        tool_calls = []

        # Look for patterns like: TOOL: tool_name INPUT: {...}
        # This is where you'd implement proper parsing

        return tool_calls

    async def _record_event(self, event: AgentEvent):
        """Record event in database"""
        query = text("""
            INSERT INTO ai_agent_events (
                event_id, event_type, source, source_agent_id, payload, metadata, status
            ) VALUES (
                :event_id, :event_type, :source, :source_agent_id, :payload, :metadata, :status
            )
        """)

        self.db.execute(query, {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source": event.source,
            "source_agent_id": event.source_agent_id,
            "payload": json.dumps(event.payload),
            "metadata": json.dumps(event.metadata),
            "status": event.status.value
        })
        self.db.commit()

    async def _record_execution(self, execution: AgentExecution):
        """Record execution in database"""
        query = text("""
            INSERT INTO ai_agent_executions (
                execution_id, agent_id, event_id, tool_name, input, output,
                status, error_message, duration_ms, entity_type, entity_id, metadata
            ) VALUES (
                :execution_id, :agent_id, :event_id, :tool_name, :input, :output,
                :status, :error_message, :duration_ms, :entity_type, :entity_id, :metadata
            )
        """)

        self.db.execute(query, {
            "execution_id": execution.execution_id,
            "agent_id": execution.agent_id,
            "event_id": execution.event_id,
            "tool_name": execution.tool_name,
            "input": json.dumps(execution.input),
            "output": json.dumps(execution.output) if execution.output else None,
            "status": execution.status.value,
            "error_message": execution.error_message,
            "duration_ms": execution.duration_ms,
            "entity_type": execution.entity_type,
            "entity_id": execution.entity_id,
            "metadata": json.dumps(execution.metadata)
        })
        self.db.commit()
