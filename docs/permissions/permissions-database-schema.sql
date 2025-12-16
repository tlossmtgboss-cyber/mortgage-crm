-- ============================================================================
-- Perennia AI - Stage-Based Permissions Database Schema
-- ============================================================================
-- This schema supports:
-- 1. Subscription-based licensing (Lead, Active Loan, Portfolio stages)
-- 2. Role-based access control within each stage
-- 3. Permission templates per role
-- 4. Individual permission overrides
-- 5. Full audit logging
-- ============================================================================

-- ============================================================================
-- PART 1: SUBSCRIPTION & STAGE MANAGEMENT
-- ============================================================================

-- Subscription tiers (Starter, Professional, Enterprise, Custom)
CREATE TABLE subscription_tiers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    stages JSONB NOT NULL DEFAULT '[]',  -- ['lead', 'active_loan', 'portfolio']
    features JSONB NOT NULL DEFAULT '{}',
    price_monthly DECIMAL(10,2),
    price_annual DECIMAL(10,2),
    max_users INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default subscription tiers
INSERT INTO subscription_tiers (name, description, stages, features, max_users) VALUES
('Starter', 'Lead management only', '["lead"]',
 '{"maxLeads": 1000, "aiAssistant": false, "advancedAnalytics": false}', 5),
('Professional', 'Lead and active loan management', '["lead", "active_loan"]',
 '{"maxLeads": 5000, "maxLoans": 500, "aiAssistant": true, "advancedAnalytics": false}', 25),
('Enterprise', 'Full platform access', '["lead", "active_loan", "portfolio"]',
 '{"maxLeads": -1, "maxLoans": -1, "aiAssistant": true, "advancedAnalytics": true, "apiAccess": true}', -1),
('Custom', 'Custom stage selection', '[]',
 '{"customizable": true}', -1);

-- Organization subscriptions
CREATE TABLE organization_subscriptions (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    subscription_tier_id INTEGER REFERENCES subscription_tiers(id),
    -- Override stages for custom subscriptions
    enabled_stages JSONB NOT NULL DEFAULT '[]',  -- ['lead', 'active_loan', 'portfolio']
    -- Subscription status
    status VARCHAR(50) DEFAULT 'active',  -- active, trial, suspended, cancelled
    trial_ends_at TIMESTAMP,
    billing_cycle VARCHAR(20) DEFAULT 'monthly',  -- monthly, annual
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    -- Usage tracking
    current_user_count INTEGER DEFAULT 0,
    -- Metadata
    stripe_subscription_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(organization_id)
);

-- Create index for subscription lookups
CREATE INDEX idx_org_subscriptions_org ON organization_subscriptions(organization_id);
CREATE INDEX idx_org_subscriptions_status ON organization_subscriptions(status);

-- ============================================================================
-- PART 2: LOAN STAGES DEFINITION
-- ============================================================================

