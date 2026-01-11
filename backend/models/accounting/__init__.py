"""
SQLAlchemy models for the Complete Accounting System.

This module contains models for:
- Chart of Accounts & General Ledger
- Journal Entries
- Accounts Receivable (Customers, Invoices, Payments)
- Accounts Payable (Vendors, Bills, Payments)
- Banking & Plaid Integration
- Budgeting
- Accounting Periods
"""

from .core import (
    ChartOfAccounts,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
    JournalEntryTemplate,
    JournalEntryTemplateLine,
    AccountingSettings,
    TaxRate,
    RecurringTransaction,
    AccountingAuditLog,
)

from .accounts_receivable import (
    ARCustomer,
    ARInvoice,
    ARInvoiceLine,
    ARPayment,
    ARPaymentApplication,
)

from .accounts_payable import (
    APVendor,
    APBill,
    APBillLine,
    APPayment,
    APPaymentApplication,
)

from .banking import (
    BankAccount,
    PlaidItem,
    BankTransaction,
    BankCategorizationRule,
    BankReconciliation,
)

from .budgeting import (
    BudgetTemplate,
    BudgetItem,
)

__all__ = [
    # Core
    'ChartOfAccounts',
    'AccountingPeriod',
    'JournalEntry',
    'JournalEntryLine',
    'JournalEntryTemplate',
    'JournalEntryTemplateLine',
    'AccountingSettings',
    'TaxRate',
    'RecurringTransaction',
    'AccountingAuditLog',
    # AR
    'ARCustomer',
    'ARInvoice',
    'ARInvoiceLine',
    'ARPayment',
    'ARPaymentApplication',
    # AP
    'APVendor',
    'APBill',
    'APBillLine',
    'APPayment',
    'APPaymentApplication',
    # Banking
    'BankAccount',
    'PlaidItem',
    'BankTransaction',
    'BankCategorizationRule',
    'BankReconciliation',
    # Budgeting
    'BudgetTemplate',
    'BudgetItem',
]
