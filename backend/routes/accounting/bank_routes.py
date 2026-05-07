"""
Banking API Routes with Plaid Integration.

Provides endpoints for:
- Bank account management
- Plaid Link integration (connect banks)
- Transaction syncing and categorization
- Bank reconciliation
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import case, func, and_, or_
from typing import Optional, List, Literal
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pydantic import BaseModel, Field
import uuid
import os
import json
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)

from database import get_db
from models.accounting.core import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    AccountingPeriod, AccountingAuditLog
)
from models.accounting.banking import (
    BankAccount, PlaidItem, BankTransaction,
    BankCategorizationRule, BankReconciliation
)

# Plaid client setup
try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.transactions_sync_request import TransactionsSyncRequest
    from plaid.model.accounts_get_request import AccountsGetRequest
    from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
    from plaid.model.item_remove_request import ItemRemoveRequest
    from plaid.model.products import Products
    from plaid.model.country_code import CountryCode
    PLAID_AVAILABLE = True
except ImportError:
    PLAID_AVAILABLE = False

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

router = APIRouter(prefix="/api/v1/accounting/banking", tags=["Banking"])


# =============================================================================
# Plaid Configuration
# =============================================================================

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
PLAID_SECRET = os.getenv("PLAID_SECRET", "")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")  # sandbox, development, production
PLAID_WEBHOOK_URL = os.getenv("PLAID_WEBHOOK_URL", "")
PLAID_WEBHOOK_VERIFY_KEY = os.getenv("PLAID_WEBHOOK_VERIFY_KEY", "")

def get_plaid_client():
    """Get configured Plaid client."""
    if not PLAID_AVAILABLE:
        return None

    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        return None

    configuration = plaid.Configuration(
        host=getattr(plaid.Environment, PLAID_ENV.capitalize(), plaid.Environment.Sandbox),
        api_key={
            'clientId': PLAID_CLIENT_ID,
            'secret': PLAID_SECRET,
        }
    )

    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


# =============================================================================
# Pydantic Schemas
# =============================================================================

class BankAccountCreate(BaseModel):
    account_name: str = Field(..., min_length=1, max_length=255)
    account_type: str = Field(default="checking", pattern="^(checking|savings|credit_card|money_market|other)$")
    institution_name: Optional[str] = None
    account_number_last4: Optional[str] = Field(None, max_length=4)
    routing_number: Optional[str] = None
    gl_account_id: str  # Link to Chart of Accounts
    opening_balance: Decimal = Field(default=Decimal("0"))
    opening_balance_date: Optional[date] = None
    is_primary: bool = False
    notes: Optional[str] = None


class BankAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    institution_name: Optional[str] = None
    gl_account_id: Optional[str] = None
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class CategorizationRuleCreate(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=255)
    match_type: str = Field(default="contains", pattern="^(contains|starts_with|ends_with|exact|regex)$")
    match_field: str = Field(default="description", pattern="^(description|merchant_name|category)$")
    match_value: str
    target_account_id: str
    apply_to_account_id: Optional[str] = None  # Specific bank account or all
    priority: int = Field(default=100, ge=1, le=1000)
    is_active: bool = True


class TransactionCategorizeRequest(BaseModel):
    account_id: str
    description: Optional[str] = None
    notes: Optional[str] = None


class ReconciliationCreate(BaseModel):
    bank_account_id: str
    statement_date: date
    statement_ending_balance: Decimal
    statement_start_date: Optional[date] = None


class ReconciliationUpdate(BaseModel):
    cleared_transactions: List[str] = []  # Transaction IDs to mark as cleared
    adjustments: Optional[List[dict]] = None  # [{"description": "...", "amount": 10.00}]


# =============================================================================
# Helper Functions
# =============================================================================

def get_organization_id(request: Request) -> int:
    """Get organization ID from tenant context middleware."""
    org_id = getattr(request.state, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def log_audit(db: Session, org_id: int, user_id: int, action: str,
              entity_type: str, entity_id: uuid.UUID, entity_number: str = None,
              old_values: dict = None, new_values: dict = None, summary: str = None):
    """Log an audit entry."""
    audit = AccountingAuditLog(
        organization_id=org_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_number=entity_number,
        old_values=old_values,
        new_values=new_values,
        change_summary=summary,
    )
    db.add(audit)


def apply_categorization_rules(
    db: Session,
    transaction: BankTransaction,
    org_id: int,
) -> Optional[str]:
    """Apply categorization rules to a transaction."""
    rules = db.query(BankCategorizationRule).filter(
        BankCategorizationRule.organization_id == org_id,
        BankCategorizationRule.is_active == True,
        or_(
            BankCategorizationRule.apply_to_account_id == None,
            BankCategorizationRule.apply_to_account_id == transaction.bank_account_id
        )
    ).order_by(BankCategorizationRule.priority).all()

    for rule in rules:
        if rule.matches(transaction):
            return str(rule.target_account_id)

    return None


# =============================================================================
# Bank Account Routes
# =============================================================================

@router.get("/accounts")
async def list_bank_accounts(
    request: Request,
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    """List bank accounts."""
    org_id = get_organization_id(request)

    query = db.query(BankAccount).filter(
        BankAccount.organization_id == org_id
    )

    if not include_inactive:
        query = query.filter(BankAccount.is_active == True)

    accounts = query.order_by(BankAccount.is_primary.desc(), BankAccount.account_name).all()

    # Get current balances
    result = []
    for account in accounts:
        account_dict = account.to_dict()

        # Calculate balance from transactions
        balance = db.query(func.sum(
            BankTransaction.amount
        )).filter(
            BankTransaction.bank_account_id == account.id,
            BankTransaction.status != 'excluded'
        ).scalar() or Decimal("0")

        account_dict['calculated_balance'] = float(account.opening_balance + balance)
        account_dict['plaid_connected'] = account.plaid_item_id is not None
        result.append(account_dict)

    return {
        "success": True,
        "accounts": result,
    }


@router.get("/accounts/{account_id}")
async def get_bank_account(
    request: Request,
    account_id: str,
    db: Session = Depends(get_db),
):
    """Get a single bank account with details."""
    org_id = get_organization_id(request)

    account = db.query(BankAccount).filter(
        BankAccount.id == account_id,
        BankAccount.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    result = account.to_dict()

    # Get transaction stats
    stats = db.query(
        func.count(BankTransaction.id).label('total_transactions'),
        func.sum(case((BankTransaction.match_status == 'unmatched', 1), else_=0)).label('unmatched'),
        func.sum(case((BankTransaction.match_status == 'matched', 1), else_=0)).label('matched'),
    ).filter(
        BankTransaction.bank_account_id == account_id
    ).first()

    result['transaction_stats'] = {
        'total': stats.total_transactions or 0,
        'unmatched': int(stats.unmatched or 0),
        'matched': int(stats.matched or 0),
    }

    # Get last sync info
    if account.plaid_item:
        result['last_sync'] = account.plaid_item.last_successful_sync.isoformat() if account.plaid_item.last_successful_sync else None
        result['sync_status'] = account.plaid_item.sync_status

    return {
        "success": True,
        "account": result,
    }


@router.post("/accounts")
async def create_bank_account(
    request: Request,
    data: BankAccountCreate,
    db: Session = Depends(get_db),
):
    """Create a new bank account (manual, not Plaid-connected)."""
    org_id = get_organization_id(request)

    # Validate GL account
    gl_account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == data.gl_account_id,
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.is_active == True
    ).first()

    if not gl_account:
        raise HTTPException(status_code=404, detail="GL account not found")

    # If setting as primary, unset others
    if data.is_primary:
        db.query(BankAccount).filter(
            BankAccount.organization_id == org_id,
            BankAccount.is_primary == True
        ).update({'is_primary': False})

    account = BankAccount(
        organization_id=org_id,
        account_name=data.account_name,
        account_type=data.account_type,
        institution_name=data.institution_name,
        account_number_last4=data.account_number_last4,
        routing_number=data.routing_number,
        gl_account_id=data.gl_account_id,
        opening_balance=data.opening_balance,
        opening_balance_date=data.opening_balance_date or date.today(),
        current_balance=data.opening_balance,
        is_primary=data.is_primary,
        notes=data.notes,
    )

    db.add(account)
    db.flush()

    log_audit(
        db, org_id, 1, 'create', 'bank_account', account.id,
        entity_number=account.account_name,
        summary=f"Created bank account {account.account_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Bank account {account.account_name} created",
        "account": account.to_dict(),
    }


@router.put("/accounts/{account_id}")
async def update_bank_account(
    request: Request,
    account_id: str,
    data: BankAccountUpdate,
    db: Session = Depends(get_db),
):
    """Update a bank account."""
    org_id = get_organization_id(request)

    account = db.query(BankAccount).filter(
        BankAccount.id == account_id,
        BankAccount.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    old_values = account.to_dict()

    # If setting as primary, unset others
    if data.is_primary:
        db.query(BankAccount).filter(
            BankAccount.organization_id == org_id,
            BankAccount.is_primary == True,
            BankAccount.id != account_id
        ).update({'is_primary': False})

    update_data = data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for key, value in update_data.items():
        if key not in _protected:
            setattr(account, key, value)

    log_audit(
        db, org_id, 1, 'update', 'bank_account', account.id,
        entity_number=account.account_name,
        old_values=old_values,
        summary=f"Updated bank account {account.account_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Bank account {account.account_name} updated",
        "account": account.to_dict(),
    }


# =============================================================================
# Plaid Integration Routes
# =============================================================================

@router.get("/plaid/status")
async def get_plaid_status():
    """Check Plaid integration status."""
    client = get_plaid_client()

    return {
        "success": True,
        "plaid_available": PLAID_AVAILABLE,
        "plaid_configured": client is not None,
        "environment": PLAID_ENV,
    }


@router.post("/plaid/create-link-token")
async def create_plaid_link_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a Plaid Link token for connecting a bank."""
    org_id = get_organization_id(request)
    client = get_plaid_client()

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Plaid integration not configured. Set PLAID_CLIENT_ID and PLAID_SECRET."
        )

    try:
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(
                client_user_id=f"org_{org_id}"
            ),
            client_name="Perennia Accounting",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
            webhook=PLAID_WEBHOOK_URL if PLAID_WEBHOOK_URL else None,
        )

        response = client.link_token_create(request)

        return {
            "success": True,
            "link_token": response.link_token,
            "expiration": response.expiration.isoformat(),
        }

    except plaid.ApiException as e:
        error_response = json.loads(e.body)
        raise HTTPException(
            status_code=400,
            detail=f"Plaid error: {error_response.get('error_code', 'UNKNOWN_ERROR')}"
        )


