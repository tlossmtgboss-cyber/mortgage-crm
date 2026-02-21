# Database Schema — Complete Table Definitions

## Overview

These are ALL the tables required for the SLA dates → Workflow tasks pipeline.
Run these in order (dependencies are respected).

---

## Enum Types

```sql
-- Create all enum types first
DO $$ BEGIN
    CREATE TYPE workflow_task_status AS ENUM ('pending', 'completed', 'archived', 'cancelled', 'paused');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE workflow_task_type AS ENUM ('phone', 'email', 'text', 'realtor', 'ai', 'internal');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE workflow_route AS ENUM ('power_dialer', 'task_screen', 'ai_queue');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE sla_status_type AS ENUM ('IN_PROGRESS', 'ON_TRACK', 'APPROACHING', 'OVERDUE', 'COMPLETED', 'MISSED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
```

---

## Table: loans (ALTER — add Important Dates columns)

```sql
-- Important Dates columns on loans table
ALTER TABLE loans ADD COLUMN IF NOT EXISTS new_lead_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS attempted_contact_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS pre_qual_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS pre_approval_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS application_received_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS credit_pulled_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS disclosed_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS processing_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS appraisal_ordered_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS appraisal_received_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS title_ordered_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS title_received_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS uw_submission_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS conditional_approval_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS conditions_sent_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS conditions_received_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS resubmission_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS clear_to_close_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS closing_disclosure_sent_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS closing_scheduled_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS funded_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS mum_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS suspended_date TIMESTAMPTZ;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS current_milestone_status VARCHAR(50);
ALTER TABLE loans ADD COLUMN IF NOT EXISTS current_milestone_entered_at TIMESTAMPTZ;

-- Important Dates columns on leads table
ALTER TABLE leads ADD COLUMN IF NOT EXISTS new_lead_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS attempted_contact_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS pre_qual_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS pre_approval_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS application_received_date TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_milestone_status VARCHAR(50);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_milestone_entered_at TIMESTAMPTZ;

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_loans_milestone_status ON loans(current_milestone_status, current_milestone_entered_at);
CREATE INDEX IF NOT EXISTS idx_leads_milestone_status ON leads(current_milestone_status, current_milestone_entered_at);
CREATE INDEX IF NOT EXISTS idx_loans_org_milestone ON loans(organization_id, current_milestone_status) WHERE current_milestone_status IS NOT NULL;
```

---

## Table: loan_milestone_history

```sql
CREATE TABLE IF NOT EXISTS loan_milestone_history (
    id BIGSERIAL PRIMARY KEY,
    loan_id BIGINT REFERENCES loans(id) ON DELETE CASCADE,
    lead_id BIGINT REFERENCES leads(id) ON DELETE CASCADE,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    milestone_type VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    target_deadline TIMESTAMPTZ,
    sla_target_days INTEGER,
    actual_days INTEGER,
    sla_status sla_status_type DEFAULT 'IN_PROGRESS',
    triggered_by VARCHAR(50),
    triggered_by_user_id BIGINT REFERENCES users(id),
    trigger_notes TEXT,
    previous_milestone_type VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_milestone_history_loan ON loan_milestone_history(loan_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_milestone_history_type ON loan_milestone_history(milestone_type, sla_status);
CREATE INDEX IF NOT EXISTS idx_milestone_history_org ON loan_milestone_history(organization_id, milestone_type);
```

---

## Table: sla_configurations

```sql
CREATE TABLE IF NOT EXISTS sla_configurations (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    user_id BIGINT REFERENCES users(id),
    team_id BIGINT REFERENCES teams(id),
    milestone_type VARCHAR(50) NOT NULL,
    target_days INTEGER NOT NULL,
    warning_threshold_days INTEGER DEFAULT 2,
    escalation_enabled BOOLEAN DEFAULT true,
    escalation_after_days INTEGER,
    escalation_to_role VARCHAR(50),
    create_proactive_task BOOLEAN DEFAULT true,
    create_overdue_task BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_sla_config UNIQUE (organization_id, COALESCE(user_id, 0), COALESCE(team_id, 0), milestone_type)
);

CREATE INDEX IF NOT EXISTS idx_sla_config_lookup ON sla_configurations(organization_id, milestone_type, is_active) WHERE is_active = true;
```

---

## Table: company_holidays

```sql
CREATE TABLE IF NOT EXISTS company_holidays (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    holiday_date DATE NOT NULL,
    holiday_name VARCHAR(100),
    is_recurring BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_holiday UNIQUE (organization_id, holiday_date)
);

CREATE INDEX IF NOT EXISTS idx_holidays_lookup ON company_holidays(organization_id, holiday_date);
```