-- Define the three core stages
CREATE TABLE loan_stages (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,  -- 'lead', 'active_loan', 'portfolio'
    name VARCHAR(100) NOT NULL,
    description TEXT,
    display_order INTEGER DEFAULT 0,
    icon VARCHAR(50),
    color VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert the three core stages
INSERT INTO loan_stages (code, name, description, display_order, icon, color) VALUES
('lead', 'Lead Management', 'Lead intake, qualification, and nurturing', 1, 'UserPlus', '#3B82F6'),
('active_loan', 'Active Loan', 'Loan processing, underwriting, and closing', 2, 'FileText', '#10B981'),
('portfolio', 'Portfolio', 'Client retention, MUM, and referral management', 3, 'Briefcase', '#8B5CF6');

-- ============================================================================
-- PART 3: PERMISSION DEFINITIONS
-- ============================================================================

-- Master list of all permissions
CREATE TABLE permission_definitions (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) NOT NULL UNIQUE,  -- e.g., 'lead.intake.view_all'
    stage_code VARCHAR(50) REFERENCES loan_stages(code),  -- NULL for cross-stage permissions
    category VARCHAR(100) NOT NULL,  -- e.g., 'intake', 'processing', 'analytics'
    name VARCHAR(255) NOT NULL,
    description TEXT,
    -- Permission metadata
    requires_subscription BOOLEAN DEFAULT TRUE,  -- Some permissions always available
    risk_level VARCHAR(20) DEFAULT 'low',  -- low, medium, high, critical
    -- UI metadata
    display_order INTEGER DEFAULT 0,
    group_name VARCHAR(100),  -- For UI grouping
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for permission lookups
CREATE INDEX idx_permission_defs_key ON permission_definitions(key);
CREATE INDEX idx_permission_defs_stage ON permission_definitions(stage_code);
CREATE INDEX idx_permission_defs_category ON permission_definitions(category);

-- ============================================================================
-- PART 4: PERMISSION TEMPLATES (ROLE-BASED)
-- ============================================================================

-- Permission templates organized by stage and role
CREATE TABLE stage_permission_templates (
    id SERIAL PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,  -- e.g., 'lead_admin', 'loan_processor'
    name VARCHAR(255) NOT NULL,
    description TEXT,
    -- Stage association
    stage_code VARCHAR(50) REFERENCES loan_stages(code),  -- NULL for cross-stage templates
    -- Role type
    role_type VARCHAR(50) NOT NULL,  -- 'admin', 'standard', 'readonly', 'processor', etc.
    -- Permissions granted by this template
    permissions JSONB NOT NULL DEFAULT '{}',  -- {"permission_key": true/false}
    -- Data scope defaults
    default_scope VARCHAR(50) DEFAULT 'assigned',  -- all, team, territory, branch, assigned
    -- Template metadata
    is_system_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    -- Audit
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for template lookups
CREATE INDEX idx_stage_templates_code ON stage_permission_templates(code);
CREATE INDEX idx_stage_templates_stage ON stage_permission_templates(stage_code);

-- ============================================================================
-- PART 5: USER STAGE ACCESS & PERMISSIONS
-- ============================================================================

-- User stage access (which stages a user can access)
CREATE TABLE user_stage_access (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stage_code VARCHAR(50) NOT NULL REFERENCES loan_stages(code),
    -- Access type
    access_type VARCHAR(50) DEFAULT 'subscription',  -- subscription, granted, trial
    -- Template applied for this stage
    template_id INTEGER REFERENCES stage_permission_templates(id),
    -- Data scope for this stage
    data_scope VARCHAR(50) DEFAULT 'assigned',  -- all, team, territory, branch, assigned
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by INTEGER REFERENCES users(id),
    expires_at TIMESTAMP,  -- For temporary access
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, stage_code)
);

-- Create indexes
CREATE INDEX idx_user_stage_access_user ON user_stage_access(user_id);
CREATE INDEX idx_user_stage_access_stage ON user_stage_access(stage_code);
CREATE INDEX idx_user_stage_access_active ON user_stage_access(user_id, is_active);

-- Individual permission overrides (beyond template)
CREATE TABLE user_permission_overrides (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_key VARCHAR(255) NOT NULL,
    -- Override value
    granted BOOLEAN NOT NULL,
    -- Scope override
    scope_override VARCHAR(50),  -- NULL means use template default
    -- Temporary grant
    is_temporary BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP,
    -- Reason for override
    reason TEXT,
    -- Audit
    granted_by INTEGER REFERENCES users(id),
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, permission_key)
);

-- Create indexes
CREATE INDEX idx_user_perm_overrides_user ON user_permission_overrides(user_id);
CREATE INDEX idx_user_perm_overrides_key ON user_permission_overrides(permission_key);
CREATE INDEX idx_user_perm_overrides_expires ON user_permission_overrides(expires_at)
    WHERE expires_at IS NOT NULL;

-- ============================================================================
-- PART 6: PERMISSION REQUEST WORKFLOW
-- ============================================================================

-- Permission requests (self-service)
CREATE TABLE stage_permission_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- What they're requesting
    request_type VARCHAR(50) NOT NULL,  -- 'stage_access', 'permission', 'template_change', 'scope_upgrade'
    stage_code VARCHAR(50) REFERENCES loan_stages(code),
    permission_key VARCHAR(255),
    template_id INTEGER REFERENCES stage_permission_templates(id),
    requested_scope VARCHAR(50),
    -- Request details
    justification TEXT NOT NULL,
    urgency VARCHAR(20) DEFAULT 'medium',  -- low, medium, high, critical
    is_temporary BOOLEAN DEFAULT FALSE,
    duration_days INTEGER,
    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, approved, denied, more_info, cancelled
    -- Manager response
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_notes TEXT,
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_stage_perm_requests_user ON stage_permission_requests(user_id);
CREATE INDEX idx_stage_perm_requests_status ON stage_permission_requests(status);
CREATE INDEX idx_stage_perm_requests_pending ON stage_permission_requests(status)
    WHERE status = 'pending';

-- ============================================================================
-- PART 7: AUDIT LOGGING
-- ============================================================================

-- Comprehensive permission audit log
CREATE TABLE permission_audit_log (
    id SERIAL PRIMARY KEY,
    -- Who and when
    user_id INTEGER NOT NULL REFERENCES users(id),
    actor_id INTEGER REFERENCES users(id),  -- Who made the change
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- What changed
    action VARCHAR(50) NOT NULL,  -- grant, revoke, modify, template_apply, stage_enable, stage_disable
    entity_type VARCHAR(50) NOT NULL,  -- stage_access, permission, template, scope
    entity_id VARCHAR(255),  -- The specific permission/stage/template
    -- Change details
    previous_value JSONB,
    new_value JSONB,
    -- Context
    reason TEXT,
    request_id INTEGER REFERENCES stage_permission_requests(id),
    -- Request metadata
    ip_address INET,
    user_agent TEXT,
    session_id VARCHAR(255)
);

