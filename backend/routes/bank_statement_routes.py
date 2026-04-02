"""
Bank Statement API Routes

Endpoints for bank statement extraction, analysis, and worksheet generation.
Supports Non-QM bank statement income calculation programs.
"""

import logging
import os
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.bank_statement_models import (
    BankStatementWorksheet, BankStatementAccount, BankStatementMonth,
    StatementType, CalculationMethod, ExtractionStatus
)
from services.bank_statement_extraction_service import get_bank_statement_extraction_service
from services.bank_statement_worksheet_generator import get_worksheet_generator
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/bank-statements", tags=["Bank Statements"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class WorksheetCreateRequest(BaseModel):
    """Request to create a new bank statement worksheet."""
    loan_id: int
    borrower_id: int
    borrower_name: str
    business_name: Optional[str] = None
    ownership_percentage: float = 100.0
    months_of_statements: int = 12
    calculation_method: str = "UNIFORM_EXPENSE_RATIO"
    ltv_percentage: Optional[float] = 80.0
    cpa_expense_ratio: Optional[float] = None
    has_separate_business_account: bool = False


class MonthlyDataInput(BaseModel):
    """Input for a single month's bank statement data."""
    month_number: int
    statement_month: str
    statement_end_date: Optional[str] = None
    total_deposits: float = 0
    ineligible_deposits: float = 0
    eligible_deposits: float = 0
    beginning_balance: float = 0
    ending_balance: float = 0
    nsf_count: int = 0


class AccountDataInput(BaseModel):
    """Input for a bank account's data."""
    statement_type: str  # PERSONAL or BUSINESS
    bank_name: str
    account_last_four: str
    monthly_data: List[MonthlyDataInput]


class WorksheetUpdateRequest(BaseModel):
    """Request to update worksheet with extracted/manual data."""
    personal_account: Optional[AccountDataInput] = None
    business_account: Optional[AccountDataInput] = None


# =============================================================================
# WORKSHEET MANAGEMENT
# =============================================================================

@router.post("/worksheets")
async def create_worksheet(
    request: WorksheetCreateRequest,
    db: Session = Depends(get_db),
):
    """Create a new bank statement worksheet for a loan."""
    # Check if worksheet already exists
    existing = db.query(BankStatementWorksheet).filter(
        BankStatementWorksheet.loan_id == request.loan_id,
        BankStatementWorksheet.borrower_id == request.borrower_id
    ).first()

    if existing:
        return {
            "success": True,
            "message": "Worksheet already exists",
            "worksheet_id": existing.id,
            "status": existing.status.value
        }

    # Create new worksheet
    try:
        calc_method = CalculationMethod(request.calculation_method)
    except ValueError:
        calc_method = CalculationMethod.UNIFORM_EXPENSE_RATIO

    worksheet = BankStatementWorksheet(
        loan_id=request.loan_id,
        borrower_id=request.borrower_id,
        borrower_name=request.borrower_name,
        business_name=request.business_name,
        ownership_percentage=request.ownership_percentage,
        months_of_statements=request.months_of_statements,
        calculation_method=calc_method,
        ltv_percentage=request.ltv_percentage,
        cpa_expense_ratio=request.cpa_expense_ratio,
        has_separate_business_account=request.has_separate_business_account,
        status=ExtractionStatus.PENDING
    )

    db.add(worksheet)
    db.commit()
    db.refresh(worksheet)

    return {
        "success": True,
        "message": "Worksheet created",
        "worksheet_id": worksheet.id
    }