@router.post("/plaid/exchange-token")
async def exchange_plaid_public_token(
    request: Request,
    public_token: str,
    institution_id: str,
    institution_name: str,
    accounts: List[dict],  # [{"id": "...", "name": "...", "type": "...", "mask": "..."}]
    db: Session = Depends(get_db),
):
    """Exchange Plaid public token for access token and create bank accounts."""
    org_id = get_organization_id(request)
    client = get_plaid_client()

    if not client:
        raise HTTPException(status_code=503, detail="Plaid integration not configured")

    try:
        # Exchange public token
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)

        access_token = exchange_response.access_token
        item_id = exchange_response.item_id

        # Create Plaid item record
        plaid_item = PlaidItem(
            organization_id=org_id,
            item_id=item_id,
            access_token=access_token,  # Should be encrypted in production
            institution_id=institution_id,
            institution_name=institution_name,
            products=['transactions'],
            sync_status='pending',
        )

        db.add(plaid_item)
        db.flush()

        # Create bank accounts for each selected account
        created_accounts = []

        for acct in accounts:
            # Find or create a GL account for this bank
            gl_account = db.query(ChartOfAccounts).filter(
                ChartOfAccounts.organization_id == org_id,
                ChartOfAccounts.account_sub_type == 'cash',
                ChartOfAccounts.is_active == True
            ).first()

            if not gl_account:
                raise HTTPException(
                    status_code=400,
                    detail="No cash GL account found. Create one first."
                )

            bank_account = BankAccount(
                organization_id=org_id,
                account_name=f"{institution_name} - {acct['name']}",
                account_type=acct.get('type', 'checking').lower(),
                institution_name=institution_name,
                account_number_last4=acct.get('mask'),
                gl_account_id=gl_account.id,
                plaid_item_id=plaid_item.id,
                plaid_account_id=acct['id'],
                opening_balance=Decimal("0"),
                opening_balance_date=date.today(),
            )

            db.add(bank_account)
            db.flush()
            created_accounts.append(bank_account)

            log_audit(
                db, org_id, 1, 'create', 'bank_account', bank_account.id,
                entity_number=bank_account.account_name,
                summary=f"Connected bank account via Plaid: {bank_account.account_name}"
            )

        db.commit()

        return {
            "success": True,
            "message": f"Connected {len(created_accounts)} bank account(s)",
            "plaid_item_id": str(plaid_item.id),
            "accounts": [a.to_dict() for a in created_accounts],
        }

    except plaid.ApiException as e:
        error_response = json.loads(e.body)
        raise HTTPException(
            status_code=400,
            detail=f"Plaid error: {error_response.get('error_code', 'UNKNOWN_ERROR')}"
        )


