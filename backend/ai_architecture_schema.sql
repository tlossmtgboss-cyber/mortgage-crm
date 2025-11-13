-- ============================================================================
-- AI ARCHITECTURE DATABASE SCHEMA
-- Mortgage OS: From Agentic AI → AMAS → Self-Improving → Cognitive → EDWs → AAIO
-- ============================================================================

-- ============================================================================
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
-- PHASE 3: COGNITIVE ARCHITECTURE
-- ============================================================================

-- Long-Term Memory: AI knowledge base
CREATE TABLE IF NOT EXISTS ai_long_term_memory (
    id SERIAL PRIMARY KEY,
    memory_id VARCHAR UNIQUE NOT NULL,
    memory_type VARCHAR NOT NULL, -- 'experience', 'fact', 'pattern', 'reflection', 'sop'
    agent_id VARCHAR REFERENCES ai_agents(id),
    title VARCHAR,
    content TEXT NOT NULL,
    embedding VECTOR(1536), -- For semantic search (if using pgvector)
    entities JSONB, -- Referenced entities: leads, loans, users, etc.
    tags JSONB, -- Categorization tags
    confidence DECIMAL(3,2),
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP,
    relevance_score DECIMAL(5,2),
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_ltm_type ON ai_long_term_memory(memory_type);
CREATE INDEX idx_ai_ltm_agent ON ai_long_term_memory(agent_id);
CREATE INDEX idx_ai_ltm_created ON ai_long_term_memory(created_at);

-- Knowledge Graph Nodes
CREATE TABLE IF NOT EXISTS ai_knowledge_nodes (
    id SERIAL PRIMARY KEY,
    node_id VARCHAR UNIQUE NOT NULL,
    node_type VARCHAR NOT NULL, -- 'lead', 'borrower', 'loan', 'property', 'agent', 'builder', 'partner'
    entity_id VARCHAR NOT NULL, -- Reference to actual entity
    label VARCHAR,
    properties JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_knowledge_nodes_type ON ai_knowledge_nodes(node_type);
CREATE INDEX idx_ai_knowledge_nodes_entity ON ai_knowledge_nodes(entity_id);

-- Knowledge Graph Edges
CREATE TABLE IF NOT EXISTS ai_knowledge_edges (
    id SERIAL PRIMARY KEY,
    edge_id VARCHAR UNIQUE NOT NULL,
    source_node_id VARCHAR NOT NULL REFERENCES ai_knowledge_nodes(node_id),
    target_node_id VARCHAR NOT NULL REFERENCES ai_knowledge_nodes(node_id),
    relationship_type VARCHAR NOT NULL, -- 'referred_by', 'owns', 'applied_for', 'works_with'
    properties JSONB,
    weight DECIMAL(5,2) DEFAULT 1.0, -- Relationship strength
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_knowledge_edges_source ON ai_knowledge_edges(source_node_id);
CREATE INDEX idx_ai_knowledge_edges_target ON ai_knowledge_edges(target_node_id);
CREATE INDEX idx_ai_knowledge_edges_type ON ai_knowledge_edges(relationship_type);

-- Reflections: AI self-analysis after workflows
CREATE TABLE IF NOT EXISTS ai_reflections (
    id SERIAL PRIMARY KEY,
    reflection_id VARCHAR UNIQUE NOT NULL,
    agent_id VARCHAR NOT NULL REFERENCES ai_agents(id),
    execution_id VARCHAR REFERENCES ai_agent_executions(execution_id),
    workflow_name VARCHAR,
    what_worked TEXT,
    what_failed TEXT,
    what_to_change TEXT,
    lessons_learned JSONB,
    applied_to_memory BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_reflections_agent ON ai_reflections(agent_id);
CREATE INDEX idx_ai_reflections_created ON ai_reflections(created_at);

-- ============================================================================
-- PHASE 4: ENTERPRISE DIGITAL WORKERS (EDWs)
-- ============================================================================

-- Digital Worker Profiles
CREATE TABLE IF NOT EXISTS ai_digital_workers (
    id SERIAL PRIMARY KEY,
    worker_id VARCHAR UNIQUE NOT NULL,
    agent_id VARCHAR UNIQUE NOT NULL REFERENCES ai_agents(id),
    job_title VARCHAR NOT NULL,
    department VARCHAR, -- 'sales', 'operations', 'underwriting', 'portfolio', 'customer_success'
    manager_user_id INTEGER REFERENCES users(id),
    responsibilities JSONB, -- Array of responsibility descriptions
    permissions JSONB, -- Subset of tools/data access
    status VARCHAR DEFAULT 'active', -- 'active', 'on_leave', 'terminated'
    hire_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_digital_workers_dept ON ai_digital_workers(department);
CREATE INDEX idx_ai_digital_workers_manager ON ai_digital_workers(manager_user_id);

-- Digital Worker KPIs
CREATE TABLE IF NOT EXISTS ai_worker_kpis (
    id SERIAL PRIMARY KEY,
    worker_id VARCHAR NOT NULL REFERENCES ai_digital_workers(worker_id),
    kpi_name VARCHAR NOT NULL,
    kpi_target DECIMAL(10,2) NOT NULL,
    kpi_unit VARCHAR NOT NULL, -- 'count', 'percent', 'time_minutes', 'dollar'
    period VARCHAR DEFAULT 'weekly', -- 'daily', 'weekly', 'monthly', 'quarterly'
    current_value DECIMAL(10,2),
    status VARCHAR, -- 'on_track', 'at_risk', 'missed', 'exceeded'
    period_start TIMESTAMP,
    period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_worker_kpis_worker ON ai_worker_kpis(worker_id);
CREATE INDEX idx_ai_worker_kpis_period ON ai_worker_kpis(period_start, period_end);

-- Digital Worker Reports
CREATE TABLE IF NOT EXISTS ai_worker_reports (
    id SERIAL PRIMARY KEY,
    report_id VARCHAR UNIQUE NOT NULL,
    worker_id VARCHAR NOT NULL REFERENCES ai_digital_workers(worker_id),
    report_type VARCHAR NOT NULL, -- 'daily', 'weekly', 'monthly', 'incident'
    report_period_start TIMESTAMP,
    report_period_end TIMESTAMP,
    summary TEXT,
    accomplishments JSONB,
    challenges JSONB,
    escalations JSONB,
    kpi_performance JSONB,
    next_priorities JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_worker_reports_worker ON ai_worker_reports(worker_id);
CREATE INDEX idx_ai_worker_reports_type ON ai_worker_reports(report_type);
CREATE INDEX idx_ai_worker_reports_created ON ai_worker_reports(created_at);

-- ============================================================================
-- PHASE 5: AUTONOMOUS AI ORGANIZATION (AAIO)
-- ============================================================================

-- AI Leadership Roles
CREATE TABLE IF NOT EXISTS ai_leadership_roles (
    id SERIAL PRIMARY KEY,
    role_id VARCHAR UNIQUE NOT NULL,
    agent_id VARCHAR UNIQUE NOT NULL REFERENCES ai_agents(id),
    title VARCHAR NOT NULL, -- 'AI COO', 'AI CCO', 'AI CRO', 'AI CHRO', 'AI CPO'
    department VARCHAR, -- 'operations', 'customer', 'revenue', 'hr', 'product'
    scope JSONB, -- Areas of responsibility
    managed_workers JSONB, -- Array of worker_ids this role manages
    decision_authority VARCHAR, -- 'advisory', 'limited', 'full'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_leadership_roles_dept ON ai_leadership_roles(department);

-- Strategic Initiatives: AI-proposed business strategies
CREATE TABLE IF NOT EXISTS ai_strategic_initiatives (
    id SERIAL PRIMARY KEY,
    initiative_id VARCHAR UNIQUE NOT NULL,
    proposed_by_agent_id VARCHAR NOT NULL REFERENCES ai_agents(id),
    title VARCHAR NOT NULL,
    description TEXT,
    category VARCHAR, -- 'efficiency', 'revenue', 'customer_experience', 'risk_mitigation'
    priority VARCHAR DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    estimated_impact JSONB, -- Expected outcomes, metrics
    resources_required JSONB,
    timeline JSONB,
    status VARCHAR DEFAULT 'proposed', -- 'proposed', 'approved', 'in_progress', 'completed', 'rejected'
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    owner_agent_id VARCHAR REFERENCES ai_agents(id),
    progress JSONB,
    results JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_ai_strategic_initiatives_status ON ai_strategic_initiatives(status);
CREATE INDEX idx_ai_strategic_initiatives_category ON ai_strategic_initiatives(category);

-- System Health: Overall AI org performance
CREATE TABLE IF NOT EXISTS ai_system_health (
    id SERIAL PRIMARY KEY,
    snapshot_id VARCHAR UNIQUE NOT NULL,
    snapshot_date TIMESTAMP NOT NULL,
    overall_status VARCHAR, -- 'healthy', 'degraded', 'critical'
    total_agents INTEGER,
    active_agents INTEGER,
    total_executions INTEGER,
    success_rate DECIMAL(5,2),
    avg_response_time_ms INTEGER,
    total_cost_usd DECIMAL(10,2),
    kpis_on_track INTEGER,
    kpis_at_risk INTEGER,
    open_escalations INTEGER,
    agent_metrics JSONB, -- Per-agent summary
    leadership_summary TEXT,
    recommendations JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_system_health_date ON ai_system_health(snapshot_date);

-- ============================================================================
-- VIEWS FOR QUICK ACCESS
-- ============================================================================

-- Active Agents Summary
CREATE OR REPLACE VIEW v_active_agents AS
SELECT
    a.id,
    a.name,
    a.agent_type,
    a.status,
    COUNT(DISTINCT ae.id) as total_executions,
    AVG(ae.duration_ms) as avg_duration_ms,
    SUM(CASE WHEN ae.status = 'success' THEN 1 ELSE 0 END)::DECIMAL / NULLIF(COUNT(ae.id), 0) * 100 as success_rate,
    MAX(ae.created_at) as last_execution
FROM ai_agents a
LEFT JOIN ai_agent_executions ae ON a.id = ae.agent_id AND ae.created_at > NOW() - INTERVAL '7 days'
WHERE a.status = 'active'
GROUP BY a.id, a.name, a.agent_type, a.status;

-- Pending Agent Messages
CREATE OR REPLACE VIEW v_pending_agent_messages AS
SELECT
    m.id,
    m.message_id,
    m.from_agent_id,
    fa.name as from_agent_name,
    m.to_agent_id,
    ta.name as to_agent_name,
    m.message_type,
    m.subject,
    m.priority,
    m.requires_human_review,
    m.created_at
FROM ai_agent_messages m
JOIN ai_agents fa ON m.from_agent_id = fa.id
LEFT JOIN ai_agents ta ON m.to_agent_id = ta.id
WHERE m.status = 'pending'
ORDER BY
    CASE m.priority
        WHEN 'urgent' THEN 1
        WHEN 'high' THEN 2
        WHEN 'normal' THEN 3
        WHEN 'low' THEN 4
    END,
    m.created_at;

-- Digital Worker Performance
CREATE OR REPLACE VIEW v_worker_performance AS
SELECT
    w.worker_id,
    w.job_title,
    w.department,
    COUNT(DISTINCT k.id) as total_kpis,
    SUM(CASE WHEN k.status = 'on_track' OR k.status = 'exceeded' THEN 1 ELSE 0 END) as kpis_met,
    COUNT(DISTINCT ae.id) as total_tasks,
    AVG(ae.confidence_score) as avg_confidence,
    MAX(ae.created_at) as last_activity
FROM ai_digital_workers w
LEFT JOIN ai_worker_kpis k ON w.worker_id = k.worker_id AND k.period_end > NOW()
LEFT JOIN ai_agent_executions ae ON w.agent_id = ae.agent_id AND ae.created_at > NOW() - INTERVAL '7 days'
WHERE w.status = 'active'
GROUP BY w.worker_id, w.job_title, w.department;

-- Self-Improvement Pipeline
CREATE OR REPLACE VIEW v_improvement_pipeline AS
SELECT
    f.finding_id,
    f.finding_type,
    f.severity,
    f.title,
    f.affected_agent_id,
    a.name as agent_name,
    f.estimated_impact,
    f.status,
    f.created_at
FROM ai_audit_findings f
LEFT JOIN ai_agents a ON f.affected_agent_id = a.id
WHERE f.status IN ('pending', 'approved')
ORDER BY
    CASE f.severity
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        WHEN 'low' THEN 4
    END,
    f.created_at;