-- Create indexes for audit queries
CREATE INDEX idx_perm_audit_user ON permission_audit_log(user_id);
CREATE INDEX idx_perm_audit_actor ON permission_audit_log(actor_id);
CREATE INDEX idx_perm_audit_timestamp ON permission_audit_log(timestamp);
CREATE INDEX idx_perm_audit_action ON permission_audit_log(action);

-- ============================================================================
-- PART 8: PERMISSION CONFLICTS (SEPARATION OF DUTIES)
-- ============================================================================

-- Define conflicting permissions that shouldn't be held together
CREATE TABLE permission_conflicts (
    id SERIAL PRIMARY KEY,
    permission_a VARCHAR(255) NOT NULL,
    permission_b VARCHAR(255) NOT NULL,
    conflict_type VARCHAR(50) NOT NULL,  -- 'hard' (never allowed), 'soft' (warning)
    description TEXT NOT NULL,
    risk_level VARCHAR(20) NOT NULL,  -- low, medium, high, critical
    resolution_options JSONB,  -- Suggested resolutions
    requires_approval_level VARCHAR(50),  -- 'manager', 'director', 'executive'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(permission_a, permission_b)
);

-- ============================================================================
-- PART 9: SEED DEFAULT PERMISSIONS
-- ============================================================================

-- Lead Stage Permissions
INSERT INTO permission_definitions (key, stage_code, category, name, description, display_order) VALUES
-- Lead Intake
('lead.intake.view_all', 'lead', 'intake', 'View All Leads', 'View all leads in the system', 1),
('lead.intake.view_team', 'lead', 'intake', 'View Team Leads', 'View leads assigned to team members', 2),
('lead.intake.view_assigned', 'lead', 'intake', 'View Assigned Leads', 'View only assigned leads', 3),
('lead.intake.create', 'lead', 'intake', 'Create Leads', 'Create new leads', 4),
('lead.intake.edit_all', 'lead', 'intake', 'Edit All Leads', 'Edit any lead', 5),
('lead.intake.edit_own', 'lead', 'intake', 'Edit Own Leads', 'Edit only assigned leads', 6),
('lead.intake.delete', 'lead', 'intake', 'Delete Leads', 'Delete leads from the system', 7),
('lead.intake.import', 'lead', 'intake', 'Import Leads', 'Bulk import leads', 8),
('lead.intake.export', 'lead', 'intake', 'Export Leads', 'Export lead data', 9),
-- Lead Assignment
('lead.assignment.assign', 'lead', 'assignment', 'Assign Leads', 'Assign leads to team members', 10),
('lead.assignment.reassign', 'lead', 'assignment', 'Reassign Leads', 'Reassign leads between users', 11),
('lead.assignment.view_pool', 'lead', 'assignment', 'View Lead Pool', 'View unassigned lead pool', 12),
('lead.assignment.claim', 'lead', 'assignment', 'Claim Leads', 'Claim leads from the pool', 13),
-- Lead Communication
('lead.communication.email', 'lead', 'communication', 'Send Emails', 'Send emails to leads', 14),
('lead.communication.sms', 'lead', 'communication', 'Send SMS', 'Send text messages to leads', 15),
('lead.communication.call', 'lead', 'communication', 'Make Calls', 'Use dialer to call leads', 16),
('lead.communication.view_history', 'lead', 'communication', 'View History', 'View communication history', 17),
-- Lead Qualification
('lead.qualification.credit_check', 'lead', 'qualification', 'Run Credit Checks', 'Run soft/hard credit checks', 18),
('lead.qualification.pre_qualify', 'lead', 'qualification', 'Pre-Qualify Leads', 'Pre-qualify leads for loans', 19),
('lead.qualification.update_status', 'lead', 'qualification', 'Update Status', 'Update lead status', 20),
('lead.qualification.add_notes', 'lead', 'qualification', 'Add Notes', 'Add notes to leads', 21),
-- Lead Analytics
('lead.analytics.view_metrics', 'lead', 'analytics', 'View Metrics', 'View lead metrics', 22),
('lead.analytics.view_conversion', 'lead', 'analytics', 'View Conversion Rates', 'View conversion analytics', 23),
('lead.analytics.view_sources', 'lead', 'analytics', 'View Source Performance', 'View lead source analytics', 24),
-- Lead Automation
('lead.automation.workflows', 'lead', 'automation', 'Configure Workflows', 'Configure lead workflows', 25),
('lead.automation.campaigns', 'lead', 'automation', 'Manage Campaigns', 'Manage drip campaigns', 26),
('lead.automation.auto_assignment', 'lead', 'automation', 'Auto-Assignment Rules', 'Configure auto-assignment', 27);