---

## Table: workflow_configurations

```sql
CREATE TABLE IF NOT EXISTS workflow_configurations (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    milestone_type VARCHAR(50) NOT NULL,
    is_system_default BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    applies_to VARCHAR(20) DEFAULT 'all',
    lead_source_filter VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by BIGINT REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_config_milestone ON workflow_configurations(organization_id, milestone_type, is_active) WHERE is_active = true;
```

---

## Table: workflow_day_configs

```sql
CREATE TABLE IF NOT EXISTS workflow_day_configs (
    id BIGSERIAL PRIMARY KEY,
    workflow_id BIGINT NOT NULL REFERENCES workflow_configurations(id) ON DELETE CASCADE,
    day_number INTEGER NOT NULL,
    day_label VARCHAR(100),
    phone_enabled BOOLEAN DEFAULT false,
    email_enabled BOOLEAN DEFAULT false,
    text_enabled BOOLEAN DEFAULT false,
    realtor_enabled BOOLEAN DEFAULT false,
    ai_enabled BOOLEAN DEFAULT false,
    responsible_role VARCHAR(50) NOT NULL,
    completion_rule VARCHAR(20) DEFAULT 'all',
    priority VARCHAR(10) DEFAULT 'medium',
    task_title_template VARCHAR(200),
    task_description_template TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_workflow_day UNIQUE (workflow_id, day_number, responsible_role)
);

CREATE INDEX IF NOT EXISTS idx_day_config_lookup ON workflow_day_configs(workflow_id, day_number);
```

---

## Table: workflow_instances

```sql
CREATE TABLE IF NOT EXISTS workflow_instances (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    loan_id BIGINT REFERENCES loans(id) ON DELETE CASCADE,
    lead_id BIGINT REFERENCES leads(id) ON DELETE CASCADE,
    workflow_id BIGINT NOT NULL REFERENCES workflow_configurations(id),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    current_day INTEGER DEFAULT 0,
    last_task_generated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_instance_active ON workflow_instances(organization_id, status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_workflow_instance_loan ON workflow_instances(loan_id, status);
CREATE INDEX IF NOT EXISTS idx_workflow_instance_lead ON workflow_instances(lead_id, status);
```

---

## Table: workflow_task_instances

```sql
CREATE TABLE IF NOT EXISTS workflow_task_instances (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    workflow_instance_id BIGINT NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    day_config_id BIGINT NOT NULL REFERENCES workflow_day_configs(id),
    loan_id BIGINT REFERENCES loans(id) ON DELETE CASCADE,
    lead_id BIGINT REFERENCES leads(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    task_type workflow_task_type NOT NULL,
    priority VARCHAR(10) DEFAULT 'medium',
    assigned_role VARCHAR(50) NOT NULL,
    assigned_to_user_id BIGINT REFERENCES users(id),
    routed_to workflow_route NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    day_number INTEGER NOT NULL,
    status workflow_task_status NOT NULL DEFAULT 'pending',
    completed_at TIMESTAMPTZ,
    completed_by_user_id BIGINT REFERENCES users(id),
    archived_at TIMESTAMPTZ,
    archive_reason VARCHAR(50),
    task_group_key VARCHAR(100),
    ai_confidence DECIMAL(5,4),
    ai_auto_completed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_workflow_task_generation UNIQUE (workflow_instance_id, day_config_id, due_at, task_type, assigned_role)
);

CREATE INDEX IF NOT EXISTS idx_task_instance_user ON workflow_task_instances(assigned_to_user_id, status, due_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_task_instance_workflow ON workflow_task_instances(workflow_instance_id, status);
CREATE INDEX IF NOT EXISTS idx_task_instance_route ON workflow_task_instances(routed_to, status, organization_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_task_instance_group ON workflow_task_instances(task_group_key) WHERE task_group_key IS NOT NULL AND status = 'pending';
```

---

## Seed Data: System Default SLA Configurations

