"""
Migration: Add Post-Closing Referral Workflow Tables
Creates tables for the automated post-closing referral workflow system:
- employer_records
- opportunities
- recurring_tasks
- workflow_executions

Also adds missing referral columns to leads table.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def run_migration():
    """Add post-closing workflow tables and columns"""

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:

        # ================================================================
        # 1. ADD MISSING COLUMNS TO LEADS TABLE
        # ================================================================
        print("\n=== Adding columns to leads table ===")

        new_lead_columns = [
            ("employer_name", "VARCHAR(255)"),
            ("industry", "VARCHAR(100)"),
        ]

        for col_name, col_type in new_lead_columns:
            try:
                check_sql = text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'leads' AND column_name = :col_name
                """)
                result = conn.execute(check_sql, {"col_name": col_name})

                if result.fetchone() is None:
                    alter_sql = text(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}")
                    conn.execute(alter_sql)
                    print(f"  Added: {col_name}")
                else:
                    print(f"  Exists: {col_name}")
            except Exception as e:
                print(f"  Error adding {col_name}: {e}")

        # Add indexes for leads columns
        lead_indexes = [
            ("idx_leads_employer_name", "leads", "employer_name"),
            ("idx_leads_industry", "leads", "industry"),
        ]

        for idx_name, table, column in lead_indexes:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})"))
                print(f"  Index: {idx_name}")
            except Exception as e:
                print(f"  Index exists or error: {idx_name}")

        # ================================================================
        # 2. CREATE EMPLOYER_RECORDS TABLE
        # ================================================================
        print("\n=== Creating employer_records table ===")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS employer_records (
                    id SERIAL PRIMARY KEY,
                    company_name VARCHAR(255) NOT NULL,
                    champion_lead_id INTEGER REFERENCES leads(id),
                    status VARCHAR(50) DEFAULT 'Opportunity Identified',
                    employee_count INTEGER,
                    source VARCHAR(100),
                    notes TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    created_by INTEGER REFERENCES users(id)
                )
            """))
            print("  Created: employer_records")

            # Create indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_employer_records_company ON employer_records(company_name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_employer_records_champion ON employer_records(champion_lead_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_employer_records_status ON employer_records(status)"))
            print("  Created indexes for employer_records")
        except Exception as e:
            print(f"  Error: {e}")

        # ================================================================
        # 3. CREATE OPPORTUNITIES TABLE
        # ================================================================
        print("\n=== Creating opportunities table ===")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id SERIAL PRIMARY KEY,
                    type VARCHAR(100) NOT NULL,
                    primary_lead_id INTEGER NOT NULL REFERENCES leads(id),
                    company_name VARCHAR(255),
                    stage VARCHAR(50) DEFAULT 'Initial Discovery',
                    estimated_value NUMERIC(10, 2),
                    estimated_employee_count INTEGER,
                    champion_name VARCHAR(255),
                    source VARCHAR(100),
                    status VARCHAR(50) DEFAULT 'Active',
                    notes TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    assigned_to INTEGER REFERENCES users(id)
                )
            """))
            print("  Created: opportunities")

            # Create indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_type ON opportunities(type)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_lead ON opportunities(primary_lead_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_company ON opportunities(company_name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_stage ON opportunities(stage)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_assigned ON opportunities(assigned_to)"))
            print("  Created indexes for opportunities")
        except Exception as e:
            print(f"  Error: {e}")

        # ================================================================
        # 4. CREATE RECURRING_TASKS TABLE
        # ================================================================
        print("\n=== Creating recurring_tasks table ===")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS recurring_tasks (
                    id SERIAL PRIMARY KEY,
                    lead_id INTEGER NOT NULL REFERENCES leads(id),
                    title VARCHAR(255) NOT NULL,
                    recurrence_pattern VARCHAR(50),
                    recurrence_interval_days INTEGER,
                    priority VARCHAR(20) DEFAULT 'medium',
                    category VARCHAR(100),
                    notes TEXT,
                    assigned_to INTEGER REFERENCES users(id),
                    next_due_date TIMESTAMP WITH TIME ZONE,
                    last_completed_date TIMESTAMP WITH TIME ZONE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            print("  Created: recurring_tasks")

            # Create indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_lead ON recurring_tasks(lead_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_priority ON recurring_tasks(priority)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_category ON recurring_tasks(category)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_assigned ON recurring_tasks(assigned_to)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_due_date ON recurring_tasks(next_due_date)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_active ON recurring_tasks(is_active)"))
            print("  Created indexes for recurring_tasks")
        except Exception as e:
            print(f"  Error: {e}")

        # ================================================================
        # 5. CREATE WORKFLOW_EXECUTIONS TABLE
        # ================================================================
        print("\n=== Creating workflow_executions table ===")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    id SERIAL PRIMARY KEY,
                    workflow_id VARCHAR(100) NOT NULL,
                    workflow_name VARCHAR(255),
                    lead_id INTEGER REFERENCES leads(id),
                    loan_id INTEGER REFERENCES loans(id),
                    trigger_event VARCHAR(100),
                    execution_status VARCHAR(50),
                    actions_completed JSONB,
                    error_message TEXT,
                    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            print("  Created: workflow_executions")

            # Create indexes
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_executions_workflow ON workflow_executions(workflow_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_executions_lead ON workflow_executions(lead_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_executions_loan ON workflow_executions(loan_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_executions_trigger ON workflow_executions(trigger_event)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(execution_status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_executions_executed ON workflow_executions(executed_at)"))
            print("  Created indexes for workflow_executions")
        except Exception as e:
            print(f"  Error: {e}")

        # ================================================================
        # 6. CREATE UPDATE TRIGGERS
        # ================================================================
        print("\n=== Creating update triggers ===")

        try:
            # Create trigger function
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql'
            """))
            print("  Created: update_updated_at_column function")

            # Create triggers for tables with updated_at
            for table in ['employer_records', 'opportunities']:
                try:
                    conn.execute(text(f"""
                        DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}
                    """))
                    conn.execute(text(f"""
                        CREATE TRIGGER update_{table}_updated_at
                        BEFORE UPDATE ON {table}
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column()
                    """))
                    print(f"  Created trigger for: {table}")
                except Exception as e:
                    print(f"  Trigger error for {table}: {e}")
        except Exception as e:
            print(f"  Error creating triggers: {e}")

        conn.commit()

    print("\n=== Post-Closing Workflow Migration Complete ===")
    print("\nTables created:")
    print("  - employer_records")
    print("  - opportunities")
    print("  - recurring_tasks")
    print("  - workflow_executions")
    print("\nNext steps:")
    print("  1. Add workflow_models.py to your models")
    print("  2. Integrate post_closing_workflow.py into backend")
    print("  3. Add trigger to loan closing endpoint")


if __name__ == "__main__":
    run_migration()
