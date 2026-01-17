-- Migration: Add user roles tables
-- Description: Creates tables for managing user roles and permissions
-- Created: 2026-01-17

-- Create onboarding_roles table
CREATE TABLE IF NOT EXISTS onboarding_roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default roles
INSERT INTO onboarding_roles (name, description) VALUES
        ('Site Administrator', 'Full platform administrator with access to all companies and settings'),
    ('Company Admin', 'Company administrator with access to manage their organization'),
    ('Loan Officer', 'Primary role for licensed mortgage loan officers'),
    ('Manager', 'Management role with oversight capabilities'),
ON CONFLICT (name) DO NOTHING;
-- Create user_assigned_roles table
CREATE TABLE IF NOT EXISTS user_assigned_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by INTEGER,
    
    -- Foreign keys
    CONSTRAINT fk_user_assigned_roles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_assigned_roles_role FOREIGN KEY (role_id) REFERENCES onboarding_roles(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT uix_user_assigned_roles_user_role UNIQUE (user_id, role_id)
);

-- Create user_active_role table
CREATE TABLE IF NOT EXISTS user_active_role (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    active_role_id INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign keys
    CONSTRAINT fk_user_active_role_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_active_role_role FOREIGN KEY (active_role_id) REFERENCES onboarding_roles(id) ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_user_assigned_roles_user_id ON user_assigned_roles(user_id);
CREATE INDEX IF NOT EXISTS ix_user_assigned_roles_role_id ON user_assigned_roles(role_id);
CREATE INDEX IF NOT EXISTS ix_user_active_role_user_id ON user_active_role(user_id);
CREATE INDEX IF NOT EXISTS ix_user_active_role_role_id ON user_active_role(active_role_id);