@router.get("/worksheets/{worksheet_id}")
async def get_worksheet(
    worksheet_id: int,
    db: Session = Depends(get_db),
):
    """Get worksheet details with all account and monthly data."""
    worksheet = db.query(BankStatementWorksheet).filter(
        BankStatementWorksheet.id == worksheet_id
    ).first()

    if not worksheet:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    # Get accounts
    accounts = db.query(BankStatementAccount).filter(
        BankStatementAccount.worksheet_id == worksheet_id
    ).all()

    accounts_data = []
    for account in accounts:
        months = db.query(BankStatementMonth).filter(
            BankStatementMonth.account_id == account.id
        ).order_by(BankStatementMonth.month_number).all()

        accounts_data.append({
            "id": account.id,
            "statement_type": account.statement_type.value,
            "bank_name": account.bank_name,
            "account_last_four": account.account_last_four,
            "extraction_status": account.extraction_status.value,
            "monthly_data": [
                {
                    "month_number": m.month_number,
                    "statement_month": m.statement_month,
                    "statement_end_date": str(m.statement_end_date) if m.statement_end_date else None,
                    "total_deposits": float(m.total_deposits or 0),
                    "ineligible_deposits": float(m.ineligible_deposits or 0),
                    "eligible_deposits": float(m.eligible_deposits or 0),
                    "beginning_balance": float(m.beginning_balance or 0),
                    "ending_balance": float(m.ending_balance or 0),
                    "nsf_count": m.nsf_count or 0,
                    "extraction_confidence": m.extraction_confidence,
                    "manually_verified": m.manually_verified
                }
                for m in months
            ]
        })

    return {
        "id": worksheet.id,
        "loan_id": worksheet.loan_id,
        "borrower_id": worksheet.borrower_id,
        "borrower_name": worksheet.borrower_name,
        "business_name": worksheet.business_name,
        "ownership_percentage": float(worksheet.ownership_percentage or 100),
        "months_of_statements": worksheet.months_of_statements,
        "calculation_method": worksheet.calculation_method.value,
        "ltv_percentage": float(worksheet.ltv_percentage or 80),
        "cpa_expense_ratio": float(worksheet.cpa_expense_ratio) if worksheet.cpa_expense_ratio else None,
        "has_separate_business_account": worksheet.has_separate_business_account,
        "status": worksheet.status.value,
        "calculated_monthly_income": float(worksheet.calculated_monthly_income or 0),
        "calculated_annual_income": float(worksheet.calculated_annual_income or 0),
        "accounts": accounts_data,
        "created_at": worksheet.created_at.isoformat(),
        "updated_at": worksheet.updated_at.isoformat()
    }


@router.get("/loan/{loan_id}/worksheet")
async def get_worksheet_by_loan(
    loan_id: int,
    db: Session = Depends(get_db),
):
    """Get worksheet for a specific loan."""
    worksheet = db.query(BankStatementWorksheet).filter(
        BankStatementWorksheet.loan_id == loan_id
    ).first()

    if not worksheet:
        return {"exists": False, "worksheet": None}

    return {
        "exists": True,
        "worksheet_id": worksheet.id,
        "status": worksheet.status.value,
        "calculated_monthly_income": float(worksheet.calculated_monthly_income or 0)
    }


# =============================================================================
# DOCUMENT EXTRACTION
# =============================================================================