-- Active Loan Stage Permissions
INSERT INTO permission_definitions (key, stage_code, category, name, description, display_order) VALUES
-- Loan Pipeline
('loan.pipeline.view_all', 'active_loan', 'pipeline', 'View All Loans', 'View all loans in pipeline', 1),
('loan.pipeline.view_team', 'active_loan', 'pipeline', 'View Team Loans', 'View team loans', 2),
('loan.pipeline.view_assigned', 'active_loan', 'pipeline', 'View Assigned Loans', 'View only assigned loans', 3),
('loan.pipeline.create', 'active_loan', 'pipeline', 'Create Loan Files', 'Create new loan files', 4),
('loan.pipeline.edit_all', 'active_loan', 'pipeline', 'Edit All Loans', 'Edit any loan', 5),
('loan.pipeline.edit_own', 'active_loan', 'pipeline', 'Edit Own Loans', 'Edit only assigned loans', 6),
('loan.pipeline.delete', 'active_loan', 'pipeline', 'Delete Loans', 'Delete loan files', 7),
-- Loan Processing
('loan.processing.upload_docs', 'active_loan', 'processing', 'Upload Documents', 'Upload loan documents', 8),
('loan.processing.request_docs', 'active_loan', 'processing', 'Request Documents', 'Request documents from borrower', 9),
('loan.processing.verify_docs', 'active_loan', 'processing', 'Verify Documents', 'Verify document authenticity', 10),
('loan.processing.order_services', 'active_loan', 'processing', 'Order Services', 'Order appraisal, title, etc.', 11),
-- Underwriting
('loan.underwriting.submit', 'active_loan', 'underwriting', 'Submit to UW', 'Submit loans to underwriting', 12),
('loan.underwriting.view_conditions', 'active_loan', 'underwriting', 'View Conditions', 'View underwriting conditions', 13),
('loan.underwriting.clear_conditions', 'active_loan', 'underwriting', 'Clear Conditions', 'Clear underwriting conditions', 14),
('loan.underwriting.approve', 'active_loan', 'underwriting', 'Approve Loans', 'Approve loan applications', 15),
('loan.underwriting.deny', 'active_loan', 'underwriting', 'Deny Loans', 'Deny loan applications', 16),
('loan.underwriting.suspend', 'active_loan', 'underwriting', 'Suspend Loans', 'Suspend loan processing', 17),
-- Closing
('loan.closing.generate_disclosures', 'active_loan', 'closing', 'Generate Disclosures', 'Generate loan disclosures', 18),
('loan.closing.schedule', 'active_loan', 'closing', 'Schedule Closing', 'Schedule loan closing', 19),
('loan.closing.clear_to_close', 'active_loan', 'closing', 'Clear to Close', 'Mark loans clear to close', 20),
('loan.closing.record_funding', 'active_loan', 'closing', 'Record Funding', 'Record loan funding', 21),
-- Rate Lock
('loan.rate_lock.view', 'active_loan', 'rate_lock', 'View Rates', 'View current rates', 22),
('loan.rate_lock.lock', 'active_loan', 'rate_lock', 'Lock Rates', 'Lock interest rates', 23),
('loan.rate_lock.extend', 'active_loan', 'rate_lock', 'Extend Locks', 'Extend rate locks', 24),
('loan.rate_lock.relock', 'active_loan', 'rate_lock', 'Re-Lock Rates', 'Re-lock at new rates', 25),
-- Loan Analytics
('loan.analytics.view_pipeline', 'active_loan', 'analytics', 'View Pipeline Metrics', 'View pipeline analytics', 26),
('loan.analytics.view_pull_through', 'active_loan', 'analytics', 'View Pull-Through', 'View pull-through rates', 27),
('loan.analytics.view_cycle_times', 'active_loan', 'analytics', 'View Cycle Times', 'View processing cycle times', 28),
-- Compliance
('loan.compliance.run_checks', 'active_loan', 'compliance', 'Run Compliance Checks', 'Run compliance checks', 29),
('loan.compliance.view_audit', 'active_loan', 'compliance', 'View Audit Logs', 'View compliance audit logs', 30),
('loan.compliance.generate_reports', 'active_loan', 'compliance', 'Generate Reports', 'Generate compliance reports', 31);

