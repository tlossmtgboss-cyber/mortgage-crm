"""
Migration: Add Profitability Intelligence Tables
Creates all tables needed for the profitability tracking and analysis system.
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Run the profitability tables migration."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if main table already exists
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'expense_categories'
        """))

        if result.fetchone():
            print("Profitability tables already exist. Skipping migration.")
            return

        print("Creating profitability tables...")

        # 1. Expense Categories
        conn.execute(text("""
            CREATE TABLE expense_categories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                parent_category_id UUID REFERENCES expense_categories(id),
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_expense_categories_parent ON expense_categories(parent_category_id);
            CREATE INDEX idx_expense_categories_name ON expense_categories(name);
        """))

        # 2. Expenses (recurring and one-time)
        conn.execute(text("""
            CREATE TABLE expenses (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                category_id UUID REFERENCES expense_categories(id),
                name VARCHAR(255) NOT NULL,
                description TEXT,
                amount NUMERIC(12, 2) NOT NULL,
                expense_type VARCHAR(20) NOT NULL CHECK (expense_type IN ('fixed', 'variable', 'one_time')),
                recurrence VARCHAR(20) DEFAULT 'monthly' CHECK (recurrence IN ('daily', 'weekly', 'monthly', 'quarterly', 'annually', 'one_time')),
                effective_date DATE NOT NULL,
                end_date DATE,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER
            );

            CREATE INDEX idx_expenses_org ON expenses(organization_id);
            CREATE INDEX idx_expenses_category ON expenses(category_id);
            CREATE INDEX idx_expenses_type ON expenses(expense_type);
            CREATE INDEX idx_expenses_effective ON expenses(effective_date);
        """))

        # 3. Role Definitions
        conn.execute(text("""
            CREATE TABLE profitability_roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                department VARCHAR(100),
                is_revenue_generating BOOLEAN DEFAULT false,
                base_salary_range_min NUMERIC(10, 2),
                base_salary_range_max NUMERIC(10, 2),
                typical_benefits_percentage NUMERIC(5, 2) DEFAULT 25.00,
                description TEXT,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, name)
            );

            CREATE INDEX idx_prof_roles_org ON profitability_roles(organization_id);
        """))

        # 4. Employee Costs (fully-loaded)
        conn.execute(text("""
            CREATE TABLE employee_costs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                user_id INTEGER REFERENCES users(id),
                role_id UUID REFERENCES profitability_roles(id),
                employee_name VARCHAR(255) NOT NULL,
                base_salary NUMERIC(10, 2) NOT NULL,
                benefits_cost NUMERIC(10, 2) DEFAULT 0,
                taxes_cost NUMERIC(10, 2) DEFAULT 0,
                equipment_cost NUMERIC(10, 2) DEFAULT 0,
                training_cost NUMERIC(10, 2) DEFAULT 0,
                other_costs NUMERIC(10, 2) DEFAULT 0,
                fully_loaded_cost NUMERIC(12, 2) GENERATED ALWAYS AS (
                    base_salary + benefits_cost + taxes_cost + equipment_cost + training_cost + other_costs
                ) STORED,
                monthly_cost NUMERIC(12, 2) GENERATED ALWAYS AS (
                    (base_salary + benefits_cost + taxes_cost + equipment_cost + training_cost + other_costs) / 12
                ) STORED,
                hire_date DATE,
                termination_date DATE,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_employee_costs_org ON employee_costs(organization_id);
            CREATE INDEX idx_employee_costs_user ON employee_costs(user_id);
            CREATE INDEX idx_employee_costs_role ON employee_costs(role_id);
        """))

        # 5. Closed Loans
        conn.execute(text("""
            CREATE TABLE profitability_loans (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                loan_number VARCHAR(100) NOT NULL,
                borrower_name VARCHAR(255),
                loan_amount NUMERIC(12, 2) NOT NULL,
                loan_type VARCHAR(50),
                close_date DATE NOT NULL,
                total_revenue NUMERIC(12, 2) NOT NULL,
                processing_days INTEGER,
                lead_source VARCHAR(100),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, loan_number)
            );

            CREATE INDEX idx_prof_loans_org ON profitability_loans(organization_id);
            CREATE INDEX idx_prof_loans_close ON profitability_loans(close_date);
        """))

        # 6. Loan Attributions (employee contribution to loans)
        conn.execute(text("""
            CREATE TABLE loan_attributions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                loan_id UUID REFERENCES profitability_loans(id) ON DELETE CASCADE,
                employee_cost_id UUID REFERENCES employee_costs(id),
                attribution_percentage NUMERIC(5, 2) NOT NULL CHECK (attribution_percentage > 0 AND attribution_percentage <= 100),
                role_at_time VARCHAR(100),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_loan_attr_loan ON loan_attributions(loan_id);
            CREATE INDEX idx_loan_attr_employee ON loan_attributions(employee_cost_id);
        """))

        # 7. Revenue Records
        conn.execute(text("""
            CREATE TABLE revenue_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                loan_id UUID REFERENCES profitability_loans(id) ON DELETE SET NULL,
                revenue_type VARCHAR(50) NOT NULL CHECK (revenue_type IN ('origination_fee', 'processing_fee', 'admin_fee', 'commission', 'rebate', 'other')),
                amount NUMERIC(12, 2) NOT NULL,
                description TEXT,
                record_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_revenue_org ON revenue_records(organization_id);
            CREATE INDEX idx_revenue_loan ON revenue_records(loan_id);
            CREATE INDEX idx_revenue_date ON revenue_records(record_date);
        """))

        # 8. Monthly Snapshots (for historical tracking)
        conn.execute(text("""
            CREATE TABLE profitability_snapshots (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                snapshot_month DATE NOT NULL,
                total_revenue NUMERIC(12, 2) NOT NULL,
                total_expenses NUMERIC(12, 2) NOT NULL,
                net_profit NUMERIC(12, 2) NOT NULL,
                loans_closed INTEGER NOT NULL,
                cost_per_loan NUMERIC(10, 2),
                revenue_per_loan NUMERIC(10, 2),
                profit_per_loan NUMERIC(10, 2),
                employee_count INTEGER,
                break_even_loans INTEGER,
                data_json JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, snapshot_month)
            );

            CREATE INDEX idx_snapshot_org_month ON profitability_snapshots(organization_id, snapshot_month);
        """))

        # 9. Scenarios (what-if analysis)
        conn.execute(text("""
            CREATE TABLE profitability_scenarios (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                base_month DATE NOT NULL,
                parameters JSONB NOT NULL,
                results JSONB,
                created_by INTEGER REFERENCES users(id),
                is_saved BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_scenarios_org ON profitability_scenarios(organization_id);
            CREATE INDEX idx_scenarios_created_by ON profitability_scenarios(created_by);
        """))

        # 10. AI Insights
        conn.execute(text("""
            CREATE TABLE profitability_insights (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                insight_type VARCHAR(50) NOT NULL CHECK (insight_type IN ('gap', 'gain', 'trend', 'recommendation', 'alert')),
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                severity VARCHAR(20) DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical', 'opportunity')),
                data_json JSONB,
                is_acknowledged BOOLEAN DEFAULT false,
                acknowledged_by INTEGER REFERENCES users(id),
                acknowledged_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_insights_org ON profitability_insights(organization_id);
            CREATE INDEX idx_insights_type ON profitability_insights(insight_type);
            CREATE INDEX idx_insights_severity ON profitability_insights(severity);
        """))

        # 11. Audit Trail
        conn.execute(text("""
            CREATE TABLE profitability_audit (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                user_id INTEGER REFERENCES users(id),
                action VARCHAR(50) NOT NULL,
                entity_type VARCHAR(50) NOT NULL,
                entity_id UUID,
                old_values JSONB,
                new_values JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_prof_audit_org ON profitability_audit(organization_id);
            CREATE INDEX idx_prof_audit_entity ON profitability_audit(entity_type, entity_id);
            CREATE INDEX idx_prof_audit_created ON profitability_audit(created_at);
        """))

        # Seed default expense categories
        conn.execute(text("""
            INSERT INTO expense_categories (name, description) VALUES
            ('Personnel', 'Employee-related expenses including salaries and benefits'),
            ('Technology', 'Software, hardware, and IT infrastructure'),
            ('Marketing', 'Advertising, lead generation, and marketing campaigns'),
            ('Operations', 'Office space, utilities, and operational costs'),
            ('Professional Services', 'Legal, accounting, and consulting fees'),
            ('Compliance', 'Licensing, regulatory fees, and compliance costs'),
            ('Training', 'Employee training and professional development'),
            ('Travel', 'Business travel and entertainment');
        """))

        conn.commit()
        print("Profitability tables created successfully!")


if __name__ == "__main__":
    run_migration()