@router.post("/worksheets/{worksheet_id}/extract")
async def extract_from_documents(
    worksheet_id: int,
    document_ids: List[int],
    statement_type: str = "PERSONAL",
    db: Session = Depends(get_db),
):
    """
    Extract bank statement data from uploaded documents using AI.
    """
    worksheet = db.query(BankStatementWorksheet).filter(
        BankStatementWorksheet.id == worksheet_id
    ).first()

    if not worksheet:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    # Get or create account
    try:
        stmt_type = StatementType(statement_type)
    except ValueError:
        stmt_type = StatementType.PERSONAL

    account = db.query(BankStatementAccount).filter(
        BankStatementAccount.worksheet_id == worksheet_id,
        BankStatementAccount.statement_type == stmt_type
    ).first()

    if not account:
        account = BankStatementAccount(
            worksheet_id=worksheet_id,
            statement_type=stmt_type,
            document_ids=document_ids,
            extraction_status=ExtractionStatus.PROCESSING
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    else:
        account.document_ids = document_ids
        account.extraction_status = ExtractionStatus.PROCESSING
        db.commit()

    # Get document texts and extract data
    from models.smart_docs_models import SmartDocument

    extraction_service = get_bank_statement_extraction_service()
    extracted_months = []

    for doc_id in document_ids:
        doc = db.query(SmartDocument).filter(SmartDocument.id == doc_id).first()
        if doc and doc.ocr_text:
            # Extract data from document
            result = await extraction_service.extract_statement_data(
                document_text=doc.ocr_text,
                statement_type=statement_type,
                context={"borrower_name": worksheet.borrower_name}
            )

            if "error" not in result:
                result["source_document_id"] = doc_id
                extracted_months.append(result)

    # Save extracted data
    for i, month_data in enumerate(extracted_months):
        month = BankStatementMonth(
            account_id=account.id,
            worksheet_id=worksheet_id,
            month_number=i + 1,
            statement_month=month_data.get("statement_month"),
            statement_end_date=month_data.get("statement_end_date"),
            total_deposits=month_data.get("total_deposits", 0),
            ineligible_deposits=month_data.get("ineligible_deposits_total", 0),
            eligible_deposits=month_data.get("eligible_deposits_total", 0),
            beginning_balance=month_data.get("beginning_balance", 0),
            ending_balance=month_data.get("ending_balance", 0),
            nsf_count=month_data.get("nsf_count", 0),
            source_document_id=month_data.get("source_document_id"),
            extraction_confidence=month_data.get("extraction_confidence")
        )
        db.add(month)

    account.extraction_status = ExtractionStatus.COMPLETED
    account.bank_name = extracted_months[0].get("bank_name") if extracted_months else None
    account.account_last_four = extracted_months[0].get("account_last_four") if extracted_months else None

    # Update worksheet status
    worksheet.status = ExtractionStatus.COMPLETED if extracted_months else ExtractionStatus.NEEDS_REVIEW

    # Calculate income
    if extracted_months:
        income_result = extraction_service.calculate_qualifying_income(
            monthly_data=extracted_months,
            calculation_method=worksheet.calculation_method.value,
            ownership_percentage=float(worksheet.ownership_percentage or 100),
            ltv_percentage=float(worksheet.ltv_percentage or 80),
            cpa_expense_ratio=float(worksheet.cpa_expense_ratio) if worksheet.cpa_expense_ratio else None
        )
        worksheet.calculated_monthly_income = income_result["monthly_qualifying_income"]
        worksheet.calculated_annual_income = income_result["annual_qualifying_income"]

    db.commit()

    return {
        "success": True,
        "message": f"Extracted {len(extracted_months)} months of data",
        "months_extracted": len(extracted_months),
        "calculated_monthly_income": float(worksheet.calculated_monthly_income or 0),
        "calculated_annual_income": float(worksheet.calculated_annual_income or 0)
    }


# =============================================================================
# WORKSHEET DOWNLOAD
# =============================================================================

@router.get("/worksheets/{worksheet_id}/download")
async def download_worksheet(
    worksheet_id: int,
    db: Session = Depends(get_db),
):
    """
    Download the completed bank statement worksheet as Excel file.
    """
    worksheet = db.query(BankStatementWorksheet).filter(
        BankStatementWorksheet.id == worksheet_id
    ).first()

    if not worksheet:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    # Get all accounts and monthly data
    accounts = db.query(BankStatementAccount).filter(
        BankStatementAccount.worksheet_id == worksheet_id
    ).all()

    personal_data = []
    business_data = []

    for account in accounts:
        months = db.query(BankStatementMonth).filter(
            BankStatementMonth.account_id == account.id
        ).order_by(BankStatementMonth.month_number).all()

        month_list = [
            {
                "statement_month": m.statement_month,
                "statement_end_date": str(m.statement_end_date) if m.statement_end_date else "",
                "total_deposits": float(m.total_deposits or 0),
                "ineligible_deposits_total": float(m.ineligible_deposits or 0),
                "eligible_deposits_total": float(m.eligible_deposits or 0),
                "beginning_balance": float(m.beginning_balance or 0),
                "ending_balance": float(m.ending_balance or 0),
                "nsf_count": m.nsf_count or 0,
                "bank_name": account.bank_name,
                "account_last_four": account.account_last_four
            }
            for m in months
        ]

        if account.statement_type == StatementType.PERSONAL:
            personal_data = month_list
        else:
            business_data = month_list

    # Generate worksheet
    generator = get_worksheet_generator()
    excel_buffer = generator.generate_worksheet(
        borrower_name=worksheet.borrower_name or "Borrower",
        business_name=worksheet.business_name,
        personal_data=personal_data,
        business_data=business_data,
        calculation_method=worksheet.calculation_method.value,
        ownership_percentage=float(worksheet.ownership_percentage or 100),
        ltv_percentage=float(worksheet.ltv_percentage or 80),
        cpa_expense_ratio=float(worksheet.cpa_expense_ratio) if worksheet.cpa_expense_ratio else None,
        months=worksheet.months_of_statements
    )

    filename = f"Bank_Statement_Worksheet_{worksheet.borrower_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        excel_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/admin/create-tables")