-- Portfolio Stage Permissions
INSERT INTO permission_definitions (key, stage_code, category, name, description, display_order) VALUES
-- Client Management
('portfolio.clients.view_all', 'portfolio', 'clients', 'View All Clients', 'View all portfolio clients', 1),
('portfolio.clients.view_own', 'portfolio', 'clients', 'View Own Clients', 'View only own clients', 2),
('portfolio.clients.edit', 'portfolio', 'clients', 'Edit Clients', 'Edit client information', 3),
('portfolio.clients.add_notes', 'portfolio', 'clients', 'Add Notes', 'Add client notes', 4),
('portfolio.clients.view_history', 'portfolio', 'clients', 'View History', 'View client loan history', 5),
-- MUM
('portfolio.mum.view_dashboard', 'portfolio', 'mum', 'View MUM Dashboard', 'View MUM dashboard', 6),
('portfolio.mum.view_equity', 'portfolio', 'mum', 'View Equity Positions', 'View client equity', 7),
('portfolio.mum.view_rate_watch', 'portfolio', 'mum', 'View Rate Watch', 'View rate watch alerts', 8),
('portfolio.mum.send_offers', 'portfolio', 'mum', 'Send Offers', 'Send refinance offers', 9),
-- Campaigns
('portfolio.campaigns.create', 'portfolio', 'campaigns', 'Create Campaigns', 'Create retention campaigns', 10),
('portfolio.campaigns.execute', 'portfolio', 'campaigns', 'Execute Campaigns', 'Execute campaigns', 11),
('portfolio.campaigns.view_results', 'portfolio', 'campaigns', 'View Results', 'View campaign results', 12),
-- Milestones
('portfolio.milestones.view', 'portfolio', 'milestones', 'View Milestones', 'View upcoming milestones', 13),
('portfolio.milestones.send_communications', 'portfolio', 'milestones', 'Send Communications', 'Send milestone messages', 14),
('portfolio.milestones.configure', 'portfolio', 'milestones', 'Configure', 'Configure auto-messages', 15),
-- Referrals
('portfolio.referrals.view', 'portfolio', 'referrals', 'View Partners', 'View referral partners', 16),
('portfolio.referrals.add', 'portfolio', 'referrals', 'Add Partners', 'Add referral partners', 17),
('portfolio.referrals.track', 'portfolio', 'referrals', 'Track Deals', 'Track referral deals', 18),
('portfolio.referrals.send_thanks', 'portfolio', 'referrals', 'Send Thank Yous', 'Send referral thank yous', 19),
-- Analytics
('portfolio.analytics.view_value', 'portfolio', 'analytics', 'View Portfolio Value', 'View portfolio value', 20),
('portfolio.analytics.view_retention', 'portfolio', 'analytics', 'View Retention Metrics', 'View retention metrics', 21),
('portfolio.analytics.view_ltv', 'portfolio', 'analytics', 'View Lifetime Value', 'View client LTV', 22),
-- Property
('portfolio.property.view_values', 'portfolio', 'property', 'View Property Values', 'View property values', 23),
('portfolio.property.set_alerts', 'portfolio', 'property', 'Set Alerts', 'Set value alerts', 24),
('portfolio.property.view_trends', 'portfolio', 'property', 'View Trends', 'View market trends', 25);

-- Cross-Stage Permissions
INSERT INTO permission_definitions (key, stage_code, category, name, description, requires_subscription, display_order) VALUES
-- Dashboard
('dashboard.view', NULL, 'dashboard', 'View Dashboard', 'View main dashboard', FALSE, 1),
('dashboard.customize', NULL, 'dashboard', 'Customize Dashboard', 'Customize dashboard layout', FALSE, 2),
-- Profile
('profile.view', NULL, 'profile', 'View Profile', 'View own profile', FALSE, 3),
('profile.edit', NULL, 'profile', 'Edit Profile', 'Edit own profile', FALSE, 4),
-- Team
('team.view_members', NULL, 'team', 'View Team', 'View team members', TRUE, 5),
('team.view_performance', NULL, 'team', 'View Performance', 'View team performance', TRUE, 6),
('team.manage_members', NULL, 'team', 'Manage Members', 'Manage team members', TRUE, 7),
('team.manage_permissions', NULL, 'team', 'Manage Permissions', 'Manage user permissions', TRUE, 8),
-- Settings
('settings.view', NULL, 'settings', 'View Settings', 'View settings', FALSE, 9),
('settings.edit_personal', NULL, 'settings', 'Edit Personal', 'Edit personal settings', FALSE, 10),
('settings.edit_company', NULL, 'settings', 'Edit Company', 'Edit company settings', TRUE, 11),
('settings.integrations', NULL, 'settings', 'Manage Integrations', 'Manage integrations', TRUE, 12),
-- AI
('ai.chat', NULL, 'ai', 'AI Chat', 'Use AI assistant', TRUE, 13),
('ai.tasks', NULL, 'ai', 'AI Tasks', 'AI task recommendations', TRUE, 14),
('ai.recommendations', NULL, 'ai', 'AI Recommendations', 'AI recommendations', TRUE, 15);

-- ============================================================================
-- PART 10: SEED DEFAULT TEMPLATES
-- ============================================================================

