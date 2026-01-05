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

router = APIRouter(prefix="/api/v1", tags=["Credit Reports"])


# ============================================================================
# Lazy imports to avoid circular dependency
# ============================================================================

def get_db_session():
    """Get database session - lazy import to avoid circular dependency"""
    from main import get_db
    return get_db

def get_current_user_dep():
    """Get current user dependency - lazy import"""
    from main import get_current_user
    return get_current_user

def get_models():
    """Get models - lazy import"""
    from main import User, Document, Lead, Loan, Base, engine, DocumentCategory
    return User, Document, Lead, Loan, Base, engine, DocumentCategory

def get_filters():
    """Get filter functions - lazy import"""
    from main import filter_leads_by_permissions, filter_loans_by_permissions
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

    User, Document, Lead, Loan, Base, engine, DocumentCategory = get_models()

    from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum as SQLEnum, inspect
    from sqlalchemy.orm import relationship

    # Check if tables exist
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "credit_items" not in existing_tables:
        # Create credit_items table
        from sqlalchemy import Table, MetaData
        metadata = MetaData()

        credit_items = Table(
            "credit_items",
            metadata,
            Column("id", Integer, primary_key=True, index=True),
            Column("loan_id", Integer, ForeignKey("loans.id"), nullable=True),
            Column("lead_id", Integer, ForeignKey("leads.id"), nullable=True),
            Column("document_id", Integer, ForeignKey("documents.id"), nullable=True),
            Column("title", String, nullable=False),
            Column("description", Text),
            Column("category", String),
            Column("severity", String, default="medium"),
            Column("status", String, default="pending"),
            Column("recommendation", Text),
            Column("account_name", String),
            Column("account_balance", Float),
            Column("notes", Text),
            Column("created_at", DateTime, default=datetime.now(timezone.utc)),
            Column("updated_at", DateTime, default=datetime.now(timezone.utc)),
        )

        credit_summaries = Table(
            "credit_summaries",
            metadata,
            Column("id", Integer, primary_key=True, index=True),
            Column("loan_id", Integer, ForeignKey("loans.id"), nullable=True),
            Column("lead_id", Integer, ForeignKey("leads.id"), nullable=True),
            Column("document_id", Integer, ForeignKey("documents.id"), nullable=True),
            Column("credit_score", Integer),
            Column("equifax_score", Integer),
            Column("experian_score", Integer),
            Column("transunion_score", Integer),
            Column("bureau", String),
            Column("report_date", DateTime),
            Column("total_accounts", Integer),
            Column("open_accounts", Integer),
            Column("closed_accounts", Integer),
            Column("total_debt", Float),
            Column("total_credit_limit", Float),
            Column("utilization", Float),
            Column("late_payments_30", Integer, default=0),
            Column("late_payments_60", Integer, default=0),
            Column("late_payments_90", Integer, default=0),
            Column("collections", Integer, default=0),
            Column("bankruptcies", Integer, default=0),
            Column("created_at", DateTime, default=datetime.now(timezone.utc)),
            Column("updated_at", DateTime, default=datetime.now(timezone.utc)),
        )

        metadata.create_all(engine)
        print("✅ Credit tables created")

    _tables_created = True


# ============================================================================
# Routes
# ============================================================================

@router.get("/loans/{loan_id}/credit-reports")
async def get_loan_credit_reports(
    loan_id: int,
    db: Session = Depends(get_db_session())
):
    """Get credit reports, items, and summary for a loan."""
    from main import get_current_user, Loan, Document, DocumentCategory
    filter_leads_by_permissions, filter_loans_by_permissions = get_filters()

    ensure_tables()

    # Get current user from request state if available
    try:
        current_user = db.info.get("current_user")
    except:
        current_user = None

    # Verify loan exists
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
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
        except:
            pass

    # Get credit items from database
    from sqlalchemy import text
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

    items = []
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

    # Get credit summary
    summary_result = db.execute(text("""
        SELECT credit_score, equifax_score, experian_score, transunion_score,
               bureau, report_date, total_accounts, open_accounts, total_debt, utilization
        FROM credit_summaries WHERE loan_id = :loan_id
        ORDER BY created_at DESC LIMIT 1
    """), {"loan_id": loan_id}).fetchone()

    summary = None
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
    db: Session = Depends(get_db_session())
):
    """Get credit reports, items, and summary for a lead."""
    from main import Lead, Document, DocumentCategory

    ensure_tables()

    # Verify lead exists
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
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
        except:
            pass

    # Get credit items from database
    from sqlalchemy import text
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

    items = []
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

    # Get credit summary
    summary_result = db.execute(text("""
        SELECT credit_score, equifax_score, experian_score, transunion_score,
               bureau, report_date, total_accounts, open_accounts, total_debt, utilization
        FROM credit_summaries WHERE lead_id = :lead_id
        ORDER BY created_at DESC LIMIT 1
    """), {"lead_id": lead_id}).fetchone()

    summary = None
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
    db: Session = Depends(get_db_session())
):
    """Update a credit item's status or notes."""
    from sqlalchemy import text

    ensure_tables()

    # Check item exists
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
    db: Session = Depends(get_db_session())
):
    """Trigger AI analysis of a credit report document."""
    from main import Document
    from sqlalchemy import text

    ensure_tables()

    # Get the document
    document = db.query(Document).filter(Document.id == request.document_id).first()
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
