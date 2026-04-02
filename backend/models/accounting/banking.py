"""
Banking Models: Bank Accounts, Plaid Integration, Transactions, Reconciliation.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


class BankAccount(Base):
    """Bank accounts for cash management."""
    __tablename__ = "bank_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    account_name = Column(String(255), nullable=False)
    account_type = Column(String(30), nullable=False)  # checking, savings, credit_card, money_market, loan, other
    institution_name = Column(String(255))
    account_number_last4 = Column(String(4))
    routing_number = Column(String(20))
    gl_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    current_balance = Column(Numeric(15, 2), default=0)
    available_balance = Column(Numeric(15, 2))
    currency = Column(String(3), default='USD')
    is_active = Column(Boolean, default=True)
    is_primary = Column(Boolean, default=False)
    # Plaid integration
    plaid_account_id = Column(String(100))
    plaid_item_id = Column(String(100))
    plaid_access_token_encrypted = Column(Text)
    plaid_last_synced_at = Column(DateTime)
    plaid_sync_cursor = Column(Text)
    plaid_status = Column(String(20))  # active, needs_reauth, error, disconnected
    plaid_error_code = Column(String(50))
    plaid_error_message = Column(Text)
    # Reconciliation
    last_reconciled_date = Column(Date)
    last_reconciled_balance = Column(Numeric(15, 2))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    gl_account = relationship("ChartOfAccounts", foreign_keys=[gl_account_id])
    transactions = relationship("BankTransaction", back_populates="bank_account")
    reconciliations = relationship("BankReconciliation", back_populates="bank_account")

    __table_args__ = (
        CheckConstraint("account_type IN ('checking', 'savings', 'credit_card', 'money_market', 'loan', 'other')", name="ck_bank_acct_type"),
        CheckConstraint("plaid_status IN ('active', 'needs_reauth', 'error', 'disconnected') OR plaid_status IS NULL", name="ck_plaid_status"),
    )

    @property
    def is_connected_to_plaid(self):
        return self.plaid_item_id is not None and self.plaid_status == 'active'

    def to_dict(self):
        return {
            'id': str(self.id),
            'account_name': self.account_name,
            'account_type': self.account_type,
            'institution_name': self.institution_name,
            'account_number_last4': self.account_number_last4,
            'current_balance': float(self.current_balance or 0),
            'available_balance': float(self.available_balance) if self.available_balance else None,
            'currency': self.currency,
            'is_active': self.is_active,
            'is_primary': self.is_primary,
            'is_connected_to_plaid': self.is_connected_to_plaid,
            'plaid_status': self.plaid_status,
            'plaid_last_synced_at': self.plaid_last_synced_at.isoformat() if self.plaid_last_synced_at else None,
            'last_reconciled_date': self.last_reconciled_date.isoformat() if self.last_reconciled_date else None,
            'gl_account_id': str(self.gl_account_id) if self.gl_account_id else None,
        }


class PlaidItem(Base):
    """Plaid institution connections."""
    __tablename__ = "plaid_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    item_id = Column(String(100), nullable=False)
    access_token_encrypted = Column(Text, nullable=False)
    institution_id = Column(String(50))
    institution_name = Column(String(255))
    institution_logo = Column(Text)
    status = Column(String(20), default='active')  # active, needs_reauth, removed, error
    consent_expiration_time = Column(DateTime)
    available_products = Column(JSONB, default=list)
    billed_products = Column(JSONB, default=list)
    error_code = Column(String(50))
    error_message = Column(Text)
    webhook_url = Column(String(500))
    last_webhook_at = Column(DateTime)
    last_successful_update = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('organization_id', 'item_id', name='uq_plaid_item'),
        CheckConstraint("status IN ('active', 'needs_reauth', 'removed', 'error')", name="ck_plaid_item_status"),
    )

    @property
    def needs_reauth(self):
        return self.status == 'needs_reauth'

    def to_dict(self):
        return {
            'id': str(self.id),
            'item_id': self.item_id,
            'institution_id': self.institution_id,
            'institution_name': self.institution_name,
            'institution_logo': self.institution_logo,
            'status': self.status,
            'consent_expiration_time': self.consent_expiration_time.isoformat() if self.consent_expiration_time else None,
            'last_successful_update': self.last_successful_update.isoformat() if self.last_successful_update else None,
            'error_code': self.error_code,
            'error_message': self.error_message,
        }


class BankTransaction(Base):
    """Bank transactions imported from Plaid or manual entry."""
    __tablename__ = "bank_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id"), nullable=False)
    transaction_date = Column(Date, nullable=False)
    post_date = Column(Date)
    amount = Column(Numeric(15, 2), nullable=False)
    description = Column(Text)
    original_description = Column(Text)
    merchant_name = Column(String(255))
    category = Column(JSONB)
    pending = Column(Boolean, default=False)
    transaction_type = Column(String(20))  # debit, credit
    # Plaid data
    plaid_transaction_id = Column(String(100), unique=True)
    plaid_account_id = Column(String(100))
    plaid_category_id = Column(String(50))
    plaid_personal_finance_category = Column(JSONB)
    plaid_payment_channel = Column(String(30))
    plaid_authorized_date = Column(Date)
    plaid_location = Column(JSONB)
    plaid_payment_meta = Column(JSONB)
    plaid_merchant_entity_id = Column(String(100))
    # Matching & reconciliation
    match_status = Column(String(20), default='unmatched')  # unmatched, suggested, matched, excluded, split
    matched_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"))
    matched_at = Column(DateTime)
    matched_by = Column(Integer)
    auto_matched = Column(Boolean, default=False)
    match_confidence = Column(Numeric(3, 2))
    # Categorization
    suggested_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    assigned_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"))
    rule_id = Column(UUID(as_uuid=True))
    excluded_reason = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    bank_account = relationship("BankAccount", back_populates="transactions")
    matched_entry = relationship("JournalEntry", foreign_keys=[matched_entry_id])
    suggested_account = relationship("ChartOfAccounts", foreign_keys=[suggested_account_id])
    assigned_account = relationship("ChartOfAccounts", foreign_keys=[assigned_account_id])

    __table_args__ = (
        CheckConstraint("transaction_type IN ('debit', 'credit') OR transaction_type IS NULL", name="ck_bank_txn_type"),
        CheckConstraint("match_status IN ('unmatched', 'suggested', 'matched', 'excluded', 'split')", name="ck_bank_txn_match"),
        Index('idx_bank_txn_date', 'transaction_date'),
        Index('idx_bank_txn_match', 'match_status'),
    )

    @property
    def is_matched(self):
        return self.match_status == 'matched'

    @property
    def is_excluded(self):
        return self.match_status == 'excluded'

    @property
    def is_inflow(self):
        return self.amount > 0 or self.transaction_type == 'credit'

    @property
    def is_outflow(self):
        return self.amount < 0 or self.transaction_type == 'debit'

    def to_dict(self):
        return {
            'id': str(self.id),
            'bank_account_id': str(self.bank_account_id),
            'transaction_date': self.transaction_date.isoformat() if self.transaction_date else None,
            'post_date': self.post_date.isoformat() if self.post_date else None,
            'amount': float(self.amount or 0),
            'description': self.description,
            'merchant_name': self.merchant_name,
            'category': self.category,
            'pending': self.pending,
            'transaction_type': self.transaction_type,
            'match_status': self.match_status,
            'matched_entry_id': str(self.matched_entry_id) if self.matched_entry_id else None,
            'match_confidence': float(self.match_confidence) if self.match_confidence else None,
            'assigned_account_id': str(self.assigned_account_id) if self.assigned_account_id else None,
            'suggested_account_id': str(self.suggested_account_id) if self.suggested_account_id else None,
            'notes': self.notes,
            'plaid_transaction_id': self.plaid_transaction_id,
        }


class BankCategorizationRule(Base):
    """Rules for auto-categorizing bank transactions."""
    __tablename__ = "bank_categorization_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    priority = Column(Integer, default=0)
    # Match criteria
    match_field = Column(String(30), nullable=False)  # description, merchant_name, amount, category
    match_type = Column(String(20), nullable=False)  # contains, starts_with, ends_with, exact, regex
    match_value = Column(Text, nullable=False)
    match_case_sensitive = Column(Boolean, default=False)
    amount_min = Column(Numeric(15, 2))
    amount_max = Column(Numeric(15, 2))
    transaction_type = Column(String(20))  # debit, credit
    # Action
    target_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"), nullable=False)
    auto_create_entry = Column(Boolean, default=False)
    description_template = Column(Text)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("ap_vendors.id"))
    customer_id = Column(UUID(as_uuid=True), ForeignKey("ar_customers.id"))
    is_active = Column(Boolean, default=True)
    match_count = Column(Integer, default=0)
    last_matched_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    target_account = relationship("ChartOfAccounts", foreign_keys=[target_account_id])

    __table_args__ = (
        CheckConstraint("match_field IN ('description', 'merchant_name', 'amount', 'category')", name="ck_rule_field"),
        CheckConstraint("match_type IN ('contains', 'starts_with', 'ends_with', 'exact', 'regex')", name="ck_rule_type"),
    )

    def matches(self, transaction: BankTransaction) -> bool:
        """Check if this rule matches a transaction."""
        # Get the field value to match
        if self.match_field == 'description':
            value = transaction.description or ''
        elif self.match_field == 'merchant_name':
            value = transaction.merchant_name or ''
        elif self.match_field == 'amount':
            # Amount matching
            amount = abs(float(transaction.amount or 0))
            if self.amount_min and amount < float(self.amount_min):
                return False
            if self.amount_max and amount > float(self.amount_max):
                return False
            return True
        else:
            return False

        # Apply case sensitivity
        if not self.match_case_sensitive:
            value = value.lower()
            match_value = self.match_value.lower()
        else:
            match_value = self.match_value

        # Check match type
        if self.match_type == 'contains':
            return match_value in value
        elif self.match_type == 'starts_with':
            return value.startswith(match_value)
        elif self.match_type == 'ends_with':
            return value.endswith(match_value)
        elif self.match_type == 'exact':
            return value == match_value
        elif self.match_type == 'regex':
            import re
            return bool(re.search(match_value, value))

        return False

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'priority': self.priority,
            'match_field': self.match_field,
            'match_type': self.match_type,
            'match_value': self.match_value,
            'match_case_sensitive': self.match_case_sensitive,
            'amount_min': float(self.amount_min) if self.amount_min else None,
            'amount_max': float(self.amount_max) if self.amount_max else None,
            'target_account_id': str(self.target_account_id),
            'auto_create_entry': self.auto_create_entry,
            'is_active': self.is_active,
            'match_count': self.match_count,
        }


class BankReconciliation(Base):
    """Bank reconciliation sessions."""
    __tablename__ = "bank_reconciliations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, nullable=False, index=True)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id"), nullable=False)
    statement_date = Column(Date, nullable=False)
    statement_ending_balance = Column(Numeric(15, 2), nullable=False)
    gl_ending_balance = Column(Numeric(15, 2))
    cleared_balance = Column(Numeric(15, 2))
    difference = Column(Numeric(15, 2))
    status = Column(String(20), default='in_progress')  # in_progress, completed, void
    completed_at = Column(DateTime)
    completed_by = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    bank_account = relationship("BankAccount", back_populates="reconciliations")

    __table_args__ = (
        CheckConstraint("status IN ('in_progress', 'completed', 'void')", name="ck_recon_status"),
    )

    @property
    def is_balanced(self):
        return self.difference == Decimal('0') if self.difference is not None else False

    def to_dict(self):
        return {
            'id': str(self.id),
            'bank_account_id': str(self.bank_account_id),
            'statement_date': self.statement_date.isoformat() if self.statement_date else None,
            'statement_ending_balance': float(self.statement_ending_balance or 0),
            'gl_ending_balance': float(self.gl_ending_balance) if self.gl_ending_balance else None,
            'cleared_balance': float(self.cleared_balance) if self.cleared_balance else None,
            'difference': float(self.difference) if self.difference else None,
            'status': self.status,
            'is_balanced': self.is_balanced,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
