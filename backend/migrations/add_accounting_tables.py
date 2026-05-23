"""
Migration: Add Complete Accounting System Tables
Creates all tables for double-entry accounting system including:
- Chart of Accounts & General Ledger
- Journal Entries
- Accounts Receivable (Customers, Invoices, Payments)
- Accounts Payable (Vendors, Bills, Payments)
- Banking & Plaid Integration
- Budgeting
- Accounting Periods
- Audit Trail

SQLite-compatible version
"""

from sqlalchemy import create_engine, text
import os
import sys
import uuid

# Add parent directory to path to import database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)


def generate_uuid():
    """Generate a UUID string."""
    return str(uuid.uuid4())


def is_sqlite():
    """Check if the database is SQLite."""
    return DATABASE_URL.startswith('sqlite')


def run_migration():
    """Run the accounting tables migration."""
    print(f"Using database: {DATABASE_URL[:50]}...")
    print(f"Database type: {'SQLite' if is_sqlite() else 'PostgreSQL'}")

    with engine.connect() as conn:
        # Check if main table already exists (SQLite-compatible)
        if is_sqlite():
            result = conn.execute(text("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='chart_of_accounts'
            """))
        else:
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'chart_of_accounts'
            """))

        if result.fetchone():
            print("Accounting tables already exist. Skipping migration.")
            return

        print("Creating accounting system tables...")

        # =====================================================================
        # 1. CHART OF ACCOUNTS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE chart_of_accounts (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                account_number VARCHAR(20) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                account_type VARCHAR(50) NOT NULL,
                account_subtype VARCHAR(50),
                parent_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                normal_balance VARCHAR(10) NOT NULL,
                is_bank_account INTEGER DEFAULT 0,
                bank_account_id VARCHAR(36),
                currency VARCHAR(3) DEFAULT 'USD',
                is_active INTEGER DEFAULT 1,
                is_system_account INTEGER DEFAULT 0,
                tax_code VARCHAR(20),
                display_order INTEGER,
                opening_balance REAL DEFAULT 0,
                opening_balance_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(organization_id, account_number)
            )
        """))

        conn.execute(text("CREATE INDEX idx_coa_org ON chart_of_accounts(organization_id)"))
        conn.execute(text("CREATE INDEX idx_coa_org_type ON chart_of_accounts(organization_id, account_type)"))
        conn.execute(text("CREATE INDEX idx_coa_parent ON chart_of_accounts(parent_account_id)"))
        conn.execute(text("CREATE INDEX idx_coa_active ON chart_of_accounts(organization_id, is_active)"))
        print("Created chart_of_accounts table")

        # =====================================================================
        # 2. ACCOUNTING PERIODS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE accounting_periods (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                period_name VARCHAR(50) NOT NULL,
                period_type VARCHAR(20) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status VARCHAR(20) DEFAULT 'open',
                closed_at TIMESTAMP,
                closed_by INTEGER,
                fiscal_year INTEGER NOT NULL,
                fiscal_period INTEGER NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, start_date, end_date)
            )
        """))

        conn.execute(text("CREATE INDEX idx_period_org ON accounting_periods(organization_id)"))
        conn.execute(text("CREATE INDEX idx_period_org_status ON accounting_periods(organization_id, status)"))
        conn.execute(text("CREATE INDEX idx_period_dates ON accounting_periods(organization_id, start_date, end_date)"))
        print("Created accounting_periods table")

        # =====================================================================
        # 3. JOURNAL ENTRIES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE journal_entries (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                entry_number VARCHAR(20) NOT NULL,
                entry_date DATE NOT NULL,
                period_id VARCHAR(36) REFERENCES accounting_periods(id),
                description TEXT NOT NULL,
                entry_type VARCHAR(30) NOT NULL,
                source_type VARCHAR(50),
                source_id VARCHAR(36),
                status VARCHAR(20) DEFAULT 'draft',
                posted_at TIMESTAMP,
                posted_by INTEGER,
                voided_at TIMESTAMP,
                voided_by INTEGER,
                void_reason TEXT,
                reversed_by_entry_id VARCHAR(36),
                reverses_entry_id VARCHAR(36),
                memo TEXT,
                reference_number VARCHAR(100),
                total_debits REAL DEFAULT 0,
                total_credits REAL DEFAULT 0,
                attachments TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(organization_id, entry_number)
            )
        """))

        conn.execute(text("CREATE INDEX idx_je_org ON journal_entries(organization_id)"))
        conn.execute(text("CREATE INDEX idx_je_org_date ON journal_entries(organization_id, entry_date)"))
        conn.execute(text("CREATE INDEX idx_je_period ON journal_entries(period_id)"))
        conn.execute(text("CREATE INDEX idx_je_source ON journal_entries(source_type, source_id)"))
        conn.execute(text("CREATE INDEX idx_je_status ON journal_entries(organization_id, status)"))
        print("Created journal_entries table")

        # =====================================================================
        # 4. JOURNAL ENTRY LINES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE journal_entry_lines (
                id VARCHAR(36) PRIMARY KEY,
                journal_entry_id VARCHAR(36) NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
                account_id VARCHAR(36) NOT NULL REFERENCES chart_of_accounts(id),
                description TEXT,
                debit_amount REAL DEFAULT 0,
                credit_amount REAL DEFAULT 0,
                currency VARCHAR(3) DEFAULT 'USD',
                exchange_rate REAL DEFAULT 1.0,
                department_id VARCHAR(36),
                project_id VARCHAR(36),
                loan_id VARCHAR(36),
                customer_id VARCHAR(36),
                vendor_id VARCHAR(36),
                line_order INTEGER NOT NULL DEFAULT 0,
                reconciled INTEGER DEFAULT 0,
                reconciled_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("CREATE INDEX idx_jel_entry ON journal_entry_lines(journal_entry_id)"))
        conn.execute(text("CREATE INDEX idx_jel_account ON journal_entry_lines(account_id)"))
        conn.execute(text("CREATE INDEX idx_jel_customer ON journal_entry_lines(customer_id)"))
        conn.execute(text("CREATE INDEX idx_jel_vendor ON journal_entry_lines(vendor_id)"))
        print("Created journal_entry_lines table")

        # =====================================================================
        # 5. AR CUSTOMERS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_customers (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                customer_number VARCHAR(20) NOT NULL,
                name VARCHAR(255) NOT NULL,
                company_name VARCHAR(255),
                email VARCHAR(255),
                phone VARCHAR(50),
                billing_address TEXT DEFAULT '{}',
                shipping_address TEXT DEFAULT '{}',
                payment_terms VARCHAR(20) DEFAULT 'net30',
                credit_limit REAL,
                current_balance REAL DEFAULT 0,
                ar_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                tax_exempt INTEGER DEFAULT 0,
                tax_id VARCHAR(50),
                notes TEXT,
                is_active INTEGER DEFAULT 1,
                contact_id INTEGER,
                borrower_id INTEGER,
                tenant_account_id VARCHAR(36),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(organization_id, customer_number)
            )
        """))

        conn.execute(text("CREATE INDEX idx_ar_cust_org ON ar_customers(organization_id)"))
        conn.execute(text("CREATE INDEX idx_ar_cust_active ON ar_customers(organization_id, is_active)"))
        conn.execute(text("CREATE INDEX idx_ar_cust_tenant ON ar_customers(tenant_account_id)"))
        print("Created ar_customers table")

        # =====================================================================
        # 6. AR INVOICES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_invoices (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                invoice_number VARCHAR(30) NOT NULL,
                customer_id VARCHAR(36) NOT NULL REFERENCES ar_customers(id),
                invoice_date DATE NOT NULL,
                due_date DATE NOT NULL,
                status VARCHAR(20) DEFAULT 'draft',
                subtotal REAL NOT NULL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                discount_amount REAL DEFAULT 0,
                discount_percent REAL,
                total_amount REAL NOT NULL DEFAULT 0,
                amount_paid REAL DEFAULT 0,
                currency VARCHAR(3) DEFAULT 'USD',
                terms TEXT,
                notes TEXT,
                memo TEXT,
                footer TEXT,
                journal_entry_id VARCHAR(36) REFERENCES journal_entries(id),
                source_type VARCHAR(50),
                source_id VARCHAR(36),
                sent_at TIMESTAMP,
                sent_to VARCHAR(255),
                viewed_at TIMESTAMP,
                last_reminder_at TIMESTAMP,
                reminder_count INTEGER DEFAULT 0,
                paid_at TIMESTAMP,
                voided_at TIMESTAMP,
                voided_by INTEGER,
                void_reason TEXT,
                template_id VARCHAR(36),
                pdf_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(organization_id, invoice_number)
            )
        """))

        conn.execute(text("CREATE INDEX idx_ar_inv_org ON ar_invoices(organization_id)"))
        conn.execute(text("CREATE INDEX idx_ar_inv_customer ON ar_invoices(customer_id)"))
        conn.execute(text("CREATE INDEX idx_ar_inv_status ON ar_invoices(organization_id, status)"))
        conn.execute(text("CREATE INDEX idx_ar_inv_due ON ar_invoices(organization_id, due_date)"))
        conn.execute(text("CREATE INDEX idx_ar_inv_date ON ar_invoices(organization_id, invoice_date)"))
        print("Created ar_invoices table")

        # =====================================================================
        # 7. AR INVOICE LINES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_invoice_lines (
                id VARCHAR(36) PRIMARY KEY,
                invoice_id VARCHAR(36) NOT NULL REFERENCES ar_invoices(id) ON DELETE CASCADE,
                line_order INTEGER NOT NULL DEFAULT 0,
                item_code VARCHAR(50),
                description TEXT NOT NULL,
                quantity REAL DEFAULT 1,
                unit_price REAL NOT NULL,
                amount REAL NOT NULL,
                discount_percent REAL,
                discount_amount REAL DEFAULT 0,
                revenue_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                tax_code VARCHAR(20),
                tax_rate REAL,
                tax_amount REAL DEFAULT 0,
                product_id VARCHAR(36),
                service_id VARCHAR(36),
                loan_id VARCHAR(36),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("CREATE INDEX idx_ar_inv_line_inv ON ar_invoice_lines(invoice_id)"))
        print("Created ar_invoice_lines table")

        # =====================================================================
        # 8. AR PAYMENTS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_payments (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                payment_number VARCHAR(30) NOT NULL,
                customer_id VARCHAR(36) NOT NULL REFERENCES ar_customers(id),
                payment_date DATE NOT NULL,
                amount REAL NOT NULL,
                amount_applied REAL DEFAULT 0,
                amount_unapplied REAL DEFAULT 0,
                payment_method VARCHAR(30) NOT NULL,
                reference_number VARCHAR(100),
                deposit_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                status VARCHAR(20) DEFAULT 'pending',
                memo TEXT,
                journal_entry_id VARCHAR(36) REFERENCES journal_entries(id),
                stripe_payment_id VARCHAR(100),
                stripe_charge_id VARCHAR(100),
                bank_transaction_id VARCHAR(36),
                reconciled_at TIMESTAMP,
                voided_at TIMESTAMP,
                voided_by INTEGER,
                void_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(organization_id, payment_number)
            )
        """))

        conn.execute(text("CREATE INDEX idx_ar_pay_org ON ar_payments(organization_id)"))
        conn.execute(text("CREATE INDEX idx_ar_pay_customer ON ar_payments(customer_id)"))
        conn.execute(text("CREATE INDEX idx_ar_pay_status ON ar_payments(organization_id, status)"))
        conn.execute(text("CREATE INDEX idx_ar_pay_date ON ar_payments(organization_id, payment_date)"))
        print("Created ar_payments table")

        # =====================================================================
        # 9. AR PAYMENT APPLICATIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_payment_applications (
                id VARCHAR(36) PRIMARY KEY,
                payment_id VARCHAR(36) NOT NULL REFERENCES ar_payments(id) ON DELETE CASCADE,
                invoice_id VARCHAR(36) NOT NULL REFERENCES ar_invoices(id),
                amount_applied REAL NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        """))

        conn.execute(text("CREATE INDEX idx_ar_pay_app_payment ON ar_payment_applications(payment_id)"))
        conn.execute(text("CREATE INDEX idx_ar_pay_app_invoice ON ar_payment_applications(invoice_id)"))
        print("Created ar_payment_applications table")

        # =====================================================================
        # 10. AP VENDORS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_vendors (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                vendor_number VARCHAR(20) NOT NULL,
                name VARCHAR(255) NOT NULL,
                company_name VARCHAR(255),
                email VARCHAR(255),
                phone VARCHAR(50),
                address TEXT DEFAULT '{}',
                payment_terms VARCHAR(20) DEFAULT 'net30',
                default_expense_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                ap_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                tax_id VARCHAR(50),
                requires_1099 INTEGER DEFAULT 0,
                form_1099_type VARCHAR(20),
                current_balance REAL DEFAULT 0,
                credit_limit REAL,
                payment_method_default VARCHAR(30),
                bank_account_info TEXT DEFAULT '{}',
                is_active INTEGER DEFAULT 1,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(organization_id, vendor_number)
            )
        """))

        conn.execute(text("CREATE INDEX idx_ap_vend_org ON ap_vendors(organization_id)"))
        conn.execute(text("CREATE INDEX idx_ap_vend_active ON ap_vendors(organization_id, is_active)"))
        conn.execute(text("CREATE INDEX idx_ap_vend_1099 ON ap_vendors(organization_id, requires_1099)"))
        print("Created ap_vendors table")

        # =====================================================================
        # 11. AP BILLS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_bills (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                bill_number VARCHAR(30) NOT NULL,
                vendor_id VARCHAR(36) NOT NULL REFERENCES ap_vendors(id),
                vendor_invoice_number VARCHAR(100),
                bill_date DATE NOT NULL,
                due_date DATE NOT NULL,
                status VARCHAR(20) DEFAULT 'draft',
                subtotal REAL NOT NULL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                shipping_amount REAL DEFAULT 0,
                discount_amount REAL DEFAULT 0,
                total_amount REAL NOT NULL DEFAULT 0,
                amount_paid REAL DEFAULT 0,
                currency VARCHAR(3) DEFAULT 'USD',
                terms TEXT,
                notes TEXT,
                memo TEXT,
                approval_status VARCHAR(20) DEFAULT 'pending',
                approved_by INTEGER,
                approved_at TIMESTAMP,
                rejection_reason TEXT,
                journal_entry_id VARCHAR(36) REFERENCES journal_entries(id),
                recurring_bill_id VARCHAR(36),
                document_url TEXT,
                voided_at TIMESTAMP,
                voided_by INTEGER,
                void_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(organization_id, bill_number)
            )
        """))

        conn.execute(text("CREATE INDEX idx_ap_bill_org ON ap_bills(organization_id)"))
        conn.execute(text("CREATE INDEX idx_ap_bill_vendor ON ap_bills(vendor_id)"))
        conn.execute(text("CREATE INDEX idx_ap_bill_status ON ap_bills(organization_id, status)"))
        conn.execute(text("CREATE INDEX idx_ap_bill_due ON ap_bills(organization_id, due_date)"))
        conn.execute(text("CREATE INDEX idx_ap_bill_approval ON ap_bills(organization_id, approval_status)"))
        print("Created ap_bills table")

        # =====================================================================
        # 12. AP BILL LINES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_bill_lines (
                id VARCHAR(36) PRIMARY KEY,
                bill_id VARCHAR(36) NOT NULL REFERENCES ap_bills(id) ON DELETE CASCADE,
                line_order INTEGER NOT NULL DEFAULT 0,
                item_code VARCHAR(50),
                description TEXT NOT NULL,
                quantity REAL DEFAULT 1,
                unit_price REAL NOT NULL,
                amount REAL NOT NULL,
                expense_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                tax_code VARCHAR(20),
                tax_amount REAL DEFAULT 0,
                department_id VARCHAR(36),
                project_id VARCHAR(36),
                billable INTEGER DEFAULT 0,
                billable_customer_id VARCHAR(36) REFERENCES ar_customers(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("CREATE INDEX idx_ap_bill_line_bill ON ap_bill_lines(bill_id)"))
        print("Created ap_bill_lines table")

        # =====================================================================
        # 13. AP PAYMENTS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_payments (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                payment_number VARCHAR(30) NOT NULL,
                vendor_id VARCHAR(36) NOT NULL REFERENCES ap_vendors(id),
                payment_date DATE NOT NULL,
                amount REAL NOT NULL,
                amount_applied REAL DEFAULT 0,
                payment_method VARCHAR(30) NOT NULL,
                check_number VARCHAR(20),
                bank_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                status VARCHAR(20) DEFAULT 'pending',
                memo TEXT,
                journal_entry_id VARCHAR(36) REFERENCES journal_entries(id),
                bank_transaction_id VARCHAR(36),
                reconciled_at TIMESTAMP,
                cleared_at TIMESTAMP,
                voided_at TIMESTAMP,
                voided_by INTEGER,
                void_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                UNIQUE(organization_id, payment_number)
            )
        """))

        conn.execute(text("CREATE INDEX idx_ap_pay_org ON ap_payments(organization_id)"))
        conn.execute(text("CREATE INDEX idx_ap_pay_vendor ON ap_payments(vendor_id)"))
        conn.execute(text("CREATE INDEX idx_ap_pay_status ON ap_payments(organization_id, status)"))
        conn.execute(text("CREATE INDEX idx_ap_pay_date ON ap_payments(organization_id, payment_date)"))
        print("Created ap_payments table")

        # =====================================================================
        # 14. AP PAYMENT APPLICATIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_payment_applications (
                id VARCHAR(36) PRIMARY KEY,
                payment_id VARCHAR(36) NOT NULL REFERENCES ap_payments(id) ON DELETE CASCADE,
                bill_id VARCHAR(36) NOT NULL REFERENCES ap_bills(id),
                amount_applied REAL NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        """))

        conn.execute(text("CREATE INDEX idx_ap_pay_app_payment ON ap_payment_applications(payment_id)"))
        conn.execute(text("CREATE INDEX idx_ap_pay_app_bill ON ap_payment_applications(bill_id)"))
        print("Created ap_payment_applications table")

        # =====================================================================
        # 15. BANK ACCOUNTS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE bank_accounts (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                account_name VARCHAR(255) NOT NULL,
                account_type VARCHAR(30) NOT NULL,
                institution_name VARCHAR(255),
                account_number_last4 VARCHAR(4),
                routing_number VARCHAR(20),
                gl_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                current_balance REAL DEFAULT 0,
                available_balance REAL,
                currency VARCHAR(3) DEFAULT 'USD',
                is_active INTEGER DEFAULT 1,
                is_primary INTEGER DEFAULT 0,
                plaid_account_id VARCHAR(100),
                plaid_item_id VARCHAR(100),
                plaid_access_token_encrypted TEXT,
                plaid_last_synced_at TIMESTAMP,
                plaid_sync_cursor TEXT,
                plaid_status VARCHAR(20),
                plaid_error_code VARCHAR(50),
                plaid_error_message TEXT,
                last_reconciled_date DATE,
                last_reconciled_balance REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        """))

        conn.execute(text("CREATE INDEX idx_bank_acct_org ON bank_accounts(organization_id)"))
        conn.execute(text("CREATE INDEX idx_bank_acct_gl ON bank_accounts(gl_account_id)"))
        conn.execute(text("CREATE INDEX idx_bank_acct_plaid ON bank_accounts(plaid_item_id)"))
        print("Created bank_accounts table")

        # =====================================================================
        # 16. PLAID ITEMS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE plaid_items (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                item_id VARCHAR(100) NOT NULL,
                access_token_encrypted TEXT NOT NULL,
                institution_id VARCHAR(50),
                institution_name VARCHAR(255),
                institution_logo TEXT,
                status VARCHAR(20) DEFAULT 'active',
                consent_expiration_time TIMESTAMP,
                available_products TEXT DEFAULT '[]',
                billed_products TEXT DEFAULT '[]',
                error_code VARCHAR(50),
                error_message TEXT,
                webhook_url VARCHAR(500),
                last_webhook_at TIMESTAMP,
                last_successful_update TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, item_id)
            )
        """))

        conn.execute(text("CREATE INDEX idx_plaid_item_org ON plaid_items(organization_id)"))
        conn.execute(text("CREATE INDEX idx_plaid_item_status ON plaid_items(status)"))
        print("Created plaid_items table")

        # =====================================================================
        # 17. BANK TRANSACTIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE bank_transactions (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                bank_account_id VARCHAR(36) NOT NULL REFERENCES bank_accounts(id),
                transaction_date DATE NOT NULL,
                post_date DATE,
                amount REAL NOT NULL,
                description TEXT,
                original_description TEXT,
                merchant_name VARCHAR(255),
                category TEXT,
                pending INTEGER DEFAULT 0,
                transaction_type VARCHAR(20),
                plaid_transaction_id VARCHAR(100),
                plaid_account_id VARCHAR(100),
                plaid_category_id VARCHAR(50),
                plaid_personal_finance_category TEXT,
                plaid_payment_channel VARCHAR(30),
                plaid_authorized_date DATE,
                plaid_location TEXT,
                plaid_payment_meta TEXT,
                plaid_merchant_entity_id VARCHAR(100),
                match_status VARCHAR(20) DEFAULT 'unmatched',
                matched_entry_id VARCHAR(36) REFERENCES journal_entries(id),
                matched_at TIMESTAMP,
                matched_by INTEGER,
                auto_matched INTEGER DEFAULT 0,
                match_confidence REAL,
                suggested_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                assigned_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                rule_id VARCHAR(36),
                excluded_reason TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(plaid_transaction_id)
            )
        """))

        conn.execute(text("CREATE INDEX idx_bank_txn_org ON bank_transactions(organization_id)"))
        conn.execute(text("CREATE INDEX idx_bank_txn_account ON bank_transactions(bank_account_id)"))
        conn.execute(text("CREATE INDEX idx_bank_txn_date ON bank_transactions(transaction_date)"))
        conn.execute(text("CREATE INDEX idx_bank_txn_match ON bank_transactions(match_status)"))
        conn.execute(text("CREATE INDEX idx_bank_txn_plaid ON bank_transactions(plaid_transaction_id)"))
        print("Created bank_transactions table")

        # =====================================================================
        # 18. BANK CATEGORIZATION RULES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE bank_categorization_rules (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                priority INTEGER DEFAULT 0,
                match_field VARCHAR(30) NOT NULL,
                match_type VARCHAR(20) NOT NULL,
                match_value TEXT NOT NULL,
                match_case_sensitive INTEGER DEFAULT 0,
                amount_min REAL,
                amount_max REAL,
                transaction_type VARCHAR(20),
                target_account_id VARCHAR(36) NOT NULL REFERENCES chart_of_accounts(id),
                auto_create_entry INTEGER DEFAULT 0,
                description_template TEXT,
                vendor_id VARCHAR(36) REFERENCES ap_vendors(id),
                customer_id VARCHAR(36) REFERENCES ar_customers(id),
                is_active INTEGER DEFAULT 1,
                match_count INTEGER DEFAULT 0,
                last_matched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        """))

        conn.execute(text("CREATE INDEX idx_bank_rule_org ON bank_categorization_rules(organization_id)"))
        conn.execute(text("CREATE INDEX idx_bank_rule_active ON bank_categorization_rules(organization_id, is_active)"))
        print("Created bank_categorization_rules table")

        # =====================================================================
        # 19. BANK RECONCILIATIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE bank_reconciliations (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                bank_account_id VARCHAR(36) NOT NULL REFERENCES bank_accounts(id),
                statement_date DATE NOT NULL,
                statement_ending_balance REAL NOT NULL,
                gl_ending_balance REAL,
                cleared_balance REAL,
                difference REAL,
                status VARCHAR(20) DEFAULT 'in_progress',
                completed_at TIMESTAMP,
                completed_by INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("CREATE INDEX idx_bank_recon_org ON bank_reconciliations(organization_id)"))
        conn.execute(text("CREATE INDEX idx_bank_recon_account ON bank_reconciliations(bank_account_id)"))
        print("Created bank_reconciliations table")

        # =====================================================================
        # 20. BUDGET TEMPLATES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE budget_templates (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                fiscal_year INTEGER NOT NULL,
                budget_type VARCHAR(30) DEFAULT 'annual',
                status VARCHAR(20) DEFAULT 'draft',
                approved_by INTEGER,
                approved_at TIMESTAMP,
                activated_at TIMESTAMP,
                total_revenue REAL DEFAULT 0,
                total_expenses REAL DEFAULT 0,
                notes TEXT,
                copied_from_budget_id VARCHAR(36),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        """))

        conn.execute(text("CREATE INDEX idx_budget_org ON budget_templates(organization_id)"))
        conn.execute(text("CREATE INDEX idx_budget_year ON budget_templates(organization_id, fiscal_year)"))
        conn.execute(text("CREATE INDEX idx_budget_status ON budget_templates(organization_id, status)"))
        print("Created budget_templates table")

        # =====================================================================
        # 21. BUDGET ITEMS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE budget_items (
                id VARCHAR(36) PRIMARY KEY,
                budget_id VARCHAR(36) NOT NULL REFERENCES budget_templates(id) ON DELETE CASCADE,
                account_id VARCHAR(36) NOT NULL REFERENCES chart_of_accounts(id),
                department_id VARCHAR(36),
                period_1 REAL DEFAULT 0,
                period_2 REAL DEFAULT 0,
                period_3 REAL DEFAULT 0,
                period_4 REAL DEFAULT 0,
                period_5 REAL DEFAULT 0,
                period_6 REAL DEFAULT 0,
                period_7 REAL DEFAULT 0,
                period_8 REAL DEFAULT 0,
                period_9 REAL DEFAULT 0,
                period_10 REAL DEFAULT 0,
                period_11 REAL DEFAULT 0,
                period_12 REAL DEFAULT 0,
                annual_total REAL DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(budget_id, account_id, department_id)
            )
        """))

        conn.execute(text("CREATE INDEX idx_budget_item_budget ON budget_items(budget_id)"))
        conn.execute(text("CREATE INDEX idx_budget_item_account ON budget_items(account_id)"))
        print("Created budget_items table")

        # =====================================================================
        # 22. ACCOUNTING AUDIT LOG
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE accounting_audit_log (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                user_id INTEGER,
                action VARCHAR(50) NOT NULL,
                entity_type VARCHAR(50) NOT NULL,
                entity_id VARCHAR(36) NOT NULL,
                entity_number VARCHAR(50),
                old_values TEXT,
                new_values TEXT,
                change_summary TEXT,
                ip_address VARCHAR(50),
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("CREATE INDEX idx_acct_audit_org ON accounting_audit_log(organization_id)"))
        conn.execute(text("CREATE INDEX idx_acct_audit_entity ON accounting_audit_log(entity_type, entity_id)"))
        conn.execute(text("CREATE INDEX idx_acct_audit_user ON accounting_audit_log(user_id)"))
        conn.execute(text("CREATE INDEX idx_acct_audit_date ON accounting_audit_log(created_at)"))
        print("Created accounting_audit_log table")

        # =====================================================================
        # 23. JOURNAL ENTRY TEMPLATES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE journal_entry_templates (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                entry_type VARCHAR(30) DEFAULT 'standard',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        """))

        conn.execute(text("""
            CREATE TABLE journal_entry_template_lines (
                id VARCHAR(36) PRIMARY KEY,
                template_id VARCHAR(36) NOT NULL REFERENCES journal_entry_templates(id) ON DELETE CASCADE,
                account_id VARCHAR(36) NOT NULL REFERENCES chart_of_accounts(id),
                description TEXT,
                debit_amount REAL DEFAULT 0,
                credit_amount REAL DEFAULT 0,
                is_percentage INTEGER DEFAULT 0,
                percentage REAL,
                line_order INTEGER NOT NULL DEFAULT 0
            )
        """))

        conn.execute(text("CREATE INDEX idx_je_template_org ON journal_entry_templates(organization_id)"))
        conn.execute(text("CREATE INDEX idx_je_template_line ON journal_entry_template_lines(template_id)"))
        print("Created journal_entry_templates tables")

        # =====================================================================
        # 24. RECURRING TRANSACTIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE recurring_transactions (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                transaction_type VARCHAR(30) NOT NULL,
                template_data TEXT NOT NULL,
                frequency VARCHAR(20) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE,
                next_date DATE,
                last_generated_date DATE,
                days_before_due INTEGER DEFAULT 0,
                auto_post INTEGER DEFAULT 0,
                auto_send INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                occurrence_count INTEGER DEFAULT 0,
                max_occurrences INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        """))

        conn.execute(text("CREATE INDEX idx_recurring_org ON recurring_transactions(organization_id)"))
        conn.execute(text("CREATE INDEX idx_recurring_next ON recurring_transactions(next_date)"))
        print("Created recurring_transactions table")

        # =====================================================================
        # 25. TAX SETTINGS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE tax_rates (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                tax_code VARCHAR(20) NOT NULL,
                name VARCHAR(100) NOT NULL,
                rate REAL NOT NULL,
                is_compound INTEGER DEFAULT 0,
                is_recoverable INTEGER DEFAULT 1,
                tax_account_id VARCHAR(36) REFERENCES chart_of_accounts(id),
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, tax_code)
            )
        """))

        conn.execute(text("CREATE INDEX idx_tax_org ON tax_rates(organization_id)"))
        print("Created tax_rates table")

        # =====================================================================
        # 26. ACCOUNTING SETTINGS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE accounting_settings (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL UNIQUE,
                fiscal_year_start_month INTEGER DEFAULT 1,
                default_ar_account_id VARCHAR(36),
                default_ap_account_id VARCHAR(36),
                default_revenue_account_id VARCHAR(36),
                default_expense_account_id VARCHAR(36),
                retained_earnings_account_id VARCHAR(36),
                default_bank_account_id VARCHAR(36),
                invoice_prefix VARCHAR(10) DEFAULT 'INV-',
                invoice_next_number INTEGER DEFAULT 1001,
                bill_prefix VARCHAR(10) DEFAULT 'BILL-',
                bill_next_number INTEGER DEFAULT 1001,
                payment_prefix VARCHAR(10) DEFAULT 'PMT-',
                payment_next_number INTEGER DEFAULT 1001,
                journal_prefix VARCHAR(10) DEFAULT 'JE-',
                journal_next_number INTEGER DEFAULT 1001,
                default_payment_terms VARCHAR(20) DEFAULT 'net30',
                require_bill_approval INTEGER DEFAULT 1,
                bill_approval_threshold REAL,
                auto_create_journal_entries INTEGER DEFAULT 1,
                lock_date DATE,
                multi_currency_enabled INTEGER DEFAULT 0,
                base_currency VARCHAR(3) DEFAULT 'USD',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("Created accounting_settings table")

        # Commit all changes
        conn.commit()
        print("\n=== Accounting system tables created successfully! ===")
        print("Tables created: 26")
        print("Indexes created: 50+")


