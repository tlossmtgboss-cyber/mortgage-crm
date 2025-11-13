-- PHASE 1: AUTONOMOUS MULTI-AGENT SYSTEM (AMAS)
-- ============================================================================

-- Agent Registry: Store all agent configurations
CREATE TABLE IF NOT EXISTS ai_agents (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    description TEXT,
    agent_type VARCHAR NOT NULL, -- 'specialized', 'meta', 'leadership'
    status VARCHAR DEFAULT 'active', -- 'active', 'paused', 'archived'
    goals JSONB, -- Array of goal strings
    tools JSONB, -- Array of allowed tool names
    triggers JSONB, -- Array of event types this agent listens to
    config JSONB, -- Agent-specific configuration
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    manager_user_id INTEGER REFERENCES users(id) -- Human manager (Phase 4)
);

CREATE INDEX idx_ai_agents_type ON ai_agents(agent_type);
CREATE INDEX idx_ai_agents_status ON ai_agents(status);

-- Tool Registry: Define all available tools agents can call
CREATE TABLE IF NOT EXISTS ai_tools (
    id SERIAL PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL,
    description TEXT,
    category VARCHAR, -- 'data_read', 'data_write', 'communication', 'analysis', 'workflow'
    input_schema JSONB, -- JSON Schema for input validation
    output_schema JSONB, -- JSON Schema for output
    handler_endpoint VARCHAR, -- API endpoint or function name
    allowed_agents JSONB, -- Array of agent IDs that can use this tool
    risk_level VARCHAR DEFAULT 'low', -- 'low', 'medium', 'high'
    requires_approval BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    execution_count INTEGER DEFAULT 0,
    avg_duration_ms INTEGER,
    success_rate DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_tools_name ON ai_tools(name);
CREATE INDEX idx_ai_tools_category ON ai_tools(category);
CREATE INDEX idx_ai_tools_active ON ai_tools(is_active);

-- Agent Events: Event bus for agent triggers
CREATE TABLE IF NOT EXISTS ai_agent_events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR UNIQUE NOT NULL,
    event_type VARCHAR NOT NULL, -- 'LeadCreated', 'LoanStageChanged', etc.
    source VARCHAR NOT NULL, -- 'system', 'user', 'webhook', 'agent'
    source_agent_id VARCHAR REFERENCES ai_agents(id),
    payload JSONB,
    metadata JSONB,
    status VARCHAR DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed'
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_agent_events_type ON ai_agent_events(event_type);
CREATE INDEX idx_ai_agent_events_status ON ai_agent_events(status);
CREATE INDEX idx_ai_agent_events_created ON ai_agent_events(created_at);

-- Agent Messages: Inter-agent communication
CREATE TABLE IF NOT EXISTS ai_agent_messages (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR UNIQUE NOT NULL,
    from_agent_id VARCHAR REFERENCES ai_agents(id),
    to_agent_id VARCHAR REFERENCES ai_agents(id),
    message_type VARCHAR NOT NULL, -- 'request', 'response', 'broadcast', 'escalation'
    subject VARCHAR,
    content TEXT,
    payload JSONB,
    priority VARCHAR DEFAULT 'normal', -- 'low', 'normal', 'high', 'urgent'
    status VARCHAR DEFAULT 'pending', -- 'pending', 'read', 'processed', 'archived'
    parent_message_id INTEGER REFERENCES ai_agent_messages(id),
    requires_human_review BOOLEAN DEFAULT FALSE,
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_agent_messages_from ON ai_agent_messages(from_agent_id);
CREATE INDEX idx_ai_agent_messages_to ON ai_agent_messages(to_agent_id);
CREATE INDEX idx_ai_agent_messages_status ON ai_agent_messages(status);
CREATE INDEX idx_ai_agent_messages_created ON ai_agent_messages(created_at);

-- Agent Execution Logs: Track all agent actions
CREATE TABLE IF NOT EXISTS ai_agent_executions (
    id SERIAL PRIMARY KEY,
    execution_id VARCHAR UNIQUE NOT NULL,
    agent_id VARCHAR NOT NULL REFERENCES ai_agents(id),
    event_id VARCHAR REFERENCES ai_agent_events(event_id),
    tool_name VARCHAR,
    input JSONB,
    output JSONB,
    status VARCHAR NOT NULL, -- 'success', 'failure', 'partial', 'timeout'
    error_message TEXT,
    duration_ms INTEGER,
    tokens_used INTEGER,
    cost_usd DECIMAL(10,4),
    confidence_score DECIMAL(3,2), -- 0.00 to 1.00
    user_feedback VARCHAR, -- 'positive', 'negative', 'neutral'
    user_feedback_comment TEXT,
    user_id INTEGER REFERENCES users(id), -- User who provided feedback
    entity_type VARCHAR, -- 'lead', 'loan', 'borrower', etc.
    entity_id VARCHAR,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_agent_executions_agent ON ai_agent_executions(agent_id);
CREATE INDEX idx_ai_agent_executions_tool ON ai_agent_executions(tool_name);
CREATE INDEX idx_ai_agent_executions_status ON ai_agent_executions(status);
CREATE INDEX idx_ai_agent_executions_created ON ai_agent_executions(created_at);
CREATE INDEX idx_ai_agent_executions_entity ON ai_agent_executions(entity_type, entity_id);

-- Agent State: Persistent state for each agent
CREATE TABLE IF NOT EXISTS ai_agent_state (
    id SERIAL PRIMARY KEY,
    agent_id VARCHAR NOT NULL REFERENCES ai_agents(id),
    state_key VARCHAR NOT NULL,
    state_value JSONB,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_id, state_key)
);

CREATE INDEX idx_ai_agent_state_agent ON ai_agent_state(agent_id);
CREATE INDEX idx_ai_agent_state_key ON ai_agent_state(state_key);

-- ============================================================================
-- PHASE 2: SELF-IMPROVING AI SYSTEM
-- ============================================================================

-- Prompt Versions: Track agent prompt evolution
CREATE TABLE IF NOT EXISTS ai_prompt_versions (
    id SERIAL PRIMARY KEY,
    agent_id VARCHAR NOT NULL REFERENCES ai_agents(id),
    version INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    system_instructions TEXT,
    tool_selection_strategy JSONB,
    routing_rules JSONB,
    status VARCHAR DEFAULT 'draft', -- 'draft', 'testing', 'active', 'archived'
    performance_metrics JSONB, -- Success rate, avg confidence, etc.
    created_by INTEGER REFERENCES users(id),
    activated_at TIMESTAMP,
    deactivated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_id, version)
);

CREATE INDEX idx_ai_prompt_versions_agent ON ai_prompt_versions(agent_id);
CREATE INDEX idx_ai_prompt_versions_status ON ai_prompt_versions(status);

-- Self-Audit Findings: AI-generated improvement proposals
CREATE TABLE IF NOT EXISTS ai_audit_findings (
    id SERIAL PRIMARY KEY,
    finding_id VARCHAR UNIQUE NOT NULL,
    finding_type VARCHAR NOT NULL, -- 'bottleneck', 'prompt_issue', 'missing_tool', 'schema_change'
    severity VARCHAR, -- 'low', 'medium', 'high', 'critical'
    title VARCHAR NOT NULL,
    description TEXT,
    affected_agent_id VARCHAR REFERENCES ai_agents(id),
    affected_tool_name VARCHAR,
    evidence JSONB, -- Logs, metrics supporting this finding
    proposed_solution TEXT,
    proposed_changes JSONB, -- Specific diffs or configs
    estimated_impact VARCHAR, -- 'low', 'medium', 'high'
    status VARCHAR DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'implemented'
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_notes TEXT,
    implemented_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_audit_findings_type ON ai_audit_findings(finding_type);
CREATE INDEX idx_ai_audit_findings_status ON ai_audit_findings(status);
CREATE INDEX idx_ai_audit_findings_agent ON ai_audit_findings(affected_agent_id);

-- Improvement Cycles: Track self-improvement iterations
CREATE TABLE IF NOT EXISTS ai_improvement_cycles (
    id SERIAL PRIMARY KEY,
    cycle_id VARCHAR UNIQUE NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    findings_count INTEGER DEFAULT 0,
    approved_count INTEGER DEFAULT 0,
    implemented_count INTEGER DEFAULT 0,
    performance_delta JSONB, -- Before/after metrics
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_improvement_cycles_start ON ai_improvement_cycles(start_date);

-- ============================================================================
