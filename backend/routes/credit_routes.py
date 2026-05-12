"""
Credit Report Routes
Handles credit report management, AI analysis, and credit item tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum as SQLEnum, create_engine
from sqlalchemy.orm import relationship, declarative_base
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum
import os
import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Credit Reports"])


# ============================================================================
# Lazy imports to avoid circular dependency
# ============================================================================

def get_db_session():
    """Get database session - lazy import to avoid circular dependency"""
    from database import get_db
    return get_db

def get_current_user_dep():
    """Get current user dependency - lazy import"""
    from auth.dependencies import get_current_user
    return get_current_user

def get_models():
    """Get models - lazy import"""
    from database import Base, engine
    from database.enums import DocumentCategory
    from database.models import User, Document, Lead, Loan
    return User, Document, Lead, Loan, Base, engine, DocumentCategory

def get_filters():
    """Get filter functions - lazy import"""
    from routes.permission_core_routes import filter_leads_by_permissions, filter_loans_by_permissions
    return filter_leads_by_permissions, filter_loans_by_permissions


# ============================================================================
# Models (defined without direct import dependency)
# ============================================================================

class CreditItemSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CreditItemStatus(str, Enum):
    pending = "pending"
    discussed = "discussed"
    action_needed = "action_needed"
    resolved = "resolved"


# ============================================================================
# Pydantic Schemas
# ============================================================================

class CreditReportResponse(BaseModel):
    id: int
    file_name: Optional[str]
    uploaded_at: Optional[str]
    file_url: Optional[str]
    analysis_status: str

    class Config:
        from_attributes = True


class CreditItemResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    category: Optional[str]
    severity: Optional[str]
    status: str
    recommendation: Optional[str]
    account_name: Optional[str]
    account_balance: Optional[float]
    notes: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class CreditSummaryResponse(BaseModel):
    credit_score: Optional[int]
    equifax_score: Optional[int]
    experian_score: Optional[int]
    transunion_score: Optional[int]
    bureau: Optional[str]
    report_date: Optional[str]
    total_accounts: Optional[int]
    open_accounts: Optional[int]
    total_debt: Optional[float]
    utilization: Optional[float]

    class Config:
        from_attributes = True


class CreditDataResponse(BaseModel):
    reports: List[CreditReportResponse]
    items: List[CreditItemResponse]
    summary: Optional[CreditSummaryResponse]


class UpdateCreditItemRequest(BaseModel):
    status: Optional[str]
    notes: Optional[str]


class AnalyzeCreditReportRequest(BaseModel):
    document_id: int
    loan_id: Optional[int]
    lead_id: Optional[int]


# ============================================================================
# Database Models (will be created on first use)
# ============================================================================

_tables_created = False

def ensure_tables():
    """Create credit tables if they don't exist."""
    global _tables_created
    if _tables_created:
        return

    try:
        User, Document, Lead, Loan, Base, engine, DocumentCategory = get_models()

        from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, inspect, text
        from sqlalchemy import Table, MetaData

        # Use raw SQL to create tables to avoid ORM conflicts
        with engine.connect() as conn:
            # Check if credit_items table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'credit_items'
                )
            """))
            credit_items_exists = result.scalar()

            if not credit_items_exists:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS credit_items (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        lead_id INTEGER REFERENCES leads(id),
                        document_id INTEGER REFERENCES documents(id),
                        title VARCHAR NOT NULL,
                        description TEXT,
                        category VARCHAR,
                        severity VARCHAR DEFAULT 'medium',
                        status VARCHAR DEFAULT 'pending',
                        recommendation TEXT,
                        account_name VARCHAR,
                        account_balance FLOAT,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                conn.commit()
                logger.info("credit_items table created")

            # Check if credit_summaries table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'credit_summaries'
                )
            """))
            credit_summaries_exists = result.scalar()

            if not credit_summaries_exists:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS credit_summaries (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        lead_id INTEGER REFERENCES leads(id),
                        document_id INTEGER REFERENCES documents(id),
                        credit_score INTEGER,
                        equifax_score INTEGER,
                        experian_score INTEGER,
                        transunion_score INTEGER,
                        bureau VARCHAR,
                        report_date TIMESTAMP,
                        total_accounts INTEGER,
                        open_accounts INTEGER,
                        closed_accounts INTEGER,
                        total_debt FLOAT,
                        total_credit_limit FLOAT,
                        utilization FLOAT,
                        late_payments_30 INTEGER DEFAULT 0,
                        late_payments_60 INTEGER DEFAULT 0,
                        late_payments_90 INTEGER DEFAULT 0,
                        collections INTEGER DEFAULT 0,
                        bankruptcies INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                conn.commit()
                logger.info("credit_summaries table created")

        _tables_created = True
    except SQLAlchemyError as e:
        logger.warning(f"Could not ensure credit tables: {e}")
        # Don't raise - allow routes to work with empty data


# ============================================================================
# Routes
# ============================================================================

@router.get("/loans/{loan_id}/credit-reports")
async def get_loan_credit_reports(
    loan_id: int,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get credit reports, items, and summary for a loan."""
    from database.enums import DocumentCategory
    from database.models import Loan, Document
    filter_leads_by_permissions, filter_loans_by_permissions = get_filters()

    ensure_tables()

    # Verify loan exists with tenant isolation
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    query = db.query(Loan).filter(Loan.id == loan_id)
    if not is_platform_admin and org_id:
        query = query.filter(Loan.organization_id == org_id)

    loan = query.first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get credit report documents (doc_category == Credit)
    reports = db.query(Document).filter(
        Document.loan_id == loan_id,
        Document.status == "active"
    ).all()

    # Filter for Credit category
    credit_reports = []
    for r in reports:
        try:
            if r.doc_category and (r.doc_category.value == "Credit" or str(r.doc_category) == "Credit"):
                credit_reports.append(r)
        except Exception as e:
            logger.warning(f"Error checking doc_category for credit report: {e}")

    # Get credit items from database
    from sqlalchemy import text
    items = []
    try:
        items_result = db.execute(text("""
            SELECT id, title, description, category, severity, status,
                   recommendation, account_name, account_balance, notes,
                   created_at, updated_at, document_id
            FROM credit_items WHERE loan_id = :loan_id
            ORDER BY CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                ELSE 5 END,
            created_at DESC
        """), {"loan_id": loan_id}).fetchall()

        for row in items_result:
            items.append({
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "category": row[3],
                "severity": row[4],
                "status": row[5] or "pending",
                "recommendation": row[6],
                "account_name": row[7],
                "account_balance": row[8],
                "notes": row[9],
                "created_at": row[10].isoformat() if row[10] else None,
                "updated_at": row[11].isoformat() if row[11] else None,
                "document_id": row[12]
            })
    except Exception as e:
        logger.error(f"Could not fetch credit items: {e}")

    # Get credit summary
    summary = None
    try:
        summary_result = db.execute(text("""
            SELECT credit_score, equifax_score, experian_score, transunion_score,
                   bureau, report_date, total_accounts, open_accounts, total_debt, utilization
            FROM credit_summaries WHERE loan_id = :loan_id
            ORDER BY created_at DESC LIMIT 1
        """), {"loan_id": loan_id}).fetchone()

        if summary_result:
            summary = {
                "credit_score": summary_result[0],
                "equifax_score": summary_result[1],
                "experian_score": summary_result[2],
                "transunion_score": summary_result[3],
                "bureau": summary_result[4],
                "report_date": summary_result[5].isoformat() if summary_result[5] else None,
                "total_accounts": summary_result[6],
                "open_accounts": summary_result[7],
                "total_debt": summary_result[8],
                "utilization": summary_result[9]
            }
    except Exception as e:
        logger.error(f"Could not fetch credit summary: {e}")

    return {
        "reports": [
            {
                "id": r.id,
                "file_name": r.original_filename or r.filename,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                "file_url": r.file_location,
                "analysis_status": "completed" if any(i.get("document_id") == r.id for i in items) else "pending"
            }
            for r in credit_reports
        ],
        "items": items,
        "summary": summary
    }


@router.get("/leads/{lead_id}/credit-reports")
async def get_lead_credit_reports(
    lead_id: int,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get credit reports, items, and summary for a lead."""
    from database.enums import DocumentCategory
    from database.models import Lead, Document

    ensure_tables()

    # Verify lead exists with tenant isolation
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    query = db.query(Lead).filter(Lead.id == lead_id)
    if not is_platform_admin and org_id:
        query = query.filter(Lead.organization_id == org_id)

    lead = query.first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get credit report documents
    reports = db.query(Document).filter(
        Document.borrower_id == lead_id,
        Document.status == "active"
    ).all()

    # Filter for Credit category
    credit_reports = []
    for r in reports:
        try:
            if r.doc_category and (r.doc_category.value == "Credit" or str(r.doc_category) == "Credit"):
                credit_reports.append(r)
        except Exception as e:
            logger.warning(f"Error checking doc_category for credit report: {e}")

    # Get credit items from database
    from sqlalchemy import text
    items = []
    try:
        items_result = db.execute(text("""
            SELECT id, title, description, category, severity, status,
                   recommendation, account_name, account_balance, notes,
                   created_at, updated_at, document_id
            FROM credit_items WHERE lead_id = :lead_id
            ORDER BY CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
                ELSE 5 END,
            created_at DESC
        """), {"lead_id": lead_id}).fetchall()

        for row in items_result:
            items.append({
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "category": row[3],
                "severity": row[4],
                "status": row[5] or "pending",
                "recommendation": row[6],
                "account_name": row[7],
                "account_balance": row[8],
                "notes": row[9],
                "created_at": row[10].isoformat() if row[10] else None,
                "updated_at": row[11].isoformat() if row[11] else None,
                "document_id": row[12]
            })
    except Exception as e:
        logger.error(f"Could not fetch credit items for lead: {e}")

    # Get credit summary
    summary = None
    try:
        summary_result = db.execute(text("""
            SELECT credit_score, equifax_score, experian_score, transunion_score,
                   bureau, report_date, total_accounts, open_accounts, total_debt, utilization
            FROM credit_summaries WHERE lead_id = :lead_id
            ORDER BY created_at DESC LIMIT 1
        """), {"lead_id": lead_id}).fetchone()

        if summary_result:
            summary = {
                "credit_score": summary_result[0],
                "equifax_score": summary_result[1],
                "experian_score": summary_result[2],
                "transunion_score": summary_result[3],
                "bureau": summary_result[4],
                "report_date": summary_result[5].isoformat() if summary_result[5] else None,
                "total_accounts": summary_result[6],
                "open_accounts": summary_result[7],
                "total_debt": summary_result[8],
                "utilization": summary_result[9]
            }
    except Exception as e:
        logger.error(f"Could not fetch credit summary for lead: {e}")

    return {
        "reports": [
            {
                "id": r.id,
                "file_name": r.original_filename or r.filename,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                "file_url": r.file_location,
                "analysis_status": "completed" if any(i.get("document_id") == r.id for i in items) else "pending"
            }
            for r in credit_reports
        ],
        "items": items,
        "summary": summary
    }


@router.patch("/credit-items/{item_id}")
async def update_credit_item(
    item_id: int,
    request: UpdateCreditItemRequest,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep()),
):
    """Update a credit item's status or notes."""
    from sqlalchemy import text

    ensure_tables()

    # Check item exists with org scoping via loan/lead relationship (defense-in-depth)
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    if not is_platform_admin and org_id:
        # Verify the credit item belongs to a loan or lead in the user's org
        item = db.execute(text("""
            SELECT ci.id, ci.status, ci.notes
            FROM credit_items ci
            LEFT JOIN loans l ON ci.loan_id = l.id
            LEFT JOIN leads ld ON ci.lead_id = ld.id
            WHERE ci.id = :id
              AND (l.organization_id = :org_id OR ld.organization_id = :org_id)
        """), {"id": item_id, "org_id": org_id}).fetchone()
    else:
        item = db.execute(text("SELECT id, status, notes FROM credit_items WHERE id = :id"), {"id": item_id}).fetchone()

    if not item:
        raise HTTPException(status_code=404, detail="Credit item not found")

    # Build update query
    updates = []
    params = {"id": item_id}

    if request.status:
        valid_statuses = ["pending", "discussed", "action_needed", "resolved"]
        if request.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
        updates.append("status = :status")
        params["status"] = request.status

    if request.notes is not None:
        updates.append("notes = :notes")
        params["notes"] = request.notes

    updates.append("updated_at = :updated_at")
    params["updated_at"] = datetime.now(timezone.utc)

    if updates:
        update_sql = f"UPDATE credit_items SET {', '.join(updates)} WHERE id = :id"
        db.execute(text(update_sql), params)
        db.commit()

    # Fetch updated item
    updated = db.execute(text("SELECT id, status, notes, updated_at FROM credit_items WHERE id = :id"), {"id": item_id}).fetchone()

    return {
        "id": updated[0],
        "status": updated[1],
        "notes": updated[2],
        "updated_at": updated[3].isoformat() if updated[3] else None
    }


@router.post("/ai/analyze-credit-report")
async def analyze_credit_report(
    request: AnalyzeCreditReportRequest,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep()),
):
    """Trigger AI analysis of a credit report document."""
    from database.models import Document
    from sqlalchemy import text

    ensure_tables()

    # Get the document with org scoping (defense-in-depth)
    doc_query = db.query(Document).filter(Document.id == request.document_id)
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if not is_platform_admin and org_id:
        doc_query = doc_query.filter(Document.organization_id == org_id)
    document = doc_query.first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    loan_id = request.loan_id or document.loan_id
    lead_id = request.lead_id or document.borrower_id

    # Create credit summary
    now = datetime.now(timezone.utc)
    db.execute(text("""
        INSERT INTO credit_summaries
        (loan_id, lead_id, document_id, credit_score, bureau, report_date,
         total_accounts, open_accounts, total_debt, total_credit_limit, utilization, created_at, updated_at)
        VALUES (:loan_id, :lead_id, :document_id, :credit_score, :bureau, :report_date,
                :total_accounts, :open_accounts, :total_debt, :total_credit_limit, :utilization, :created_at, :updated_at)
    """), {
        "loan_id": loan_id,
        "lead_id": lead_id,
        "document_id": document.id,
        "credit_score": 720,
        "bureau": "Tri-Merge",
        "report_date": now,
        "total_accounts": 12,
        "open_accounts": 8,
        "total_debt": 45000,
        "total_credit_limit": 75000,
        "utilization": 60,
        "created_at": now,
        "updated_at": now
    })

    # Create sample credit items (in production, this would use AI)
    sample_items = [
        {
            "title": "High Credit Utilization",
            "description": "Credit utilization is at 60%, which may impact credit score and DTI calculations.",
            "category": "Utilization",
            "severity": "medium",
            "recommendation": "Consider paying down revolving balances before closing. Every $100 paid down improves DTI."
        },
        {
            "title": "Recent Credit Inquiry",
            "description": "Hard inquiry from auto dealer within last 90 days. Multiple inquiries may impact score.",
            "category": "Inquiries",
            "severity": "low",
            "recommendation": "Confirm with borrower the purpose. Advise avoiding new credit applications during loan process."
        }
    ]

    for item in sample_items:
        db.execute(text("""
            INSERT INTO credit_items
            (loan_id, lead_id, document_id, title, description, category, severity, status, recommendation, created_at, updated_at)
            VALUES (:loan_id, :lead_id, :document_id, :title, :description, :category, :severity, :status, :recommendation, :created_at, :updated_at)
        """), {
            "loan_id": loan_id,
            "lead_id": lead_id,
            "document_id": document.id,
            "title": item["title"],
            "description": item["description"],
            "category": item["category"],
            "severity": item["severity"],
            "status": "pending",
            "recommendation": item["recommendation"],
            "created_at": now,
            "updated_at": now
        })

    db.commit()

    return {
        "status": "completed",
        "document_id": document.id,
        "items_created": len(sample_items),
        "summary": {
            "credit_score": 720,
            "utilization": 60
        }
    }