-- Lead Stage Templates
INSERT INTO stage_permission_templates (code, name, description, stage_code, role_type, permissions, default_scope, is_system_default, display_order) VALUES
('lead_admin', 'Lead Administrator', 'Full access to lead management', 'lead', 'admin',
 '{"lead.intake.view_all": true, "lead.intake.create": true, "lead.intake.edit_all": true, "lead.intake.delete": true, "lead.intake.import": true, "lead.intake.export": true, "lead.assignment.assign": true, "lead.assignment.reassign": true, "lead.assignment.view_pool": true, "lead.assignment.claim": true, "lead.communication.email": true, "lead.communication.sms": true, "lead.communication.call": true, "lead.communication.view_history": true, "lead.qualification.credit_check": true, "lead.qualification.pre_qualify": true, "lead.qualification.update_status": true, "lead.qualification.add_notes": true, "lead.analytics.view_metrics": true, "lead.analytics.view_conversion": true, "lead.analytics.view_sources": true, "lead.automation.workflows": true, "lead.automation.campaigns": true, "lead.automation.auto_assignment": true}',
 'all', TRUE, 1),

('lead_officer', 'Loan Officer (Leads)', 'Standard loan officer lead access', 'lead', 'standard',
 '{"lead.intake.view_team": true, "lead.intake.view_assigned": true, "lead.intake.create": true, "lead.intake.edit_own": true, "lead.intake.export": true, "lead.assignment.view_pool": true, "lead.assignment.claim": true, "lead.communication.email": true, "lead.communication.sms": true, "lead.communication.call": true, "lead.communication.view_history": true, "lead.qualification.credit_check": true, "lead.qualification.pre_qualify": true, "lead.qualification.update_status": true, "lead.qualification.add_notes": true, "lead.analytics.view_metrics": true, "lead.analytics.view_conversion": true}',
 'assigned', TRUE, 2),

('lead_sdr', 'Sales Development Rep', 'Lead intake and qualification', 'lead', 'sdr',
 '{"lead.intake.view_assigned": true, "lead.intake.create": true, "lead.intake.edit_own": true, "lead.assignment.view_pool": true, "lead.assignment.claim": true, "lead.communication.email": true, "lead.communication.sms": true, "lead.communication.call": true, "lead.communication.view_history": true, "lead.qualification.update_status": true, "lead.qualification.add_notes": true, "lead.analytics.view_metrics": true}',
 'assigned', TRUE, 3),

('lead_readonly', 'Lead Viewer', 'Read-only lead access', 'lead', 'readonly',
 '{"lead.intake.view_all": true, "lead.assignment.view_pool": true, "lead.communication.view_history": true, "lead.analytics.view_metrics": true, "lead.analytics.view_conversion": true, "lead.analytics.view_sources": true}',
 'all', TRUE, 4);

-- Active Loan Stage Templates
INSERT INTO stage_permission_templates (code, name, description, stage_code, role_type, permissions, default_scope, is_system_default, display_order) VALUES
('loan_admin', 'Loan Administrator', 'Full access to loan processing', 'active_loan', 'admin',
 '{"loan.pipeline.view_all": true, "loan.pipeline.create": true, "loan.pipeline.edit_all": true, "loan.pipeline.delete": true, "loan.processing.upload_docs": true, "loan.processing.request_docs": true, "loan.processing.verify_docs": true, "loan.processing.order_services": true, "loan.underwriting.submit": true, "loan.underwriting.view_conditions": true, "loan.underwriting.clear_conditions": true, "loan.underwriting.approve": true, "loan.underwriting.deny": true, "loan.underwriting.suspend": true, "loan.closing.generate_disclosures": true, "loan.closing.schedule": true, "loan.closing.clear_to_close": true, "loan.closing.record_funding": true, "loan.rate_lock.view": true, "loan.rate_lock.lock": true, "loan.rate_lock.extend": true, "loan.rate_lock.relock": true, "loan.analytics.view_pipeline": true, "loan.analytics.view_pull_through": true, "loan.analytics.view_cycle_times": true, "loan.compliance.run_checks": true, "loan.compliance.view_audit": true, "loan.compliance.generate_reports": true}',
 'all', TRUE, 1),

('loan_officer', 'Loan Officer (Loans)', 'Standard loan officer loan access', 'active_loan', 'standard',
 '{"loan.pipeline.view_team": true, "loan.pipeline.view_assigned": true, "loan.pipeline.create": true, "loan.pipeline.edit_own": true, "loan.processing.upload_docs": true, "loan.processing.request_docs": true, "loan.processing.order_services": true, "loan.underwriting.submit": true, "loan.underwriting.view_conditions": true, "loan.closing.generate_disclosures": true, "loan.closing.schedule": true, "loan.rate_lock.view": true, "loan.rate_lock.lock": true, "loan.rate_lock.extend": true, "loan.analytics.view_pipeline": true, "loan.analytics.view_pull_through": true, "loan.analytics.view_cycle_times": true}',
 'assigned', TRUE, 2),