```sql
-- Insert system defaults (org_id = 0 or your system org)
-- These are used when no user/team/org-specific config exists

INSERT INTO sla_configurations (organization_id, milestone_type, target_days, warning_threshold_days, escalation_enabled, escalation_after_days, escalation_to_role, is_active)
VALUES
    -- Lead Stage
    (0, 'NEW_LEAD', 1, 0, true, 2, 'manager', true),
    (0, 'ATTEMPTED_CONTACT', 1, 0, true, 2, 'manager', true),
    (0, 'PRE_QUAL', 3, 1, true, 5, 'manager', true),
    (0, 'PRE_APPROVAL', 5, 2, true, 7, 'manager', true),
    
    -- Active Loan Stage
    (0, 'APPLICATION_RECEIVED', 3, 1, true, 5, 'manager', true),
    (0, 'DISCLOSED', 3, 1, true, 5, 'manager', true),
    (0, 'IN_PROCESSING', 14, 3, true, 21, 'manager', true),
    (0, 'UW_SUBMISSION', 3, 1, true, 5, 'manager', true),
    (0, 'CONDITIONAL_APPROVAL', 7, 2, true, 10, 'manager', true),
    (0, 'CLEAR_TO_CLOSE', 5, 2, true, 7, 'manager', true),
    (0, 'CLOSING_SCHEDULED', 7, 2, true, 10, 'manager', true),
    (0, 'FUNDED', 3, 1, true, 5, 'manager', true)
ON CONFLICT DO NOTHING;
```

---

## Seed Data: System Default Workflow Configurations

```sql
-- Example: Prospect Nurture Workflow
INSERT INTO workflow_configurations (organization_id, name, description, milestone_type, is_system_default, is_active)
VALUES (0, 'Prospect Nurture', 'Standard workflow for new leads through prospect stage', 'NEW_LEAD', true, true)
ON CONFLICT DO NOTHING;

-- Get the ID (for day configs below)
-- In practice, use RETURNING id or a lookup

-- Example day configs for Prospect workflow:
-- Day 1: Phone + Email + Text by LO
INSERT INTO workflow_day_configs (workflow_id, day_number, day_label, phone_enabled, email_enabled, text_enabled, responsible_role, completion_rule, priority)
VALUES
    (1, 1, 'First 24 Hours', true, true, true, 'LO', 'all', 'high');

-- Day 2: Phone + Text by LO
INSERT INTO workflow_day_configs (workflow_id, day_number, day_label, phone_enabled, text_enabled, responsible_role, completion_rule, priority)
VALUES
    (1, 2, 'Day 2', true, true, 'LO', 'all', 'high');

-- Day 3: Phone + Email by LO
INSERT INTO workflow_day_configs (workflow_id, day_number, day_label, phone_enabled, email_enabled, responsible_role, completion_rule, priority)
VALUES
    (1, 3, 'Day 3', true, true, 'LO', 'all', 'medium');

-- Day 5: Text + Email + Realtor + AI (any one completes)
INSERT INTO workflow_day_configs (workflow_id, day_number, day_label, text_enabled, email_enabled, realtor_enabled, ai_enabled, responsible_role, completion_rule, priority)
VALUES
    (1, 5, 'Day 5', true, true, true, true, 'LO', 'any', 'medium');

-- Day 7: Phone + Email by LO
INSERT INTO workflow_day_configs (workflow_id, day_number, day_label, phone_enabled, email_enabled, responsible_role, completion_rule, priority)
VALUES
    (1, 7, 'Day 7', true, true, 'LO', 'all', 'medium');

-- Day 14: Phone + Text by LO
INSERT INTO workflow_day_configs (workflow_id, day_number, day_label, phone_enabled, text_enabled, responsible_role, completion_rule, priority)
VALUES
    (1, 14, 'Day 14', true, true, 'LO', 'all', 'low');

-- Month 2 (Day 30): Email by AI
INSERT INTO workflow_day_configs (workflow_id, day_number, day_label, email_enabled, ai_enabled, responsible_role, completion_rule, priority)
VALUES
    (1, 30, 'Month 2', true, true, 'AI', 'any', 'low');

-- Month 3 (Day 60): Email by AI
INSERT INTO workflow_day_configs (workflow_id, day_number, day_label, email_enabled, ai_enabled, responsible_role, completion_rule, priority)
VALUES
    (1, 60, 'Month 3', true, true, 'AI', 'any', 'low');
```

---

## Seed Data: US Federal Holidays (2026)

```sql
INSERT INTO company_holidays (organization_id, holiday_date, holiday_name, is_recurring)
VALUES
    (0, '2026-01-01', 'New Year''s Day', false),
    (0, '2026-01-19', 'Martin Luther King Jr. Day', false),
    (0, '2026-02-16', 'Presidents'' Day', false),
    (0, '2026-05-25', 'Memorial Day', false),
    (0, '2026-06-19', 'Juneteenth', false),
    (0, '2026-07-03', 'Independence Day (Observed)', false),
    (0, '2026-09-07', 'Labor Day', false),
    (0, '2026-10-12', 'Columbus Day', false),
    (0, '2026-11-11', 'Veterans Day', false),
    (0, '2026-11-26', 'Thanksgiving Day', false),
    (0, '2026-12-25', 'Christmas Day', false)
ON CONFLICT DO NOTHING;
```
