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
"""

from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Run the accounting tables migration."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if main table already exists
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
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                account_number VARCHAR(20) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                account_type VARCHAR(50) NOT NULL
                    CHECK (account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense')),
                account_subtype VARCHAR(50)
                    CHECK (account_subtype IN (
                        'current_asset', 'fixed_asset', 'other_asset',
                        'current_liability', 'long_term_liability',
                        'equity', 'retained_earnings',
                        'operating_revenue', 'other_revenue',
                        'cost_of_goods', 'operating_expense', 'other_expense'
                    )),
                parent_account_id UUID REFERENCES chart_of_accounts(id),
                normal_balance VARCHAR(10) NOT NULL CHECK (normal_balance IN ('debit', 'credit')),
                is_bank_account BOOLEAN DEFAULT FALSE,
                bank_account_id UUID,
                currency VARCHAR(3) DEFAULT 'USD',
                is_active BOOLEAN DEFAULT TRUE,
                is_system_account BOOLEAN DEFAULT FALSE,
                tax_code VARCHAR(20),
                display_order INTEGER,
                opening_balance NUMERIC(15, 2) DEFAULT 0,
                opening_balance_date DATE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id),
                UNIQUE(organization_id, account_number)
            );

            CREATE INDEX idx_coa_org ON chart_of_accounts(organization_id);
            CREATE INDEX idx_coa_org_type ON chart_of_accounts(organization_id, account_type);
            CREATE INDEX idx_coa_parent ON chart_of_accounts(parent_account_id);
            CREATE INDEX idx_coa_active ON chart_of_accounts(organization_id, is_active);
        """))
        print("Created chart_of_accounts table")

        # =====================================================================
        # 2. ACCOUNTING PERIODS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE accounting_periods (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                period_name VARCHAR(50) NOT NULL,
                period_type VARCHAR(20) NOT NULL CHECK (period_type IN ('month', 'quarter', 'year')),
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status VARCHAR(20) DEFAULT 'open' CHECK (status IN ('open', 'closing', 'closed', 'locked')),
                closed_at TIMESTAMP,
                closed_by INTEGER REFERENCES users(id),
                fiscal_year INTEGER NOT NULL,
                fiscal_period INTEGER NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, start_date, end_date)
            );

            CREATE INDEX idx_period_org ON accounting_periods(organization_id);
            CREATE INDEX idx_period_org_status ON accounting_periods(organization_id, status);
            CREATE INDEX idx_period_dates ON accounting_periods(organization_id, start_date, end_date);
        """))
        print("Created accounting_periods table")

        # =====================================================================
        # 3. JOURNAL ENTRIES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE journal_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                entry_number VARCHAR(20) NOT NULL,
                entry_date DATE NOT NULL,
                period_id UUID REFERENCES accounting_periods(id),
                description TEXT NOT NULL,
                entry_type VARCHAR(30) NOT NULL
                    CHECK (entry_type IN ('standard', 'adjusting', 'closing', 'reversing', 'opening')),
                source_type VARCHAR(50),
                source_id UUID,
                status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'posted', 'void')),
                posted_at TIMESTAMP,
                posted_by INTEGER REFERENCES users(id),
                voided_at TIMESTAMP,
                voided_by INTEGER REFERENCES users(id),
                void_reason TEXT,
                reversed_by_entry_id UUID REFERENCES journal_entries(id),
                reverses_entry_id UUID REFERENCES journal_entries(id),
                memo TEXT,
                reference_number VARCHAR(100),
                total_debits NUMERIC(15, 2) DEFAULT 0,
                total_credits NUMERIC(15, 2) DEFAULT 0,
                attachments JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id),
                UNIQUE(organization_id, entry_number)
            );

            CREATE INDEX idx_je_org ON journal_entries(organization_id);
            CREATE INDEX idx_je_org_date ON journal_entries(organization_id, entry_date);
            CREATE INDEX idx_je_period ON journal_entries(period_id);
            CREATE INDEX idx_je_source ON journal_entries(source_type, source_id);
            CREATE INDEX idx_je_status ON journal_entries(organization_id, status);
        """))
        print("Created journal_entries table")

        # =====================================================================
        # 4. JOURNAL ENTRY LINES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE journal_entry_lines (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                journal_entry_id UUID NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
                account_id UUID NOT NULL REFERENCES chart_of_accounts(id),
                description TEXT,
                debit_amount NUMERIC(15, 2) DEFAULT 0 CHECK (debit_amount >= 0),
                credit_amount NUMERIC(15, 2) DEFAULT 0 CHECK (credit_amount >= 0),
                currency VARCHAR(3) DEFAULT 'USD',
                exchange_rate NUMERIC(10, 6) DEFAULT 1.0,
                department_id UUID,
                project_id UUID,
                loan_id UUID,
                customer_id UUID,
                vendor_id UUID,
                line_order INTEGER NOT NULL DEFAULT 0,
                reconciled BOOLEAN DEFAULT FALSE,
                reconciled_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT chk_debit_or_credit CHECK (
                    (debit_amount > 0 AND credit_amount = 0) OR
                    (credit_amount > 0 AND debit_amount = 0)
                )
            );

            CREATE INDEX idx_jel_entry ON journal_entry_lines(journal_entry_id);
            CREATE INDEX idx_jel_account ON journal_entry_lines(account_id);
            CREATE INDEX idx_jel_customer ON journal_entry_lines(customer_id);
            CREATE INDEX idx_jel_vendor ON journal_entry_lines(vendor_id);
        """))
        print("Created journal_entry_lines table")

        # =====================================================================
        # 5. AR CUSTOMERS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_customers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                customer_number VARCHAR(20) NOT NULL,
                name VARCHAR(255) NOT NULL,
                company_name VARCHAR(255),
                email VARCHAR(255),
                phone VARCHAR(50),
                billing_address JSONB DEFAULT '{}',
                shipping_address JSONB DEFAULT '{}',
                payment_terms VARCHAR(20) DEFAULT 'net30'
                    CHECK (payment_terms IN ('immediate', 'net15', 'net30', 'net45', 'net60', 'net90')),
                credit_limit NUMERIC(12, 2),
                current_balance NUMERIC(12, 2) DEFAULT 0,
                ar_account_id UUID REFERENCES chart_of_accounts(id),
                tax_exempt BOOLEAN DEFAULT FALSE,
                tax_id VARCHAR(50),
                notes TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                contact_id INTEGER,
                borrower_id INTEGER,
                tenant_account_id UUID,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id),
                UNIQUE(organization_id, customer_number)
            );

            CREATE INDEX idx_ar_cust_org ON ar_customers(organization_id);
            CREATE INDEX idx_ar_cust_active ON ar_customers(organization_id, is_active);
            CREATE INDEX idx_ar_cust_tenant ON ar_customers(tenant_account_id);
        """))
        print("Created ar_customers table")

        # =====================================================================
        # 6. AR INVOICES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_invoices (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                invoice_number VARCHAR(30) NOT NULL,
                customer_id UUID NOT NULL REFERENCES ar_customers(id),
                invoice_date DATE NOT NULL,
                due_date DATE NOT NULL,
                status VARCHAR(20) DEFAULT 'draft'
                    CHECK (status IN ('draft', 'sent', 'viewed', 'partial', 'paid', 'overdue', 'void', 'written_off')),
                subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
                tax_amount NUMERIC(12, 2) DEFAULT 0,
                discount_amount NUMERIC(12, 2) DEFAULT 0,
                discount_percent NUMERIC(5, 2),
                total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                amount_paid NUMERIC(12, 2) DEFAULT 0,
                currency VARCHAR(3) DEFAULT 'USD',
                terms TEXT,
                notes TEXT,
                memo TEXT,
                footer TEXT,
                journal_entry_id UUID REFERENCES journal_entries(id),
                source_type VARCHAR(50),
                source_id UUID,
                sent_at TIMESTAMP,
                sent_to VARCHAR(255),
                viewed_at TIMESTAMP,
                last_reminder_at TIMESTAMP,
                reminder_count INTEGER DEFAULT 0,
                paid_at TIMESTAMP,
                voided_at TIMESTAMP,
                voided_by INTEGER REFERENCES users(id),
                void_reason TEXT,
                template_id UUID,
                pdf_url TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id),
                UNIQUE(organization_id, invoice_number)
            );

            CREATE INDEX idx_ar_inv_org ON ar_invoices(organization_id);
            CREATE INDEX idx_ar_inv_customer ON ar_invoices(customer_id);
            CREATE INDEX idx_ar_inv_status ON ar_invoices(organization_id, status);
            CREATE INDEX idx_ar_inv_due ON ar_invoices(organization_id, due_date);
            CREATE INDEX idx_ar_inv_date ON ar_invoices(organization_id, invoice_date);
        """))
        print("Created ar_invoices table")

        # =====================================================================
        # 7. AR INVOICE LINES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_invoice_lines (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                invoice_id UUID NOT NULL REFERENCES ar_invoices(id) ON DELETE CASCADE,
                line_order INTEGER NOT NULL DEFAULT 0,
                item_code VARCHAR(50),
                description TEXT NOT NULL,
                quantity NUMERIC(10, 4) DEFAULT 1,
                unit_price NUMERIC(12, 4) NOT NULL,
                amount NUMERIC(12, 2) NOT NULL,
                discount_percent NUMERIC(5, 2),
                discount_amount NUMERIC(12, 2) DEFAULT 0,
                revenue_account_id UUID REFERENCES chart_of_accounts(id),
                tax_code VARCHAR(20),
                tax_rate NUMERIC(5, 4),
                tax_amount NUMERIC(12, 2) DEFAULT 0,
                product_id UUID,
                service_id UUID,
                loan_id UUID,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_ar_inv_line_inv ON ar_invoice_lines(invoice_id);
        """))
        print("Created ar_invoice_lines table")

        # =====================================================================
        # 8. AR PAYMENTS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                payment_number VARCHAR(30) NOT NULL,
                customer_id UUID NOT NULL REFERENCES ar_customers(id),
                payment_date DATE NOT NULL,
                amount NUMERIC(12, 2) NOT NULL,
                amount_applied NUMERIC(12, 2) DEFAULT 0,
                amount_unapplied NUMERIC(12, 2) DEFAULT 0,
                payment_method VARCHAR(30) NOT NULL
                    CHECK (payment_method IN ('check', 'ach', 'wire', 'credit_card', 'cash', 'stripe', 'other')),
                reference_number VARCHAR(100),
                deposit_account_id UUID REFERENCES chart_of_accounts(id),
                status VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending', 'cleared', 'returned', 'void')),
                memo TEXT,
                journal_entry_id UUID REFERENCES journal_entries(id),
                stripe_payment_id VARCHAR(100),
                stripe_charge_id VARCHAR(100),
                bank_transaction_id UUID,
                reconciled_at TIMESTAMP,
                voided_at TIMESTAMP,
                voided_by INTEGER REFERENCES users(id),
                void_reason TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id),
                UNIQUE(organization_id, payment_number)
            );

            CREATE INDEX idx_ar_pay_org ON ar_payments(organization_id);
            CREATE INDEX idx_ar_pay_customer ON ar_payments(customer_id);
            CREATE INDEX idx_ar_pay_status ON ar_payments(organization_id, status);
            CREATE INDEX idx_ar_pay_date ON ar_payments(organization_id, payment_date);
        """))
        print("Created ar_payments table")

        # =====================================================================
        # 9. AR PAYMENT APPLICATIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ar_payment_applications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                payment_id UUID NOT NULL REFERENCES ar_payments(id) ON DELETE CASCADE,
                invoice_id UUID NOT NULL REFERENCES ar_invoices(id),
                amount_applied NUMERIC(12, 2) NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id)
            );

            CREATE INDEX idx_ar_pay_app_payment ON ar_payment_applications(payment_id);
            CREATE INDEX idx_ar_pay_app_invoice ON ar_payment_applications(invoice_id);
        """))
        print("Created ar_payment_applications table")

        # =====================================================================
        # 10. AP VENDORS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_vendors (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                vendor_number VARCHAR(20) NOT NULL,
                name VARCHAR(255) NOT NULL,
                company_name VARCHAR(255),
                email VARCHAR(255),
                phone VARCHAR(50),
                address JSONB DEFAULT '{}',
                payment_terms VARCHAR(20) DEFAULT 'net30'
                    CHECK (payment_terms IN ('immediate', 'net15', 'net30', 'net45', 'net60', 'net90')),
                default_expense_account_id UUID REFERENCES chart_of_accounts(id),
                ap_account_id UUID REFERENCES chart_of_accounts(id),
                tax_id VARCHAR(50),
                requires_1099 BOOLEAN DEFAULT FALSE,
                form_1099_type VARCHAR(20),
                current_balance NUMERIC(12, 2) DEFAULT 0,
                credit_limit NUMERIC(12, 2),
                payment_method_default VARCHAR(30),
                bank_account_info JSONB DEFAULT '{}',
                is_active BOOLEAN DEFAULT TRUE,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id),
                UNIQUE(organization_id, vendor_number)
            );

            CREATE INDEX idx_ap_vend_org ON ap_vendors(organization_id);
            CREATE INDEX idx_ap_vend_active ON ap_vendors(organization_id, is_active);
            CREATE INDEX idx_ap_vend_1099 ON ap_vendors(organization_id, requires_1099);
        """))
        print("Created ap_vendors table")

        # =====================================================================
        # 11. AP BILLS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_bills (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                bill_number VARCHAR(30) NOT NULL,
                vendor_id UUID NOT NULL REFERENCES ap_vendors(id),
                vendor_invoice_number VARCHAR(100),
                bill_date DATE NOT NULL,
                due_date DATE NOT NULL,
                status VARCHAR(20) DEFAULT 'draft'
                    CHECK (status IN ('draft', 'pending_approval', 'approved', 'partial', 'paid', 'void')),
                subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
                tax_amount NUMERIC(12, 2) DEFAULT 0,
                shipping_amount NUMERIC(12, 2) DEFAULT 0,
                discount_amount NUMERIC(12, 2) DEFAULT 0,
                total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                amount_paid NUMERIC(12, 2) DEFAULT 0,
                currency VARCHAR(3) DEFAULT 'USD',
                terms TEXT,
                notes TEXT,
                memo TEXT,
                approval_status VARCHAR(20) DEFAULT 'pending'
                    CHECK (approval_status IN ('pending', 'approved', 'rejected')),
                approved_by INTEGER REFERENCES users(id),
                approved_at TIMESTAMP,
                rejection_reason TEXT,
                journal_entry_id UUID REFERENCES journal_entries(id),
                recurring_bill_id UUID,
                document_url TEXT,
                voided_at TIMESTAMP,
                voided_by INTEGER REFERENCES users(id),
                void_reason TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id),
                UNIQUE(organization_id, bill_number)
            );

            CREATE INDEX idx_ap_bill_org ON ap_bills(organization_id);
            CREATE INDEX idx_ap_bill_vendor ON ap_bills(vendor_id);
            CREATE INDEX idx_ap_bill_status ON ap_bills(organization_id, status);
            CREATE INDEX idx_ap_bill_due ON ap_bills(organization_id, due_date);
            CREATE INDEX idx_ap_bill_approval ON ap_bills(organization_id, approval_status);
        """))
        print("Created ap_bills table")

        # =====================================================================
        # 12. AP BILL LINES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_bill_lines (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                bill_id UUID NOT NULL REFERENCES ap_bills(id) ON DELETE CASCADE,
                line_order INTEGER NOT NULL DEFAULT 0,
                item_code VARCHAR(50),
                description TEXT NOT NULL,
                quantity NUMERIC(10, 4) DEFAULT 1,
                unit_price NUMERIC(12, 4) NOT NULL,
                amount NUMERIC(12, 2) NOT NULL,
                expense_account_id UUID REFERENCES chart_of_accounts(id),
                tax_code VARCHAR(20),
                tax_amount NUMERIC(12, 2) DEFAULT 0,
                department_id UUID,
                project_id UUID,
                billable BOOLEAN DEFAULT FALSE,
                billable_customer_id UUID REFERENCES ar_customers(id),
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_ap_bill_line_bill ON ap_bill_lines(bill_id);
        """))
        print("Created ap_bill_lines table")

        # =====================================================================
        # 13. AP PAYMENTS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                payment_number VARCHAR(30) NOT NULL,
                vendor_id UUID NOT NULL REFERENCES ap_vendors(id),
                payment_date DATE NOT NULL,
                amount NUMERIC(12, 2) NOT NULL,
                amount_applied NUMERIC(12, 2) DEFAULT 0,
                payment_method VARCHAR(30) NOT NULL
                    CHECK (payment_method IN ('check', 'ach', 'wire', 'credit_card', 'cash', 'other')),
                check_number VARCHAR(20),
                bank_account_id UUID REFERENCES chart_of_accounts(id),
                status VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending', 'printed', 'sent', 'cleared', 'void')),
                memo TEXT,
                journal_entry_id UUID REFERENCES journal_entries(id),
                bank_transaction_id UUID,
                reconciled_at TIMESTAMP,
                cleared_at TIMESTAMP,
                voided_at TIMESTAMP,
                voided_by INTEGER REFERENCES users(id),
                void_reason TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id),
                UNIQUE(organization_id, payment_number)
            );

            CREATE INDEX idx_ap_pay_org ON ap_payments(organization_id);
            CREATE INDEX idx_ap_pay_vendor ON ap_payments(vendor_id);
            CREATE INDEX idx_ap_pay_status ON ap_payments(organization_id, status);
            CREATE INDEX idx_ap_pay_date ON ap_payments(organization_id, payment_date);
        """))
        print("Created ap_payments table")

        # =====================================================================
        # 14. AP PAYMENT APPLICATIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE ap_payment_applications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                payment_id UUID NOT NULL REFERENCES ap_payments(id) ON DELETE CASCADE,
                bill_id UUID NOT NULL REFERENCES ap_bills(id),
                amount_applied NUMERIC(12, 2) NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id)
            );

            CREATE INDEX idx_ap_pay_app_payment ON ap_payment_applications(payment_id);
            CREATE INDEX idx_ap_pay_app_bill ON ap_payment_applications(bill_id);
        """))
        print("Created ap_payment_applications table")

        # =====================================================================
        # 15. BANK ACCOUNTS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE bank_accounts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                account_name VARCHAR(255) NOT NULL,
                account_type VARCHAR(30) NOT NULL
                    CHECK (account_type IN ('checking', 'savings', 'credit_card', 'money_market', 'loan', 'other')),
                institution_name VARCHAR(255),
                account_number_last4 VARCHAR(4),
                routing_number VARCHAR(20),
                gl_account_id UUID REFERENCES chart_of_accounts(id),
                current_balance NUMERIC(15, 2) DEFAULT 0,
                available_balance NUMERIC(15, 2),
                currency VARCHAR(3) DEFAULT 'USD',
                is_active BOOLEAN DEFAULT TRUE,
                is_primary BOOLEAN DEFAULT FALSE,
                plaid_account_id VARCHAR(100),
                plaid_item_id VARCHAR(100),
                plaid_access_token_encrypted TEXT,
                plaid_last_synced_at TIMESTAMP,
                plaid_sync_cursor TEXT,
                plaid_status VARCHAR(20)
                    CHECK (plaid_status IN ('active', 'needs_reauth', 'error', 'disconnected')),
                plaid_error_code VARCHAR(50),
                plaid_error_message TEXT,
                last_reconciled_date DATE,
                last_reconciled_balance NUMERIC(15, 2),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id)
            );

            CREATE INDEX idx_bank_acct_org ON bank_accounts(organization_id);
            CREATE INDEX idx_bank_acct_gl ON bank_accounts(gl_account_id);
            CREATE INDEX idx_bank_acct_plaid ON bank_accounts(plaid_item_id);
        """))
        print("Created bank_accounts table")

        # =====================================================================
        # 16. PLAID ITEMS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE plaid_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                item_id VARCHAR(100) NOT NULL,
                access_token_encrypted TEXT NOT NULL,
                institution_id VARCHAR(50),
                institution_name VARCHAR(255),
                institution_logo TEXT,
                status VARCHAR(20) DEFAULT 'active'
                    CHECK (status IN ('active', 'needs_reauth', 'removed', 'error')),
                consent_expiration_time TIMESTAMP,
                available_products JSONB DEFAULT '[]',
                billed_products JSONB DEFAULT '[]',
                error_code VARCHAR(50),
                error_message TEXT,
                webhook_url VARCHAR(500),
                last_webhook_at TIMESTAMP,
                last_successful_update TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, item_id)
            );

            CREATE INDEX idx_plaid_item_org ON plaid_items(organization_id);
            CREATE INDEX idx_plaid_item_status ON plaid_items(status);
        """))
        print("Created plaid_items table")

        # =====================================================================
        # 17. BANK TRANSACTIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE bank_transactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                bank_account_id UUID NOT NULL REFERENCES bank_accounts(id),
                transaction_date DATE NOT NULL,
                post_date DATE,
                amount NUMERIC(15, 2) NOT NULL,
                description TEXT,
                original_description TEXT,
                merchant_name VARCHAR(255),
                category JSONB,
                pending BOOLEAN DEFAULT FALSE,
                transaction_type VARCHAR(20)
                    CHECK (transaction_type IN ('debit', 'credit')),
                plaid_transaction_id VARCHAR(100),
                plaid_account_id VARCHAR(100),
                plaid_category_id VARCHAR(50),
                plaid_personal_finance_category JSONB,
                plaid_payment_channel VARCHAR(30),
                plaid_authorized_date DATE,
                plaid_location JSONB,
                plaid_payment_meta JSONB,
                plaid_merchant_entity_id VARCHAR(100),
                match_status VARCHAR(20) DEFAULT 'unmatched'
                    CHECK (match_status IN ('unmatched', 'suggested', 'matched', 'excluded', 'split')),
                matched_entry_id UUID REFERENCES journal_entries(id),
                matched_at TIMESTAMP,
                matched_by INTEGER REFERENCES users(id),
                auto_matched BOOLEAN DEFAULT FALSE,
                match_confidence NUMERIC(3, 2),
                suggested_account_id UUID REFERENCES chart_of_accounts(id),
                assigned_account_id UUID REFERENCES chart_of_accounts(id),
                rule_id UUID,
                excluded_reason TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(plaid_transaction_id)
            );

            CREATE INDEX idx_bank_txn_org ON bank_transactions(organization_id);
            CREATE INDEX idx_bank_txn_account ON bank_transactions(bank_account_id);
            CREATE INDEX idx_bank_txn_date ON bank_transactions(transaction_date);
            CREATE INDEX idx_bank_txn_match ON bank_transactions(match_status);
            CREATE INDEX idx_bank_txn_plaid ON bank_transactions(plaid_transaction_id);
        """))
        print("Created bank_transactions table")

        # =====================================================================
        # 18. BANK CATEGORIZATION RULES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE bank_categorization_rules (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                priority INTEGER DEFAULT 0,
                match_field VARCHAR(30) NOT NULL
                    CHECK (match_field IN ('description', 'merchant_name', 'amount', 'category')),
                match_type VARCHAR(20) NOT NULL
                    CHECK (match_type IN ('contains', 'starts_with', 'ends_with', 'exact', 'regex')),
                match_value TEXT NOT NULL,
                match_case_sensitive BOOLEAN DEFAULT FALSE,
                amount_min NUMERIC(15, 2),
                amount_max NUMERIC(15, 2),
                transaction_type VARCHAR(20),
                target_account_id UUID NOT NULL REFERENCES chart_of_accounts(id),
                auto_create_entry BOOLEAN DEFAULT FALSE,
                description_template TEXT,
                vendor_id UUID REFERENCES ap_vendors(id),
                customer_id UUID REFERENCES ar_customers(id),
                is_active BOOLEAN DEFAULT TRUE,
                match_count INTEGER DEFAULT 0,
                last_matched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id)
            );

            CREATE INDEX idx_bank_rule_org ON bank_categorization_rules(organization_id);
            CREATE INDEX idx_bank_rule_active ON bank_categorization_rules(organization_id, is_active);
        """))
        print("Created bank_categorization_rules table")

        # =====================================================================
        # 19. BANK RECONCILIATIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE bank_reconciliations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                bank_account_id UUID NOT NULL REFERENCES bank_accounts(id),
                statement_date DATE NOT NULL,
                statement_ending_balance NUMERIC(15, 2) NOT NULL,
                gl_ending_balance NUMERIC(15, 2),
                cleared_balance NUMERIC(15, 2),
                difference NUMERIC(15, 2),
                status VARCHAR(20) DEFAULT 'in_progress'
                    CHECK (status IN ('in_progress', 'completed', 'void')),
                completed_at TIMESTAMP,
                completed_by INTEGER REFERENCES users(id),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_bank_recon_org ON bank_reconciliations(organization_id);
            CREATE INDEX idx_bank_recon_account ON bank_reconciliations(bank_account_id);
        """))
        print("Created bank_reconciliations table")

        # =====================================================================
        # 20. BUDGET TEMPLATES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE budget_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                fiscal_year INTEGER NOT NULL,
                budget_type VARCHAR(30) DEFAULT 'annual'
                    CHECK (budget_type IN ('annual', 'quarterly', 'monthly', 'rolling')),
                status VARCHAR(20) DEFAULT 'draft'
                    CHECK (status IN ('draft', 'pending_approval', 'approved', 'active', 'closed')),
                approved_by INTEGER REFERENCES users(id),
                approved_at TIMESTAMP,
                activated_at TIMESTAMP,
                total_revenue NUMERIC(15, 2) DEFAULT 0,
                total_expenses NUMERIC(15, 2) DEFAULT 0,
                notes TEXT,
                copied_from_budget_id UUID REFERENCES budget_templates(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id)
            );

            CREATE INDEX idx_budget_org ON budget_templates(organization_id);
            CREATE INDEX idx_budget_year ON budget_templates(organization_id, fiscal_year);
            CREATE INDEX idx_budget_status ON budget_templates(organization_id, status);
        """))
        print("Created budget_templates table")

        # =====================================================================
        # 21. BUDGET ITEMS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE budget_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                budget_id UUID NOT NULL REFERENCES budget_templates(id) ON DELETE CASCADE,
                account_id UUID NOT NULL REFERENCES chart_of_accounts(id),
                department_id UUID,
                period_1 NUMERIC(15, 2) DEFAULT 0,
                period_2 NUMERIC(15, 2) DEFAULT 0,
                period_3 NUMERIC(15, 2) DEFAULT 0,
                period_4 NUMERIC(15, 2) DEFAULT 0,
                period_5 NUMERIC(15, 2) DEFAULT 0,
                period_6 NUMERIC(15, 2) DEFAULT 0,
                period_7 NUMERIC(15, 2) DEFAULT 0,
                period_8 NUMERIC(15, 2) DEFAULT 0,
                period_9 NUMERIC(15, 2) DEFAULT 0,
                period_10 NUMERIC(15, 2) DEFAULT 0,
                period_11 NUMERIC(15, 2) DEFAULT 0,
                period_12 NUMERIC(15, 2) DEFAULT 0,
                annual_total NUMERIC(15, 2) GENERATED ALWAYS AS (
                    period_1 + period_2 + period_3 + period_4 + period_5 + period_6 +
                    period_7 + period_8 + period_9 + period_10 + period_11 + period_12
                ) STORED,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(budget_id, account_id, department_id)
            );

            CREATE INDEX idx_budget_item_budget ON budget_items(budget_id);
            CREATE INDEX idx_budget_item_account ON budget_items(account_id);
        """))
        print("Created budget_items table")

        # =====================================================================
        # 22. ACCOUNTING AUDIT LOG
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE accounting_audit_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                user_id INTEGER REFERENCES users(id),
                action VARCHAR(50) NOT NULL
                    CHECK (action IN (
                        'create', 'update', 'delete', 'post', 'void', 'reverse',
                        'approve', 'reject', 'send', 'apply', 'reconcile', 'close', 'reopen'
                    )),
                entity_type VARCHAR(50) NOT NULL,
                entity_id UUID NOT NULL,
                entity_number VARCHAR(50),
                old_values JSONB,
                new_values JSONB,
                change_summary TEXT,
                ip_address INET,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX idx_acct_audit_org ON accounting_audit_log(organization_id);
            CREATE INDEX idx_acct_audit_entity ON accounting_audit_log(entity_type, entity_id);
            CREATE INDEX idx_acct_audit_user ON accounting_audit_log(user_id);
            CREATE INDEX idx_acct_audit_date ON accounting_audit_log(created_at);
        """))
        print("Created accounting_audit_log table")

        # =====================================================================
        # 23. JOURNAL ENTRY TEMPLATES
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE journal_entry_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                entry_type VARCHAR(30) DEFAULT 'standard',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id)
            );

            CREATE TABLE journal_entry_template_lines (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                template_id UUID NOT NULL REFERENCES journal_entry_templates(id) ON DELETE CASCADE,
                account_id UUID NOT NULL REFERENCES chart_of_accounts(id),
                description TEXT,
                debit_amount NUMERIC(15, 2) DEFAULT 0,
                credit_amount NUMERIC(15, 2) DEFAULT 0,
                is_percentage BOOLEAN DEFAULT FALSE,
                percentage NUMERIC(5, 2),
                line_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX idx_je_template_org ON journal_entry_templates(organization_id);
            CREATE INDEX idx_je_template_line ON journal_entry_template_lines(template_id);
        """))
        print("Created journal_entry_templates tables")

        # =====================================================================
        # 24. RECURRING TRANSACTIONS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE recurring_transactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                transaction_type VARCHAR(30) NOT NULL
                    CHECK (transaction_type IN ('invoice', 'bill', 'journal_entry')),
                template_data JSONB NOT NULL,
                frequency VARCHAR(20) NOT NULL
                    CHECK (frequency IN ('daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'annually')),
                start_date DATE NOT NULL,
                end_date DATE,
                next_date DATE,
                last_generated_date DATE,
                days_before_due INTEGER DEFAULT 0,
                auto_post BOOLEAN DEFAULT FALSE,
                auto_send BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                occurrence_count INTEGER DEFAULT 0,
                max_occurrences INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id)
            );

            CREATE INDEX idx_recurring_org ON recurring_transactions(organization_id);
            CREATE INDEX idx_recurring_next ON recurring_transactions(next_date) WHERE is_active = TRUE;
        """))
        print("Created recurring_transactions table")

        # =====================================================================
        # 25. TAX SETTINGS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE tax_rates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL,
                tax_code VARCHAR(20) NOT NULL,
                name VARCHAR(100) NOT NULL,
                rate NUMERIC(5, 4) NOT NULL,
                is_compound BOOLEAN DEFAULT FALSE,
                is_recoverable BOOLEAN DEFAULT TRUE,
                tax_account_id UUID REFERENCES chart_of_accounts(id),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, tax_code)
            );

            CREATE INDEX idx_tax_org ON tax_rates(organization_id);
        """))
        print("Created tax_rates table")

        # =====================================================================
        # 26. ACCOUNTING SETTINGS
        # =====================================================================
        conn.execute(text("""
            CREATE TABLE accounting_settings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organization_id INTEGER NOT NULL UNIQUE,
                fiscal_year_start_month INTEGER DEFAULT 1,
                default_ar_account_id UUID REFERENCES chart_of_accounts(id),
                default_ap_account_id UUID REFERENCES chart_of_accounts(id),
                default_revenue_account_id UUID REFERENCES chart_of_accounts(id),
                default_expense_account_id UUID REFERENCES chart_of_accounts(id),
                retained_earnings_account_id UUID REFERENCES chart_of_accounts(id),
                default_bank_account_id UUID REFERENCES bank_accounts(id),
                invoice_prefix VARCHAR(10) DEFAULT 'INV-',
                invoice_next_number INTEGER DEFAULT 1001,
                bill_prefix VARCHAR(10) DEFAULT 'BILL-',
                bill_next_number INTEGER DEFAULT 1001,
                payment_prefix VARCHAR(10) DEFAULT 'PMT-',
                payment_next_number INTEGER DEFAULT 1001,
                journal_prefix VARCHAR(10) DEFAULT 'JE-',
                journal_next_number INTEGER DEFAULT 1001,
                default_payment_terms VARCHAR(20) DEFAULT 'net30',
                require_bill_approval BOOLEAN DEFAULT TRUE,
                bill_approval_threshold NUMERIC(12, 2),
                auto_create_journal_entries BOOLEAN DEFAULT TRUE,
                lock_date DATE,
                multi_currency_enabled BOOLEAN DEFAULT FALSE,
                base_currency VARCHAR(3) DEFAULT 'USD',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """))
        print("Created accounting_settings table")

        # =====================================================================
        # 27. DEFAULT CHART OF ACCOUNTS
        # =====================================================================
        conn.execute(text("""
            -- This function creates default chart of accounts for a new organization
            CREATE OR REPLACE FUNCTION create_default_chart_of_accounts(org_id INTEGER, created_by_user INTEGER)
            RETURNS void AS $$
            BEGIN
                -- Assets (1xxx)
                INSERT INTO chart_of_accounts (organization_id, account_number, name, account_type, account_subtype, normal_balance, is_system_account, display_order, created_by) VALUES
                (org_id, '1000', 'Assets', 'asset', NULL, 'debit', TRUE, 1000, created_by_user),
                (org_id, '1100', 'Cash and Cash Equivalents', 'asset', 'current_asset', 'debit', TRUE, 1100, created_by_user),
                (org_id, '1110', 'Operating Checking Account', 'asset', 'current_asset', 'debit', FALSE, 1110, created_by_user),
                (org_id, '1120', 'Payroll Account', 'asset', 'current_asset', 'debit', FALSE, 1120, created_by_user),
                (org_id, '1130', 'Savings Account', 'asset', 'current_asset', 'debit', FALSE, 1130, created_by_user),
                (org_id, '1150', 'Undeposited Funds', 'asset', 'current_asset', 'debit', TRUE, 1150, created_by_user),
                (org_id, '1200', 'Accounts Receivable', 'asset', 'current_asset', 'debit', TRUE, 1200, created_by_user),
                (org_id, '1210', 'Trade Receivables', 'asset', 'current_asset', 'debit', FALSE, 1210, created_by_user),
                (org_id, '1300', 'Prepaid Expenses', 'asset', 'current_asset', 'debit', FALSE, 1300, created_by_user),
                (org_id, '1500', 'Fixed Assets', 'asset', 'fixed_asset', 'debit', TRUE, 1500, created_by_user),
                (org_id, '1510', 'Furniture and Equipment', 'asset', 'fixed_asset', 'debit', FALSE, 1510, created_by_user),
                (org_id, '1520', 'Computer Equipment', 'asset', 'fixed_asset', 'debit', FALSE, 1520, created_by_user),
                (org_id, '1590', 'Accumulated Depreciation', 'asset', 'fixed_asset', 'credit', FALSE, 1590, created_by_user),

                -- Liabilities (2xxx)
                (org_id, '2000', 'Liabilities', 'liability', NULL, 'credit', TRUE, 2000, created_by_user),
                (org_id, '2100', 'Accounts Payable', 'liability', 'current_liability', 'credit', TRUE, 2100, created_by_user),
                (org_id, '2110', 'Trade Payables', 'liability', 'current_liability', 'credit', FALSE, 2110, created_by_user),
                (org_id, '2200', 'Credit Cards Payable', 'liability', 'current_liability', 'credit', FALSE, 2200, created_by_user),
                (org_id, '2300', 'Accrued Expenses', 'liability', 'current_liability', 'credit', FALSE, 2300, created_by_user),
                (org_id, '2400', 'Payroll Liabilities', 'liability', 'current_liability', 'credit', FALSE, 2400, created_by_user),
                (org_id, '2410', 'Federal Withholding Payable', 'liability', 'current_liability', 'credit', FALSE, 2410, created_by_user),
                (org_id, '2420', 'State Withholding Payable', 'liability', 'current_liability', 'credit', FALSE, 2420, created_by_user),
                (org_id, '2430', 'FICA Payable', 'liability', 'current_liability', 'credit', FALSE, 2430, created_by_user),
                (org_id, '2500', 'Sales Tax Payable', 'liability', 'current_liability', 'credit', FALSE, 2500, created_by_user),
                (org_id, '2600', 'Deferred Revenue', 'liability', 'current_liability', 'credit', FALSE, 2600, created_by_user),
                (org_id, '2700', 'Long-Term Debt', 'liability', 'long_term_liability', 'credit', FALSE, 2700, created_by_user),

                -- Equity (3xxx)
                (org_id, '3000', 'Equity', 'equity', NULL, 'credit', TRUE, 3000, created_by_user),
                (org_id, '3100', 'Owner''s Equity', 'equity', 'equity', 'credit', FALSE, 3100, created_by_user),
                (org_id, '3200', 'Retained Earnings', 'equity', 'retained_earnings', 'credit', TRUE, 3200, created_by_user),
                (org_id, '3300', 'Current Year Earnings', 'equity', 'retained_earnings', 'credit', TRUE, 3300, created_by_user),
                (org_id, '3400', 'Owner''s Draw', 'equity', 'equity', 'debit', FALSE, 3400, created_by_user),

                -- Revenue (4xxx)
                (org_id, '4000', 'Revenue', 'revenue', NULL, 'credit', TRUE, 4000, created_by_user),
                (org_id, '4100', 'Subscription Revenue', 'revenue', 'operating_revenue', 'credit', FALSE, 4100, created_by_user),
                (org_id, '4110', 'Monthly Subscriptions', 'revenue', 'operating_revenue', 'credit', FALSE, 4110, created_by_user),
                (org_id, '4120', 'Annual Subscriptions', 'revenue', 'operating_revenue', 'credit', FALSE, 4120, created_by_user),
                (org_id, '4200', 'Service Revenue', 'revenue', 'operating_revenue', 'credit', FALSE, 4200, created_by_user),
                (org_id, '4210', 'Implementation Fees', 'revenue', 'operating_revenue', 'credit', FALSE, 4210, created_by_user),
                (org_id, '4220', 'Training Revenue', 'revenue', 'operating_revenue', 'credit', FALSE, 4220, created_by_user),
                (org_id, '4230', 'Consulting Revenue', 'revenue', 'operating_revenue', 'credit', FALSE, 4230, created_by_user),
                (org_id, '4300', 'Usage-Based Revenue', 'revenue', 'operating_revenue', 'credit', FALSE, 4300, created_by_user),
                (org_id, '4310', 'Overage Charges', 'revenue', 'operating_revenue', 'credit', FALSE, 4310, created_by_user),
                (org_id, '4320', 'API Usage Revenue', 'revenue', 'operating_revenue', 'credit', FALSE, 4320, created_by_user),
                (org_id, '4900', 'Other Revenue', 'revenue', 'other_revenue', 'credit', FALSE, 4900, created_by_user),

                -- Cost of Goods Sold (5xxx)
                (org_id, '5000', 'Cost of Revenue', 'expense', 'cost_of_goods', 'debit', TRUE, 5000, created_by_user),
                (org_id, '5100', 'Cloud Infrastructure', 'expense', 'cost_of_goods', 'debit', FALSE, 5100, created_by_user),
                (org_id, '5110', 'AWS Costs', 'expense', 'cost_of_goods', 'debit', FALSE, 5110, created_by_user),
                (org_id, '5120', 'Database Costs', 'expense', 'cost_of_goods', 'debit', FALSE, 5120, created_by_user),
                (org_id, '5200', 'Third-Party Services', 'expense', 'cost_of_goods', 'debit', FALSE, 5200, created_by_user),
                (org_id, '5210', 'AI/ML API Costs', 'expense', 'cost_of_goods', 'debit', FALSE, 5210, created_by_user),
                (org_id, '5220', 'Telephony Costs', 'expense', 'cost_of_goods', 'debit', FALSE, 5220, created_by_user),
                (org_id, '5230', 'Email Service Costs', 'expense', 'cost_of_goods', 'debit', FALSE, 5230, created_by_user),
                (org_id, '5300', 'Payment Processing Fees', 'expense', 'cost_of_goods', 'debit', FALSE, 5300, created_by_user),

                -- Operating Expenses (6xxx)
                (org_id, '6000', 'Operating Expenses', 'expense', NULL, 'debit', TRUE, 6000, created_by_user),
                (org_id, '6100', 'Payroll Expenses', 'expense', 'operating_expense', 'debit', FALSE, 6100, created_by_user),
                (org_id, '6110', 'Salaries and Wages', 'expense', 'operating_expense', 'debit', FALSE, 6110, created_by_user),
                (org_id, '6120', 'Payroll Taxes', 'expense', 'operating_expense', 'debit', FALSE, 6120, created_by_user),
                (org_id, '6130', 'Employee Benefits', 'expense', 'operating_expense', 'debit', FALSE, 6130, created_by_user),
                (org_id, '6140', 'Contractor Payments', 'expense', 'operating_expense', 'debit', FALSE, 6140, created_by_user),
                (org_id, '6200', 'Marketing Expenses', 'expense', 'operating_expense', 'debit', FALSE, 6200, created_by_user),
                (org_id, '6210', 'Advertising', 'expense', 'operating_expense', 'debit', FALSE, 6210, created_by_user),
                (org_id, '6220', 'Marketing Software', 'expense', 'operating_expense', 'debit', FALSE, 6220, created_by_user),
                (org_id, '6300', 'Office Expenses', 'expense', 'operating_expense', 'debit', FALSE, 6300, created_by_user),
                (org_id, '6310', 'Rent', 'expense', 'operating_expense', 'debit', FALSE, 6310, created_by_user),
                (org_id, '6320', 'Utilities', 'expense', 'operating_expense', 'debit', FALSE, 6320, created_by_user),
                (org_id, '6330', 'Office Supplies', 'expense', 'operating_expense', 'debit', FALSE, 6330, created_by_user),
                (org_id, '6400', 'Professional Services', 'expense', 'operating_expense', 'debit', FALSE, 6400, created_by_user),
                (org_id, '6410', 'Legal Fees', 'expense', 'operating_expense', 'debit', FALSE, 6410, created_by_user),
                (org_id, '6420', 'Accounting Fees', 'expense', 'operating_expense', 'debit', FALSE, 6420, created_by_user),
                (org_id, '6500', 'Software Subscriptions', 'expense', 'operating_expense', 'debit', FALSE, 6500, created_by_user),
                (org_id, '6600', 'Insurance', 'expense', 'operating_expense', 'debit', FALSE, 6600, created_by_user),
                (org_id, '6700', 'Travel and Entertainment', 'expense', 'operating_expense', 'debit', FALSE, 6700, created_by_user),
                (org_id, '6800', 'Depreciation Expense', 'expense', 'operating_expense', 'debit', FALSE, 6800, created_by_user),
                (org_id, '6900', 'Miscellaneous Expenses', 'expense', 'operating_expense', 'debit', FALSE, 6900, created_by_user),

                -- Other Expenses (7xxx)
                (org_id, '7000', 'Other Expenses', 'expense', 'other_expense', 'debit', TRUE, 7000, created_by_user),
                (org_id, '7100', 'Interest Expense', 'expense', 'other_expense', 'debit', FALSE, 7100, created_by_user),
                (org_id, '7200', 'Bank Fees', 'expense', 'other_expense', 'debit', FALSE, 7200, created_by_user),
                (org_id, '7900', 'Other Expense', 'expense', 'other_expense', 'debit', FALSE, 7900, created_by_user);

                -- Create accounting settings
                INSERT INTO accounting_settings (
                    organization_id,
                    default_ar_account_id,
                    default_ap_account_id,
                    default_revenue_account_id,
                    default_expense_account_id,
                    retained_earnings_account_id
                )
                SELECT
                    org_id,
                    (SELECT id FROM chart_of_accounts WHERE organization_id = org_id AND account_number = '1200'),
                    (SELECT id FROM chart_of_accounts WHERE organization_id = org_id AND account_number = '2100'),
                    (SELECT id FROM chart_of_accounts WHERE organization_id = org_id AND account_number = '4100'),
                    (SELECT id FROM chart_of_accounts WHERE organization_id = org_id AND account_number = '6900'),
                    (SELECT id FROM chart_of_accounts WHERE organization_id = org_id AND account_number = '3200');
            END;
            $$ LANGUAGE plpgsql;
        """))
        print("Created default chart of accounts function")

        # Commit all changes
        conn.commit()
        print("\n=== Accounting system tables created successfully! ===")
        print("Tables created: 26")
        print("Indexes created: 50+")
        print("Functions created: 1 (create_default_chart_of_accounts)")


def rollback_migration():
    """Rollback the accounting tables migration."""
    engine = create_engine(DATABASE_URL)

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
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                print(f"Dropped {table}")
            except Exception as e:
                print(f"Error dropping {table}: {e}")

        # Drop function
        conn.execute(text("DROP FUNCTION IF EXISTS create_default_chart_of_accounts(INTEGER, INTEGER)"))

        conn.commit()
        print("Rollback complete")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migration()
    else:
        run_migration()