async def create_tables(
    admin_key: str = None,
):
    """
    Admin endpoint to create bank statement tables.
    """
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    from database import engine
    from models.bank_statement_models import (
        BankStatementWorksheet, BankStatementAccount,
        BankStatementMonth, BankStatementIneligibleItem
    )

    tables = [
        BankStatementWorksheet.__table__,
        BankStatementAccount.__table__,
        BankStatementMonth.__table__,
        BankStatementIneligibleItem.__table__,
    ]

    created = []
    for table in tables:
        try:
            table.create(bind=engine, checkfirst=True)
            created.append(table.name)
        except Exception as e:
            logger.error(f"Error creating table {table.name}: {e}")

    return {
        "success": True,
        "message": f"Created tables: {', '.join(created)}",
        "tables": created
    }


@router.post("/worksheets/{worksheet_id}/update-data")
async def update_worksheet_data(
    worksheet_id: int,
    request: WorksheetUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update worksheet with manual data entry or corrections.
    """
    worksheet = db.query(BankStatementWorksheet).filter(
        BankStatementWorksheet.id == worksheet_id
    ).first()

    if not worksheet:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    def save_account_data(account_input: AccountDataInput, stmt_type: StatementType):
        # Get or create account
        account = db.query(BankStatementAccount).filter(
            BankStatementAccount.worksheet_id == worksheet_id,
            BankStatementAccount.statement_type == stmt_type
        ).first()

        if not account:
            account = BankStatementAccount(
                worksheet_id=worksheet_id,
                statement_type=stmt_type,
                bank_name=account_input.bank_name,
                account_last_four=account_input.account_last_four,
                extraction_status=ExtractionStatus.COMPLETED
            )
            db.add(account)
            db.flush()
        else:
            account.bank_name = account_input.bank_name
            account.account_last_four = account_input.account_last_four

        # Delete existing months
        db.query(BankStatementMonth).filter(
            BankStatementMonth.account_id == account.id
        ).delete()

        # Add new months
        for month_data in account_input.monthly_data:
            month = BankStatementMonth(
                account_id=account.id,
                worksheet_id=worksheet_id,
                month_number=month_data.month_number,
                statement_month=month_data.statement_month,
                total_deposits=month_data.total_deposits,
                ineligible_deposits=month_data.ineligible_deposits,
                eligible_deposits=month_data.eligible_deposits,
                beginning_balance=month_data.beginning_balance,
                ending_balance=month_data.ending_balance,
                nsf_count=month_data.nsf_count,
                manually_verified=True
            )
            db.add(month)

    if request.personal_account:
        save_account_data(request.personal_account, StatementType.PERSONAL)

    if request.business_account:
        save_account_data(request.business_account, StatementType.BUSINESS)

    worksheet.status = ExtractionStatus.COMPLETED
    worksheet.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {"success": True, "message": "Worksheet data updated"}