def create_default_chart_of_accounts(conn, org_id: int, created_by_user: int = None):
    """Create default chart of accounts for an organization."""

    accounts = [
        # Assets (1xxx)
        (org_id, '1000', 'Assets', 'asset', None, 'debit', 1, 1000),
        (org_id, '1100', 'Cash and Cash Equivalents', 'asset', 'current_asset', 'debit', 1, 1100),
        (org_id, '1110', 'Operating Checking Account', 'asset', 'current_asset', 'debit', 0, 1110),
        (org_id, '1120', 'Payroll Account', 'asset', 'current_asset', 'debit', 0, 1120),
        (org_id, '1130', 'Savings Account', 'asset', 'current_asset', 'debit', 0, 1130),
        (org_id, '1150', 'Undeposited Funds', 'asset', 'current_asset', 'debit', 1, 1150),
        (org_id, '1200', 'Accounts Receivable', 'asset', 'current_asset', 'debit', 1, 1200),
        (org_id, '1210', 'Trade Receivables', 'asset', 'current_asset', 'debit', 0, 1210),
        (org_id, '1300', 'Prepaid Expenses', 'asset', 'current_asset', 'debit', 0, 1300),
        (org_id, '1500', 'Fixed Assets', 'asset', 'fixed_asset', 'debit', 1, 1500),
        (org_id, '1510', 'Furniture and Equipment', 'asset', 'fixed_asset', 'debit', 0, 1510),
        (org_id, '1520', 'Computer Equipment', 'asset', 'fixed_asset', 'debit', 0, 1520),
        (org_id, '1590', 'Accumulated Depreciation', 'asset', 'fixed_asset', 'credit', 0, 1590),

        # Liabilities (2xxx)
        (org_id, '2000', 'Liabilities', 'liability', None, 'credit', 1, 2000),
        (org_id, '2100', 'Accounts Payable', 'liability', 'current_liability', 'credit', 1, 2100),
        (org_id, '2110', 'Trade Payables', 'liability', 'current_liability', 'credit', 0, 2110),
        (org_id, '2200', 'Credit Cards Payable', 'liability', 'current_liability', 'credit', 0, 2200),
        (org_id, '2300', 'Accrued Expenses', 'liability', 'current_liability', 'credit', 0, 2300),
        (org_id, '2400', 'Payroll Liabilities', 'liability', 'current_liability', 'credit', 0, 2400),
        (org_id, '2410', 'Federal Withholding Payable', 'liability', 'current_liability', 'credit', 0, 2410),
        (org_id, '2420', 'State Withholding Payable', 'liability', 'current_liability', 'credit', 0, 2420),
        (org_id, '2430', 'FICA Payable', 'liability', 'current_liability', 'credit', 0, 2430),
        (org_id, '2500', 'Sales Tax Payable', 'liability', 'current_liability', 'credit', 0, 2500),
        (org_id, '2600', 'Deferred Revenue', 'liability', 'current_liability', 'credit', 0, 2600),
        (org_id, '2700', 'Long-Term Debt', 'liability', 'long_term_liability', 'credit', 0, 2700),

        # Equity (3xxx)
        (org_id, '3000', 'Equity', 'equity', None, 'credit', 1, 3000),
        (org_id, '3100', "Owner's Equity", 'equity', 'equity', 'credit', 0, 3100),
        (org_id, '3200', 'Retained Earnings', 'equity', 'retained_earnings', 'credit', 1, 3200),
        (org_id, '3300', 'Current Year Earnings', 'equity', 'retained_earnings', 'credit', 1, 3300),
        (org_id, '3400', "Owner's Draw", 'equity', 'equity', 'debit', 0, 3400),

        # Revenue (4xxx)
        (org_id, '4000', 'Revenue', 'revenue', None, 'credit', 1, 4000),
        (org_id, '4100', 'Subscription Revenue', 'revenue', 'operating_revenue', 'credit', 0, 4100),
        (org_id, '4110', 'Monthly Subscriptions', 'revenue', 'operating_revenue', 'credit', 0, 4110),
        (org_id, '4120', 'Annual Subscriptions', 'revenue', 'operating_revenue', 'credit', 0, 4120),
        (org_id, '4200', 'Service Revenue', 'revenue', 'operating_revenue', 'credit', 0, 4200),
        (org_id, '4210', 'Implementation Fees', 'revenue', 'operating_revenue', 'credit', 0, 4210),
        (org_id, '4220', 'Training Revenue', 'revenue', 'operating_revenue', 'credit', 0, 4220),
        (org_id, '4230', 'Consulting Revenue', 'revenue', 'operating_revenue', 'credit', 0, 4230),
        (org_id, '4300', 'Usage-Based Revenue', 'revenue', 'operating_revenue', 'credit', 0, 4300),
        (org_id, '4310', 'Overage Charges', 'revenue', 'operating_revenue', 'credit', 0, 4310),
        (org_id, '4320', 'API Usage Revenue', 'revenue', 'operating_revenue', 'credit', 0, 4320),
        (org_id, '4900', 'Other Revenue', 'revenue', 'other_revenue', 'credit', 0, 4900),

        # Cost of Goods Sold (5xxx)
        (org_id, '5000', 'Cost of Revenue', 'expense', 'cost_of_goods', 'debit', 1, 5000),
        (org_id, '5100', 'Cloud Infrastructure', 'expense', 'cost_of_goods', 'debit', 0, 5100),
        (org_id, '5110', 'AWS Costs', 'expense', 'cost_of_goods', 'debit', 0, 5110),
        (org_id, '5120', 'Database Costs', 'expense', 'cost_of_goods', 'debit', 0, 5120),
        (org_id, '5200', 'Third-Party Services', 'expense', 'cost_of_goods', 'debit', 0, 5200),
        (org_id, '5210', 'AI/ML API Costs', 'expense', 'cost_of_goods', 'debit', 0, 5210),
        (org_id, '5220', 'Telephony Costs', 'expense', 'cost_of_goods', 'debit', 0, 5220),
        (org_id, '5230', 'Email Service Costs', 'expense', 'cost_of_goods', 'debit', 0, 5230),
        (org_id, '5300', 'Payment Processing Fees', 'expense', 'cost_of_goods', 'debit', 0, 5300),

        # Operating Expenses (6xxx)
        (org_id, '6000', 'Operating Expenses', 'expense', None, 'debit', 1, 6000),
        (org_id, '6100', 'Payroll Expenses', 'expense', 'operating_expense', 'debit', 0, 6100),
        (org_id, '6110', 'Salaries and Wages', 'expense', 'operating_expense', 'debit', 0, 6110),
        (org_id, '6120', 'Payroll Taxes', 'expense', 'operating_expense', 'debit', 0, 6120),
        (org_id, '6130', 'Employee Benefits', 'expense', 'operating_expense', 'debit', 0, 6130),
        (org_id, '6140', 'Contractor Payments', 'expense', 'operating_expense', 'debit', 0, 6140),
        (org_id, '6200', 'Marketing Expenses', 'expense', 'operating_expense', 'debit', 0, 6200),
        (org_id, '6210', 'Advertising', 'expense', 'operating_expense', 'debit', 0, 6210),
        (org_id, '6220', 'Marketing Software', 'expense', 'operating_expense', 'debit', 0, 6220),
        (org_id, '6300', 'Office Expenses', 'expense', 'operating_expense', 'debit', 0, 6300),
        (org_id, '6310', 'Rent', 'expense', 'operating_expense', 'debit', 0, 6310),
        (org_id, '6320', 'Utilities', 'expense', 'operating_expense', 'debit', 0, 6320),
        (org_id, '6330', 'Office Supplies', 'expense', 'operating_expense', 'debit', 0, 6330),
        (org_id, '6400', 'Professional Services', 'expense', 'operating_expense', 'debit', 0, 6400),
        (org_id, '6410', 'Legal Fees', 'expense', 'operating_expense', 'debit', 0, 6410),
        (org_id, '6420', 'Accounting Fees', 'expense', 'operating_expense', 'debit', 0, 6420),
        (org_id, '6500', 'Software Subscriptions', 'expense', 'operating_expense', 'debit', 0, 6500),
        (org_id, '6600', 'Insurance', 'expense', 'operating_expense', 'debit', 0, 6600),
        (org_id, '6700', 'Travel and Entertainment', 'expense', 'operating_expense', 'debit', 0, 6700),
        (org_id, '6800', 'Depreciation Expense', 'expense', 'operating_expense', 'debit', 0, 6800),
        (org_id, '6900', 'Miscellaneous Expenses', 'expense', 'operating_expense', 'debit', 0, 6900),

        # Other Expenses (7xxx)
        (org_id, '7000', 'Other Expenses', 'expense', 'other_expense', 'debit', 1, 7000),
        (org_id, '7100', 'Interest Expense', 'expense', 'other_expense', 'debit', 0, 7100),
        (org_id, '7200', 'Bank Fees', 'expense', 'other_expense', 'debit', 0, 7200),
        (org_id, '7900', 'Other Expense', 'expense', 'other_expense', 'debit', 0, 7900),
    ]

    for acct in accounts:
        account_id = generate_uuid()
        conn.execute(text("""
            INSERT INTO chart_of_accounts
            (id, organization_id, account_number, name, account_type, account_subtype,
             normal_balance, is_system_account, display_order, created_by)
            VALUES (:id, :org_id, :account_number, :name, :account_type, :account_subtype,
                    :normal_balance, :is_system_account, :display_order, :created_by)
        """), {
            "id": account_id,
            "org_id": acct[0],
            "account_number": acct[1],
            "name": acct[2],
            "account_type": acct[3],
            "account_subtype": acct[4],
            "normal_balance": acct[5],
            "is_system_account": acct[6],
            "display_order": acct[7],
            "created_by": created_by_user
        })

    conn.commit()
    print(f"Created {len(accounts)} default chart of accounts entries for organization {org_id}")


def rollback_migration():
    """Rollback the accounting tables migration."""
    print(f"Using database: {DATABASE_URL[:50]}...")

    with engine.connect() as conn:
        print("Rolling back accounting tables...")

        tables = [
            'accounting_audit_log',
            'budget_items',
            'budget_templates',
            'bank_reconciliations',
            'bank_categorization_rules',
            'bank_transactions',
            'plaid_items',
            'bank_accounts',
            'ap_payment_applications',
            'ap_payments',
            'ap_bill_lines',
            'ap_bills',
            'ap_vendors',
            'ar_payment_applications',
            'ar_payments',
            'ar_invoice_lines',
            'ar_invoices',
            'ar_customers',
            'journal_entry_template_lines',
            'journal_entry_templates',
            'journal_entry_lines',
            'journal_entries',
            'accounting_periods',
            'recurring_transactions',
            'tax_rates',
            'accounting_settings',
            'chart_of_accounts',
        ]

        for table in tables:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                print(f"Dropped {table}")
            except Exception as e:
                print(f"Error dropping {table}: {e}")

        conn.commit()
        print("Rollback complete")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migration()
    else:
        run_migration()