@router.post("/plaid/sync/{account_id}")
async def sync_plaid_transactions(
    request: Request,
    account_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Sync transactions from Plaid for a bank account."""
    org_id = get_organization_id(request)

    account = db.query(BankAccount).filter(
        BankAccount.id == account_id,
        BankAccount.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    if not account.plaid_item_id:
        raise HTTPException(status_code=400, detail="Account is not connected to Plaid")

    plaid_item = account.plaid_item
    client = get_plaid_client()

    if not client:
        raise HTTPException(status_code=503, detail="Plaid integration not configured")

    try:
        # Use transactions/sync for incremental updates
        cursor = plaid_item.transactions_cursor
        has_more = True
        added_count = 0
        modified_count = 0
        removed_count = 0

        while has_more:
            request = TransactionsSyncRequest(
                access_token=plaid_item.access_token,
                cursor=cursor,
            )

            response = client.transactions_sync(request)

            # Process added transactions
            for txn in response.added:
                if txn.account_id != account.plaid_account_id:
                    continue

                # Check if already exists
                existing = db.query(BankTransaction).filter(
                    BankTransaction.plaid_transaction_id == txn.transaction_id
                ).first()

                if existing:
                    continue

                bank_txn = BankTransaction(
                    bank_account_id=account.id,
                    transaction_date=txn.date,
                    posted_date=txn.datetime.date() if txn.datetime else txn.date,
                    amount=Decimal(str(-txn.amount)),  # Plaid uses negative for debits
                    description=txn.name,
                    merchant_name=txn.merchant_name,
                    category=txn.category[0] if txn.category else None,
                    plaid_transaction_id=txn.transaction_id,
                    plaid_category=txn.category,
                    is_pending=txn.pending,
                    match_status='unmatched',
                )

                # Try to auto-categorize
                target_account = apply_categorization_rules(db, bank_txn, org_id)
                if target_account:
                    bank_txn.categorized_account_id = target_account
                    bank_txn.match_status = 'categorized'

                db.add(bank_txn)
                added_count += 1

            # Process modified transactions
            for txn in response.modified:
                existing = db.query(BankTransaction).filter(
                    BankTransaction.plaid_transaction_id == txn.transaction_id
                ).first()

                if existing:
                    existing.amount = Decimal(str(-txn.amount))
                    existing.description = txn.name
                    existing.merchant_name = txn.merchant_name
                    existing.is_pending = txn.pending
                    modified_count += 1

            # Process removed transactions
            for txn in response.removed:
                existing = db.query(BankTransaction).filter(
                    BankTransaction.plaid_transaction_id == txn.transaction_id
                ).first()

                if existing and existing.match_status == 'unmatched':
                    db.delete(existing)
                    removed_count += 1

            cursor = response.next_cursor
            has_more = response.has_more

        # Update plaid item
        plaid_item.transactions_cursor = cursor
        plaid_item.last_successful_sync = datetime.now(timezone.utc)
        plaid_item.sync_status = 'synced'

        # Update account balance
        balance_request = AccountsBalanceGetRequest(access_token=plaid_item.access_token)
        balance_response = client.accounts_balance_get(balance_request)

        for plaid_acct in balance_response.accounts:
            if plaid_acct.account_id == account.plaid_account_id:
                account.current_balance = Decimal(str(plaid_acct.balances.current or 0))
                account.available_balance = Decimal(str(plaid_acct.balances.available or 0)) if plaid_acct.balances.available else None
                break

        db.commit()

        return {
            "success": True,
            "message": f"Sync complete: {added_count} added, {modified_count} modified, {removed_count} removed",
            "stats": {
                "added": added_count,
                "modified": modified_count,
                "removed": removed_count,
            },
            "current_balance": float(account.current_balance),
        }

    except plaid.ApiException as e:
        error_response = json.loads(e.body)
        plaid_item.sync_status = 'error'
        plaid_item.error_code = error_response.get('error_code')
        plaid_item.error_message = error_response.get('error_message')
        db.commit()

        raise HTTPException(
            status_code=400,
            detail=f"Plaid sync error: {error_response.get('error_code', 'SYNC_ERROR')}"
        )


@router.delete("/plaid/disconnect/{account_id}")
async def disconnect_plaid_account(
    request: Request,
    account_id: str,
    db: Session = Depends(get_db),
):
    """Disconnect a Plaid-connected bank account."""
    org_id = get_organization_id(request)

    account = db.query(BankAccount).filter(
        BankAccount.id == account_id,
        BankAccount.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    if not account.plaid_item_id:
        raise HTTPException(status_code=400, detail="Account is not connected to Plaid")

    plaid_item = account.plaid_item
    client = get_plaid_client()

    # Remove from Plaid
    if client and plaid_item.access_token:
        try:
            request = ItemRemoveRequest(access_token=plaid_item.access_token)
            client.item_remove(request)
        except Exception as e:
            logger.warning(f"Error removing Plaid item (continuing): {e}")

    # Check if other accounts use this plaid item
    other_accounts = db.query(BankAccount).filter(
        BankAccount.plaid_item_id == plaid_item.id,
        BankAccount.id != account_id
    ).count()

    # Disconnect the account
    account.plaid_item_id = None
    account.plaid_account_id = None

    # Delete plaid item if no other accounts use it
    if other_accounts == 0:
        db.delete(plaid_item)

    log_audit(
        db, org_id, 1, 'disconnect', 'bank_account', account.id,
        entity_number=account.account_name,
        summary=f"Disconnected Plaid from {account.account_name}"
    )

    db.commit()

    return {
        "success": True,
        "message": f"Disconnected {account.account_name} from Plaid",
    }


# =============================================================================
# Plaid Webhook
# =============================================================================

@router.post("/plaid/webhook")
async def handle_plaid_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Handle Plaid webhook notifications."""
    body = await request.body()

    # Verify webhook signature — fail-closed when key not configured
    if not PLAID_WEBHOOK_VERIFY_KEY:
        logger.error("PLAID_WEBHOOK_VERIFY_KEY not configured — rejecting webhook")
        raise HTTPException(status_code=401, detail="Webhook verification not configured")
    provided_sig = request.headers.get("Plaid-Verification", "")
    if not provided_sig:
        logger.warning("Missing Plaid-Verification header")
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    expected = hmac.new(
        PLAID_WEBHOOK_VERIFY_KEY.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(provided_sig, expected):
        logger.warning(f"Invalid Plaid webhook signature from {request.client.host}")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except Exception as e:
        logger.warning(f"Error parsing Plaid webhook JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    webhook_type = payload.get('webhook_type')
    webhook_code = payload.get('webhook_code')
    item_id = payload.get('item_id')

    if not item_id:
        return {"success": True, "message": "No item_id"}

    # Find the plaid item
    plaid_item = db.query(PlaidItem).filter(
        PlaidItem.item_id == item_id
    ).first()

    if not plaid_item:
        return {"success": True, "message": "Item not found"}

    # Handle different webhook types
    if webhook_type == 'TRANSACTIONS':
        if webhook_code in ('INITIAL_UPDATE', 'HISTORICAL_UPDATE', 'DEFAULT_UPDATE', 'SYNC_UPDATES_AVAILABLE'):
            # Mark for sync
            plaid_item.sync_status = 'pending_sync'
            db.commit()

            # Could trigger background sync here
            # background_tasks.add_task(sync_plaid_transactions_task, plaid_item.id)

    elif webhook_type == 'ITEM':
        if webhook_code == 'ERROR':
            plaid_item.sync_status = 'error'
            plaid_item.error_code = payload.get('error', {}).get('error_code')
            plaid_item.error_message = payload.get('error', {}).get('error_message')
            db.commit()

        elif webhook_code == 'PENDING_EXPIRATION':
            plaid_item.sync_status = 'pending_expiration'
            db.commit()

    return {"success": True, "message": f"Processed {webhook_type}/{webhook_code}"}


# =============================================================================
# Transaction Routes
# =============================================================================

@router.get("/transactions")
async def list_transactions(
    request: Request,
    account_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="unmatched, categorized, matched, excluded"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List bank transactions."""
    org_id = get_organization_id(request)

    query = db.query(BankTransaction).join(BankAccount).filter(
        BankAccount.organization_id == org_id
    )

    if account_id:
        query = query.filter(BankTransaction.bank_account_id == account_id)

    if status:
        query = query.filter(BankTransaction.match_status == status)

    if from_date:
        query = query.filter(BankTransaction.transaction_date >= from_date)

    if to_date:
        query = query.filter(BankTransaction.transaction_date <= to_date)

    if search:
        query = query.filter(
            or_(
                BankTransaction.description.ilike(f"%{search}%"),
                BankTransaction.merchant_name.ilike(f"%{search}%")
            )
        )

    total = query.count()
    transactions = query.order_by(
        BankTransaction.transaction_date.desc(),
        BankTransaction.id
    ).offset(skip).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "transactions": [t.to_dict() for t in transactions],
    }


@router.get("/transactions/{transaction_id}")
async def get_transaction(
    request: Request,
    transaction_id: str,
    db: Session = Depends(get_db),
):
    """Get a single transaction."""
    org_id = get_organization_id(request)

    transaction = db.query(BankTransaction).join(BankAccount).filter(
        BankTransaction.id == transaction_id,
        BankAccount.organization_id == org_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    result = transaction.to_dict()

    # Include potential matches
    if transaction.match_status == 'unmatched':
        # Find potential GL matches based on amount and date
        potential = db.query(JournalEntryLine, JournalEntry).join(
            JournalEntry
        ).filter(
            JournalEntry.organization_id == org_id,
            JournalEntry.status == 'posted',
            JournalEntry.entry_date >= transaction.transaction_date - timedelta(days=3),
            JournalEntry.entry_date <= transaction.transaction_date + timedelta(days=3),
            or_(
                JournalEntryLine.debit_amount == abs(transaction.amount),
                JournalEntryLine.credit_amount == abs(transaction.amount)
            )
        ).limit(5).all()

        result['potential_matches'] = [
            {
                'entry_id': str(entry.id),
                'entry_number': entry.entry_number,
                'entry_date': entry.entry_date.isoformat(),
                'description': line.description,
                'amount': float(line.debit_amount or line.credit_amount),
            }
            for line, entry in potential
        ]

    return {
        "success": True,
        "transaction": result,
    }


@router.post("/transactions/{transaction_id}/categorize")
async def categorize_transaction(
    request: Request,
    transaction_id: str,
    data: TransactionCategorizeRequest,
    db: Session = Depends(get_db),
):
    """Categorize a bank transaction to a GL account."""
    org_id = get_organization_id(request)

    transaction = db.query(BankTransaction).join(BankAccount).filter(
        BankTransaction.id == transaction_id,
        BankAccount.organization_id == org_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Validate target account
    target_account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == data.account_id,
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.is_active == True
    ).first()

    if not target_account:
        raise HTTPException(status_code=404, detail="Target account not found")

    transaction.categorized_account_id = data.account_id
    transaction.match_status = 'categorized'

    if data.description:
        transaction.description = data.description
    if data.notes:
        transaction.notes = data.notes

    db.commit()

    return {
        "success": True,
        "message": "Transaction categorized",
        "transaction": transaction.to_dict(),
    }


@router.post("/transactions/{transaction_id}/match")
async def match_transaction_to_entry(
    request: Request,
    transaction_id: str,
    journal_entry_id: str,
    db: Session = Depends(get_db),
):
    """Match a bank transaction to a journal entry."""
    org_id = get_organization_id(request)

    transaction = db.query(BankTransaction).join(BankAccount).filter(
        BankTransaction.id == transaction_id,
        BankAccount.organization_id == org_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Validate journal entry
    entry = db.query(JournalEntry).filter(
        JournalEntry.id == journal_entry_id,
        JournalEntry.organization_id == org_id
    ).first()

    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    transaction.matched_entry_id = journal_entry_id
    transaction.match_status = 'matched'
    transaction.matched_at = datetime.now(timezone.utc)
    transaction.matched_by = 1

    db.commit()

    return {
        "success": True,
        "message": "Transaction matched to journal entry",
        "transaction": transaction.to_dict(),
    }


@router.post("/transactions/{transaction_id}/create-entry")
async def create_entry_from_transaction(
    request: Request,
    transaction_id: str,
    account_id: str,  # The expense/revenue account
    description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Create a journal entry from a bank transaction."""
    org_id = get_organization_id(request)

    transaction = db.query(BankTransaction).join(BankAccount).filter(
        BankTransaction.id == transaction_id,
        BankAccount.organization_id == org_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    bank_account = transaction.bank_account

    # Validate target account
    target_account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == account_id,
        ChartOfAccounts.organization_id == org_id,
        ChartOfAccounts.is_active == True
    ).first()

    if not target_account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Find accounting period
    period = db.query(AccountingPeriod).filter(
        AccountingPeriod.organization_id == org_id,
        AccountingPeriod.start_date <= transaction.transaction_date,
        AccountingPeriod.end_date >= transaction.transaction_date,
        AccountingPeriod.status == 'open'
    ).first()

    if not period:
        raise HTTPException(status_code=400, detail="No open accounting period for transaction date")

    # Generate entry number
    entry_count = db.query(func.count(JournalEntry.id)).filter(
        JournalEntry.organization_id == org_id
    ).scalar() or 0

    entry_number = f"BNK-{entry_count + 1:06d}"

    # Create journal entry
    entry = JournalEntry(
        organization_id=org_id,
        period_id=period.id,
        entry_number=entry_number,
        entry_date=transaction.transaction_date,
        description=description or transaction.description,
        source='bank_transaction',
        source_id=transaction.id,
        status='posted',
        posted_at=datetime.now(timezone.utc),
        posted_by=1,
    )

    db.add(entry)
    db.flush()

    amount = abs(transaction.amount)

    if transaction.amount > 0:
        # Money in: Debit Bank, Credit Revenue/Other
        db.add(JournalEntryLine(
            entry_id=entry.id,
            line_number=1,
            account_id=bank_account.gl_account_id,
            description=f"Deposit - {transaction.description}",
            debit_amount=amount,
            credit_amount=Decimal("0"),
        ))
        db.add(JournalEntryLine(
            entry_id=entry.id,
            line_number=2,
            account_id=account_id,
            description=transaction.description,
            debit_amount=Decimal("0"),
            credit_amount=amount,
        ))
    else:
        # Money out: Debit Expense, Credit Bank
        db.add(JournalEntryLine(
            entry_id=entry.id,
            line_number=1,
            account_id=account_id,
            description=transaction.description,
            debit_amount=amount,
            credit_amount=Decimal("0"),
        ))
        db.add(JournalEntryLine(
            entry_id=entry.id,
            line_number=2,
            account_id=bank_account.gl_account_id,
            description=f"Payment - {transaction.description}",
            debit_amount=Decimal("0"),
            credit_amount=amount,
        ))

    # Update transaction
    transaction.matched_entry_id = entry.id
    transaction.match_status = 'matched'
    transaction.matched_at = datetime.now(timezone.utc)
    transaction.matched_by = 1
    transaction.categorized_account_id = account_id

    log_audit(
        db, org_id, 1, 'create', 'journal_entry', entry.id,
        entity_number=entry_number,
        summary=f"Created from bank transaction: {transaction.description}"
    )

    db.commit()

    return {
        "success": True,
        "message": "Journal entry created and matched",
        "entry": {
            "id": str(entry.id),
            "entry_number": entry.entry_number,
        },
        "transaction": transaction.to_dict(),
    }


@router.post("/transactions/{transaction_id}/exclude")
async def exclude_transaction(
    request: Request,
    transaction_id: str,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Exclude a transaction from reconciliation."""
    org_id = get_organization_id(request)

    transaction = db.query(BankTransaction).join(BankAccount).filter(
        BankTransaction.id == transaction_id,
        BankAccount.organization_id == org_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction.match_status = 'excluded'
    transaction.status = 'excluded'
    transaction.notes = reason

    db.commit()

    return {
        "success": True,
        "message": "Transaction excluded",
    }


# =============================================================================
# Categorization Rules Routes
# =============================================================================

@router.get("/rules")
async def list_categorization_rules(
    request: Request,
    db: Session = Depends(get_db),
):
    """List categorization rules."""
    org_id = get_organization_id(request)

    rules = db.query(BankCategorizationRule).filter(
        BankCategorizationRule.organization_id == org_id
    ).order_by(BankCategorizationRule.priority).all()

    return {
        "success": True,
        "rules": [r.to_dict() for r in rules],
    }


@router.post("/rules")
async def create_categorization_rule(
    request: Request,
    data: CategorizationRuleCreate,
    db: Session = Depends(get_db),
):
    """Create a categorization rule."""
    org_id = get_organization_id(request)

    # Validate target account
    target_account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.id == data.target_account_id,
        ChartOfAccounts.organization_id == org_id
    ).first()

    if not target_account:
        raise HTTPException(status_code=404, detail="Target account not found")

    rule = BankCategorizationRule(
        organization_id=org_id,
        **data.model_dump()
    )

    db.add(rule)
    db.commit()

    return {
        "success": True,
        "message": f"Rule '{rule.rule_name}' created",
        "rule": rule.to_dict(),
    }


@router.delete("/rules/{rule_id}")
async def delete_categorization_rule(
    request: Request,
    rule_id: str,
    db: Session = Depends(get_db),
):
    """Delete a categorization rule."""
    org_id = get_organization_id(request)

    rule = db.query(BankCategorizationRule).filter(
        BankCategorizationRule.id == rule_id,
        BankCategorizationRule.organization_id == org_id
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(rule)
    db.commit()

    return {
        "success": True,
        "message": "Rule deleted",
    }


@router.post("/rules/apply")
async def apply_rules_to_unmatched(
    request: Request,
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Apply categorization rules to all unmatched transactions."""
    org_id = get_organization_id(request)

    query = db.query(BankTransaction).join(BankAccount).filter(
        BankAccount.organization_id == org_id,
        BankTransaction.match_status == 'unmatched'
    )

    if account_id:
        query = query.filter(BankTransaction.bank_account_id == account_id)

    transactions = query.all()

    categorized_count = 0

    for txn in transactions:
        target_account = apply_categorization_rules(db, txn, org_id)
        if target_account:
            txn.categorized_account_id = target_account
            txn.match_status = 'categorized'
            categorized_count += 1

    db.commit()

    return {
        "success": True,
        "message": f"Applied rules: {categorized_count} transactions categorized",
        "categorized_count": categorized_count,
        "total_checked": len(transactions),
    }


# =============================================================================
# Bank Reconciliation Routes
# =============================================================================

@router.get("/reconciliations")
async def list_reconciliations(
    request: Request,
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List bank reconciliations."""
    org_id = get_organization_id(request)

    query = db.query(BankReconciliation).join(BankAccount).filter(
        BankAccount.organization_id == org_id
    )

    if account_id:
        query = query.filter(BankReconciliation.bank_account_id == account_id)

    reconciliations = query.order_by(BankReconciliation.statement_date.desc()).all()

    return {
        "success": True,
        "reconciliations": [r.to_dict() for r in reconciliations],
    }


@router.post("/reconciliations")
async def start_reconciliation(
    request: Request,
    data: ReconciliationCreate,
    db: Session = Depends(get_db),
):
    """Start a new bank reconciliation."""
    org_id = get_organization_id(request)

    # Validate account
    account = db.query(BankAccount).filter(
        BankAccount.id == data.bank_account_id,
        BankAccount.organization_id == org_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    # Check for existing unfinished reconciliation
    existing = db.query(BankReconciliation).filter(
        BankReconciliation.bank_account_id == data.bank_account_id,
        BankReconciliation.status == 'in_progress'
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="An unfinished reconciliation exists. Complete or delete it first."
        )

    # Get last reconciled balance
    last_recon = db.query(BankReconciliation).filter(
        BankReconciliation.bank_account_id == data.bank_account_id,
        BankReconciliation.status == 'completed'
    ).order_by(BankReconciliation.statement_date.desc()).first()

    beginning_balance = last_recon.statement_ending_balance if last_recon else account.opening_balance
    start_date = data.statement_start_date or (last_recon.statement_date + timedelta(days=1) if last_recon else account.opening_balance_date)

    recon = BankReconciliation(
        bank_account_id=data.bank_account_id,
        statement_date=data.statement_date,
        statement_start_date=start_date,
        statement_ending_balance=data.statement_ending_balance,
        beginning_balance=beginning_balance,
        status='in_progress',
        started_at=datetime.now(timezone.utc),
        started_by=1,
    )

    db.add(recon)
    db.flush()

    # Get uncleared transactions for this period
    transactions = db.query(BankTransaction).filter(
        BankTransaction.bank_account_id == data.bank_account_id,
        BankTransaction.transaction_date <= data.statement_date,
        BankTransaction.is_reconciled == False,
        BankTransaction.status != 'excluded'
    ).all()

    db.commit()

    return {
        "success": True,
        "message": "Reconciliation started",
        "reconciliation": recon.to_dict(),
        "uncleared_transactions": [t.to_dict() for t in transactions],
        "beginning_balance": float(beginning_balance),
    }


@router.get("/reconciliations/{recon_id}")
async def get_reconciliation(
    request: Request,
    recon_id: str,
    db: Session = Depends(get_db),
):
    """Get reconciliation details with transactions."""
    org_id = get_organization_id(request)

    recon = db.query(BankReconciliation).join(BankAccount).filter(
        BankReconciliation.id == recon_id,
        BankAccount.organization_id == org_id
    ).first()

    if not recon:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    # Get transactions for this period
    transactions = db.query(BankTransaction).filter(
        BankTransaction.bank_account_id == recon.bank_account_id,
        BankTransaction.transaction_date >= recon.statement_start_date,
        BankTransaction.transaction_date <= recon.statement_date,
        BankTransaction.status != 'excluded'
    ).order_by(BankTransaction.transaction_date).all()

    # Calculate current position
    cleared_total = sum(
        t.amount for t in transactions
        if t.is_reconciled or t.id in (recon.cleared_transaction_ids or [])
    )

    calculated_balance = recon.beginning_balance + cleared_total
    difference = recon.statement_ending_balance - calculated_balance

    result = recon.to_dict()
    result['transactions'] = [t.to_dict() for t in transactions]
    result['cleared_total'] = float(cleared_total)
    result['calculated_balance'] = float(calculated_balance)
    result['difference'] = float(difference)
    result['is_balanced'] = abs(difference) < Decimal("0.01")

    return {
        "success": True,
        "reconciliation": result,
    }


@router.put("/reconciliations/{recon_id}")
async def update_reconciliation(
    request: Request,
    recon_id: str,
    data: ReconciliationUpdate,
    db: Session = Depends(get_db),
):
    """Update reconciliation (mark transactions as cleared)."""
    org_id = get_organization_id(request)

    recon = db.query(BankReconciliation).join(BankAccount).filter(
        BankReconciliation.id == recon_id,
        BankAccount.organization_id == org_id
    ).first()

    if not recon:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if recon.status == 'completed':
        raise HTTPException(status_code=400, detail="Reconciliation is already completed")

    # Update cleared transactions
    recon.cleared_transaction_ids = data.cleared_transactions

    # Calculate new totals
    cleared_total = Decimal("0")
    for txn_id in data.cleared_transactions:
        txn = db.query(BankTransaction).filter(BankTransaction.id == txn_id).first()
        if txn:
            cleared_total += txn.amount

    recon.cleared_balance = recon.beginning_balance + cleared_total

    db.commit()

    difference = recon.statement_ending_balance - recon.cleared_balance

    return {
        "success": True,
        "message": "Reconciliation updated",
        "cleared_balance": float(recon.cleared_balance),
        "statement_balance": float(recon.statement_ending_balance),
        "difference": float(difference),
        "is_balanced": abs(difference) < Decimal("0.01"),
    }


@router.post("/reconciliations/{recon_id}/complete")
async def complete_reconciliation(
    request: Request,
    recon_id: str,
    db: Session = Depends(get_db),
):
    """Complete and finalize a reconciliation."""
    org_id = get_organization_id(request)

    recon = db.query(BankReconciliation).join(BankAccount).filter(
        BankReconciliation.id == recon_id,
        BankAccount.organization_id == org_id
    ).first()

    if not recon:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if recon.status == 'completed':
        raise HTTPException(status_code=400, detail="Reconciliation is already completed")

    # Calculate final difference
    cleared_total = Decimal("0")
    for txn_id in (recon.cleared_transaction_ids or []):
        txn = db.query(BankTransaction).filter(BankTransaction.id == txn_id).first()
        if txn:
            cleared_total += txn.amount

    calculated_balance = recon.beginning_balance + cleared_total
    difference = recon.statement_ending_balance - calculated_balance

    if abs(difference) >= Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail=f"Reconciliation does not balance. Difference: ${float(difference):.2f}"
        )

    # Mark transactions as reconciled
    for txn_id in (recon.cleared_transaction_ids or []):
        db.query(BankTransaction).filter(
            BankTransaction.id == txn_id
        ).update({
            'is_reconciled': True,
            'reconciled_at': datetime.now(timezone.utc),
        })

    recon.status = 'completed'
    recon.completed_at = datetime.now(timezone.utc)
    recon.completed_by = 1
    recon.cleared_balance = calculated_balance

    # Update bank account
    recon.bank_account.last_reconciled_date = recon.statement_date
    recon.bank_account.last_reconciled_balance = recon.statement_ending_balance

    log_audit(
        db, org_id, 1, 'complete', 'bank_reconciliation', recon.id,
        summary=f"Completed reconciliation for {recon.bank_account.account_name} as of {recon.statement_date}"
    )

    db.commit()

    return {
        "success": True,
        "message": "Reconciliation completed",
        "reconciliation": recon.to_dict(),
    }


@router.delete("/reconciliations/{recon_id}")
async def delete_reconciliation(
    request: Request,
    recon_id: str,
    db: Session = Depends(get_db),
):
    """Delete an in-progress reconciliation."""
    org_id = get_organization_id(request)

    recon = db.query(BankReconciliation).join(BankAccount).filter(
        BankReconciliation.id == recon_id,
        BankAccount.organization_id == org_id
    ).first()

    if not recon:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if recon.status == 'completed':
        raise HTTPException(status_code=400, detail="Cannot delete completed reconciliation")

    db.delete(recon)
    db.commit()

    return {
        "success": True,
        "message": "Reconciliation deleted",
    }


# =============================================================================
# Summary / Dashboard
# =============================================================================

@router.get("/summary")
async def get_banking_summary(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get banking summary for dashboard."""
    org_id = get_organization_id(request)

    # Get account balances
    accounts = db.query(BankAccount).filter(
        BankAccount.organization_id == org_id,
        BankAccount.is_active == True
    ).all()

    total_cash = sum(a.current_balance or Decimal("0") for a in accounts)

    # Unmatched transactions
    unmatched = db.query(func.count(BankTransaction.id)).join(BankAccount).filter(
        BankAccount.organization_id == org_id,
        BankTransaction.match_status == 'unmatched'
    ).scalar() or 0

    # Pending reconciliation
    pending_recon = db.query(func.count(BankReconciliation.id)).join(BankAccount).filter(
        BankAccount.organization_id == org_id,
        BankReconciliation.status == 'in_progress'
    ).scalar() or 0

    # Recent transactions
    recent = db.query(BankTransaction).join(BankAccount).filter(
        BankAccount.organization_id == org_id
    ).order_by(BankTransaction.transaction_date.desc()).limit(5).all()

    return {
        "success": True,
        "summary": {
            "total_cash_balance": float(total_cash),
            "account_count": len(accounts),
            "unmatched_transactions": unmatched,
            "pending_reconciliations": pending_recon,
            "accounts": [
                {
                    "id": str(a.id),
                    "name": a.account_name,
                    "balance": float(a.current_balance or 0),
                    "plaid_connected": a.plaid_item_id is not None,
                }
                for a in accounts
            ],
            "recent_transactions": [t.to_dict() for t in recent],
        },
    }