('loan_processor', 'Loan Processor', 'Document and processing access', 'active_loan', 'processor',
 '{"loan.pipeline.view_all": true, "loan.pipeline.create": true, "loan.pipeline.edit_all": true, "loan.processing.upload_docs": true, "loan.processing.request_docs": true, "loan.processing.verify_docs": true, "loan.processing.order_services": true, "loan.underwriting.submit": true, "loan.underwriting.view_conditions": true, "loan.underwriting.clear_conditions": true, "loan.closing.generate_disclosures": true, "loan.closing.schedule": true, "loan.closing.clear_to_close": true, "loan.closing.record_funding": true, "loan.rate_lock.view": true, "loan.analytics.view_pipeline": true, "loan.analytics.view_cycle_times": true, "loan.compliance.run_checks": true}',
 'all', TRUE, 3),

('loan_underwriter', 'Underwriter', 'Underwriting decision access', 'active_loan', 'underwriter',
 '{"loan.pipeline.view_all": true, "loan.underwriting.view_conditions": true, "loan.underwriting.clear_conditions": true, "loan.underwriting.approve": true, "loan.underwriting.deny": true, "loan.underwriting.suspend": true, "loan.rate_lock.view": true, "loan.analytics.view_pipeline": true, "loan.compliance.run_checks": true, "loan.compliance.view_audit": true}',
 'all', TRUE, 4),

('loan_closer', 'Closer', 'Closing and funding access', 'active_loan', 'closer',
 '{"loan.pipeline.view_all": true, "loan.underwriting.view_conditions": true, "loan.closing.generate_disclosures": true, "loan.closing.schedule": true, "loan.closing.clear_to_close": true, "loan.closing.record_funding": true, "loan.rate_lock.view": true, "loan.analytics.view_cycle_times": true}',
 'all', TRUE, 5),

('loan_readonly', 'Loan Viewer', 'Read-only loan access', 'active_loan', 'readonly',
 '{"loan.pipeline.view_all": true, "loan.underwriting.view_conditions": true, "loan.rate_lock.view": true, "loan.analytics.view_pipeline": true, "loan.analytics.view_pull_through": true, "loan.analytics.view_cycle_times": true}',
 'all', TRUE, 6);

-- Portfolio Stage Templates
INSERT INTO stage_permission_templates (code, name, description, stage_code, role_type, permissions, default_scope, is_system_default, display_order) VALUES
('portfolio_admin', 'Portfolio Administrator', 'Full portfolio management access', 'portfolio', 'admin',
 '{"portfolio.clients.view_all": true, "portfolio.clients.edit": true, "portfolio.clients.add_notes": true, "portfolio.clients.view_history": true, "portfolio.mum.view_dashboard": true, "portfolio.mum.view_equity": true, "portfolio.mum.view_rate_watch": true, "portfolio.mum.send_offers": true, "portfolio.campaigns.create": true, "portfolio.campaigns.execute": true, "portfolio.campaigns.view_results": true, "portfolio.milestones.view": true, "portfolio.milestones.send_communications": true, "portfolio.milestones.configure": true, "portfolio.referrals.view": true, "portfolio.referrals.add": true, "portfolio.referrals.track": true, "portfolio.referrals.send_thanks": true, "portfolio.analytics.view_value": true, "portfolio.analytics.view_retention": true, "portfolio.analytics.view_ltv": true, "portfolio.property.view_values": true, "portfolio.property.set_alerts": true, "portfolio.property.view_trends": true}',
 'all', TRUE, 1),

('portfolio_officer', 'Loan Officer (Portfolio)', 'Client relationship management', 'portfolio', 'standard',
 '{"portfolio.clients.view_own": true, "portfolio.clients.edit": true, "portfolio.clients.add_notes": true, "portfolio.clients.view_history": true, "portfolio.mum.view_dashboard": true, "portfolio.mum.view_equity": true, "portfolio.mum.view_rate_watch": true, "portfolio.mum.send_offers": true, "portfolio.campaigns.execute": true, "portfolio.campaigns.view_results": true, "portfolio.milestones.view": true, "portfolio.milestones.send_communications": true, "portfolio.referrals.view": true, "portfolio.referrals.add": true, "portfolio.referrals.track": true, "portfolio.referrals.send_thanks": true, "portfolio.analytics.view_value": true, "portfolio.analytics.view_retention": true, "portfolio.property.view_values": true, "portfolio.property.set_alerts": true, "portfolio.property.view_trends": true}',
 'assigned', TRUE, 2),

('portfolio_analyst', 'Portfolio Analyst', 'Analytics and reporting access', 'portfolio', 'analyst',
 '{"portfolio.clients.view_all": true, "portfolio.clients.view_history": true, "portfolio.mum.view_dashboard": true, "portfolio.mum.view_equity": true, "portfolio.mum.view_rate_watch": true, "portfolio.campaigns.view_results": true, "portfolio.milestones.view": true, "portfolio.referrals.view": true, "portfolio.referrals.track": true, "portfolio.analytics.view_value": true, "portfolio.analytics.view_retention": true, "portfolio.analytics.view_ltv": true, "portfolio.property.view_values": true, "portfolio.property.view_trends": true}',
 'all', TRUE, 3),

('portfolio_readonly', 'Portfolio Viewer', 'Read-only portfolio access', 'portfolio', 'readonly',
 '{"portfolio.clients.view_all": true, "portfolio.clients.view_history": true, "portfolio.mum.view_dashboard": true, "portfolio.mum.view_equity": true, "portfolio.campaigns.view_results": true, "portfolio.milestones.view": true, "portfolio.referrals.view": true, "portfolio.analytics.view_value": true, "portfolio.property.view_values": true, "portfolio.property.view_trends": true}',
 'all', TRUE, 4);

-- ============================================================================
-- PART 11: HELPER FUNCTIONS
-- ============================================================================

-- Function to check if user has stage access
CREATE OR REPLACE FUNCTION user_has_stage_access(p_user_id INTEGER, p_stage_code VARCHAR)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM user_stage_access
        WHERE user_id = p_user_id
        AND stage_code = p_stage_code
        AND is_active = TRUE
        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    );
END;
$$ LANGUAGE plpgsql;

-- Function to check if user has specific permission
CREATE OR REPLACE FUNCTION user_has_permission(p_user_id INTEGER, p_permission_key VARCHAR)
RETURNS BOOLEAN AS $$
DECLARE
    v_stage_code VARCHAR;
    v_template_permissions JSONB;
    v_override_granted BOOLEAN;
BEGIN
    -- Get the stage for this permission
    SELECT stage_code INTO v_stage_code
    FROM permission_definitions WHERE key = p_permission_key;

    -- If stage-specific, check stage access first
    IF v_stage_code IS NOT NULL THEN
        IF NOT user_has_stage_access(p_user_id, v_stage_code) THEN
            RETURN FALSE;
        END IF;
    END IF;

    -- Check for individual override first
    SELECT granted INTO v_override_granted
    FROM user_permission_overrides
    WHERE user_id = p_user_id
    AND permission_key = p_permission_key
    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP);

    IF v_override_granted IS NOT NULL THEN
        RETURN v_override_granted;
    END IF;

    -- Check template permissions
    SELECT spt.permissions INTO v_template_permissions
    FROM user_stage_access usa
    JOIN stage_permission_templates spt ON spt.id = usa.template_id
    WHERE usa.user_id = p_user_id
    AND usa.stage_code = v_stage_code
    AND usa.is_active = TRUE;

    IF v_template_permissions IS NOT NULL THEN
        RETURN COALESCE((v_template_permissions->>p_permission_key)::BOOLEAN, FALSE);
    END IF;

    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Function to get user's data scope for a stage
CREATE OR REPLACE FUNCTION get_user_data_scope(p_user_id INTEGER, p_stage_code VARCHAR)
RETURNS VARCHAR AS $$
DECLARE
    v_scope VARCHAR;
BEGIN
    SELECT COALESCE(data_scope, 'assigned') INTO v_scope
    FROM user_stage_access
    WHERE user_id = p_user_id
    AND stage_code = p_stage_code
    AND is_active = TRUE;

    RETURN COALESCE(v_scope, 'none');
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PART 12: TRIGGERS FOR AUDIT LOGGING
-- ============================================================================

-- Trigger function for audit logging
CREATE OR REPLACE FUNCTION log_permission_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO permission_audit_log (user_id, actor_id, action, entity_type, entity_id, new_value)
        VALUES (NEW.user_id, current_setting('app.current_user_id', true)::INTEGER, 'grant', TG_TABLE_NAME, NEW.id::VARCHAR, to_jsonb(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO permission_audit_log (user_id, actor_id, action, entity_type, entity_id, previous_value, new_value)
        VALUES (NEW.user_id, current_setting('app.current_user_id', true)::INTEGER, 'modify', TG_TABLE_NAME, NEW.id::VARCHAR, to_jsonb(OLD), to_jsonb(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO permission_audit_log (user_id, actor_id, action, entity_type, entity_id, previous_value)
        VALUES (OLD.user_id, current_setting('app.current_user_id', true)::INTEGER, 'revoke', TG_TABLE_NAME, OLD.id::VARCHAR, to_jsonb(OLD));
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
CREATE TRIGGER trg_user_stage_access_audit
AFTER INSERT OR UPDATE OR DELETE ON user_stage_access
FOR EACH ROW EXECUTE FUNCTION log_permission_change();

CREATE TRIGGER trg_user_permission_overrides_audit
AFTER INSERT OR UPDATE OR DELETE ON user_permission_overrides
FOR EACH ROW EXECUTE FUNCTION log_permission_change();
