"""
Data Import Routes - CSV/Excel Lead Import with Field Mapping, Preview, and Rollback

Enterprise Readiness Domain 10 (Migration & Data Import):
  - Check 10.8:  Generic CSV lead/contact import
  - Check 10.9:  Field mapping UI support (save/load templates)
  - Check 10.10: Import validation with dry-run/preview mode
  - Check 10.11: Import rollback capability
  - Check 10.14: Bulk import progress tracking

Endpoints:
  POST   /api/v1/imports/preview              - Dry-run preview of import
  POST   /api/v1/imports/execute              - Execute import
  POST   /api/v1/imports/leads                - Quick import (auto-map + execute)
  GET    /api/v1/imports                      - List import history
  GET    /api/v1/imports/{import_id}/status    - Import progress/status
  POST   /api/v1/imports/{import_id}/rollback  - Rollback a completed import
  POST   /api/v1/imports/field-mappings        - Save field mapping template
  GET    /api/v1/imports/field-mappings         - List saved templates
  GET    /api/v1/imports/field-mappings/{id}    - Get a template
  DELETE /api/v1/imports/field-mappings/{id}    - Delete a template
"""
import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_MB = 10
MAX_ROWS = 50_000
PREVIEW_ROW_COUNT = 10

# Columns the Lead table actually accepts
LEAD_IMPORTABLE_FIELDS = {
    "name", "first_name", "last_name", "email", "phone",
    "stage", "source", "owner_id",
    "co_applicant_name", "co_applicant_email", "co_applicant_phone",
    "preferred_communication",
    "loan_type", "preapproval_amount", "credit_score",
    "address", "city", "state", "zip_code",
    "property_type", "property_value", "down_payment",
    "employment_status", "annual_income", "monthly_debts",
    "first_time_buyer", "loan_amount", "notes",
    "organization_code", "lender",
}

# Fuzzy header -> canonical field mapping used for auto-detection
_HEADER_ALIASES: Dict[str, str] = {
    # name
    "full name": "name", "fullname": "name", "contact name": "name",
    "borrower name": "name", "client name": "name", "lead name": "name",
    "name": "name",
    # first / last
    "first name": "first_name", "firstname": "first_name",
    "first": "first_name", "fname": "first_name", "given name": "first_name",
    "last name": "last_name", "lastname": "last_name",
    "last": "last_name", "lname": "last_name", "surname": "last_name",
    "family name": "last_name",
    # email
    "email": "email", "email address": "email", "e-mail": "email",
    "emailaddress": "email", "contact email": "email",
    # phone
    "phone": "phone", "phone number": "phone", "phonenumber": "phone",
    "mobile": "phone", "cell": "phone", "cell phone": "phone",
    "telephone": "phone", "contact phone": "phone",
    # stage
    "stage": "stage", "status": "stage", "lead stage": "stage",
    "lead status": "stage", "pipeline stage": "stage",
    # source
    "source": "source", "lead source": "source", "origin": "source",
    "referral source": "source", "channel": "source",
    # address
    "address": "address", "street": "address", "street address": "address",
    "property address": "address",
    "city": "city", "town": "city",
    "state": "state", "province": "state", "st": "state",
    "zip": "zip_code", "zip code": "zip_code", "zipcode": "zip_code",
    "postal code": "zip_code", "postal": "zip_code",
    # financial
    "loan amount": "loan_amount", "loanamount": "loan_amount",
    "loan type": "loan_type", "loantype": "loan_type",
    "credit score": "credit_score", "creditscore": "credit_score",
    "fico": "credit_score", "fico score": "credit_score",
    "income": "annual_income", "annual income": "annual_income",
    "property value": "property_value", "home value": "property_value",
    "down payment": "down_payment", "downpayment": "down_payment",
    "preapproval": "preapproval_amount", "pre-approval": "preapproval_amount",
    "preapproval amount": "preapproval_amount",
    # property
    "property type": "property_type", "propertytype": "property_type",
    # misc
    "notes": "notes", "comments": "notes", "note": "notes",
    "owner": "owner_id", "assigned to": "owner_id",
    "co-applicant name": "co_applicant_name", "co applicant": "co_applicant_name",
    "co-applicant email": "co_applicant_email",
    "co-applicant phone": "co_applicant_phone",
    "employment": "employment_status", "employment status": "employment_status",
    "first time buyer": "first_time_buyer", "ftb": "first_time_buyer",
    "lender": "lender",
}


# ---------------------------------------------------------------------------
# Pydantic models for request/response
# ---------------------------------------------------------------------------

class FieldMappingTemplate(BaseModel):
    name: str
    description: Optional[str] = None
    mappings: Dict[str, str]  # source_column -> lead_field


class ImportPreviewRequest(BaseModel):
    field_mapping: Optional[Dict[str, str]] = None  # source_col -> lead_field
    mapping_template_id: Optional[int] = None


class ImportExecuteRequest(BaseModel):
    field_mapping: Dict[str, str]
    duplicate_strategy: str = "skip"  # skip | update | create
    default_stage: str = "New"
    default_source: Optional[str] = None
    skip_invalid_rows: bool = True


# ---------------------------------------------------------------------------
# Data transformation helpers
# ---------------------------------------------------------------------------

_PHONE_STRIP_RE = re.compile(r"[^\d+]")


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Normalize phone number to +1XXXXXXXXXX or 10-digit."""
    if not raw or not raw.strip():
        return None
    digits = _PHONE_STRIP_RE.sub("", raw.strip())
    if digits.startswith("+"):
        return digits  # already E.164-ish
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    # Return cleaned but non-standard number as-is
    return digits if digits else None


def normalize_name_case(raw: Optional[str]) -> Optional[str]:
    """Title-case a name, handling edge cases like McDonald, O'Brien."""
    if not raw or not raw.strip():
        return None
    name = raw.strip()
    # Already mixed case (likely correct)? Leave it.
    if name != name.upper() and name != name.lower():
        return name
    parts = name.title().split()
    fixed = []
    for p in parts:
        # Handle Mc/Mac prefixes
        if p.startswith("Mc") and len(p) > 2:
            p = "Mc" + p[2:].capitalize()
        elif p.startswith("Mac") and len(p) > 3 and p[3:4].isalpha():
            p = "Mac" + p[3:].capitalize()
        # Handle O' prefix
        if p.startswith("O'") and len(p) > 2:
            p = "O'" + p[2:].capitalize()
        fixed.append(p)
    return " ".join(fixed)


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def validate_email(raw: Optional[str]) -> Optional[str]:
    """Validate and lowercase email. Returns None if invalid."""
    if not raw or not raw.strip():
        return None
    email = raw.strip().lower()
    if _EMAIL_RE.match(email):
        return email
    return None


def parse_bool(raw: Any) -> Optional[bool]:
    """Parse boolean-ish strings."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "y", "t"):
        return True
    if s in ("0", "false", "no", "n", "f", ""):
        return False
    return None


def parse_float(raw: Any) -> Optional[float]:
    """Parse numeric values, stripping currency symbols."""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("$", "").replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_int(raw: Any) -> Optional[int]:
    """Parse integer values."""
    f = parse_float(raw)
    if f is not None:
        return int(f)
    return None


def transform_value(field: str, raw_value: Any) -> Any:
    """Apply appropriate transformation for a given lead field."""
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        return None

    # Name fields
    if field in ("name", "first_name", "last_name", "co_applicant_name"):
        return normalize_name_case(raw_value)

    # Email fields
    if field in ("email", "co_applicant_email"):
        return validate_email(raw_value)

    # Phone fields
    if field in ("phone", "co_applicant_phone"):
        return normalize_phone(raw_value)

    # Numeric float fields
    if field in (
        "preapproval_amount", "property_value", "down_payment",
        "annual_income", "monthly_debts", "loan_amount",
    ):
        return parse_float(raw_value)

    # Integer fields
    if field in ("credit_score", "owner_id"):
        return parse_int(raw_value)

    # Boolean fields
    if field == "first_time_buyer":
        return parse_bool(raw_value)

    # String fields -- strip whitespace
    return str(raw_value).strip() if raw_value else None


# ---------------------------------------------------------------------------
# File parsing helpers
# ---------------------------------------------------------------------------

def _read_csv_bytes(content: bytes, filename: str) -> tuple[list[str], list[dict]]:
    """Parse CSV bytes, return (headers, rows_as_dicts)."""
    # Try UTF-8 first, then latin-1 fallback
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text_content = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Unable to decode file. Please use UTF-8 encoding.")

    # Sniff dialect
    sample = text_content[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text_content), dialect=dialect)
    headers = reader.fieldnames or []
    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break
        rows.append(row)
    return headers, rows


def _read_excel_bytes(content: bytes, filename: str) -> tuple[list[str], list[dict]]:
    """Parse Excel bytes, return (headers, rows_as_dicts). Requires openpyxl."""
    try:
        import openpyxl
    except ImportError:
        raise ValueError(
            "Excel import requires the openpyxl package. "
            "Please install it: pip install openpyxl"
        )

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise ValueError("Excel file has no active worksheet")

    rows_iter = ws.iter_rows(values_only=True)
    try:
        raw_headers = next(rows_iter)
    except StopIteration:
        raise ValueError("Excel file is empty")

    headers = [str(h).strip() if h else f"column_{i}" for i, h in enumerate(raw_headers)]
    rows = []
    for i, row_values in enumerate(rows_iter):
        if i >= MAX_ROWS:
            break
        row_dict = {}
        for j, val in enumerate(row_values):
            if j < len(headers):
                row_dict[headers[j]] = val
        # Skip completely empty rows
        if any(v is not None and str(v).strip() for v in row_values):
            rows.append(row_dict)
    wb.close()
    return headers, rows


def parse_upload(content: bytes, filename: str) -> tuple[list[str], list[dict]]:
    """Parse uploaded file, return (headers, rows)."""
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xls")):
        return _read_excel_bytes(content, filename)
    else:
        # Default to CSV for .csv, .tsv, .txt
        return _read_csv_bytes(content, filename)


def auto_detect_mapping(headers: list[str]) -> Dict[str, str]:
    """Auto-detect field mapping from header names."""
    mapping: Dict[str, str] = {}
    for header in headers:
        normalized = header.strip().lower().replace("_", " ").replace("-", " ")
        # Exact alias match
        if normalized in _HEADER_ALIASES:
            mapping[header] = _HEADER_ALIASES[normalized]
        # Exact match to field name
        elif normalized.replace(" ", "_") in LEAD_IMPORTABLE_FIELDS:
            mapping[header] = normalized.replace(" ", "_")
        # Otherwise skip (unmapped)
    return mapping


# ---------------------------------------------------------------------------
# Row validation
# ---------------------------------------------------------------------------

def validate_row(row_data: dict, row_index: int) -> tuple[dict, list[str]]:
    """Validate and transform a single mapped row.
    Returns (clean_data, list_of_errors).
    """
    errors: list[str] = []
    clean: dict = {}

    for field, raw in row_data.items():
        if field not in LEAD_IMPORTABLE_FIELDS:
            continue
        val = transform_value(field, raw)
        if val is not None:
            clean[field] = val

    # Must have at least a name or (first_name + last_name)
    has_name = bool(clean.get("name"))
    has_parts = bool(clean.get("first_name")) or bool(clean.get("last_name"))
    if not has_name and not has_parts:
        errors.append(f"Row {row_index}: Missing name (need 'name' or 'first_name'/'last_name')")

    # Synthesize name from parts if needed
    if not has_name and has_parts:
        first = clean.get("first_name", "")
        last = clean.get("last_name", "")
        clean["name"] = f"{first} {last}".strip()

    # Validate email format if provided
    if "email" in row_data:
        raw_email = row_data["email"]
        if raw_email and str(raw_email).strip():
            validated = validate_email(raw_email)
            if validated is None:
                errors.append(f"Row {row_index}: Invalid email '{raw_email}'")
            else:
                clean["email"] = validated

    # Validate credit score range
    cs = clean.get("credit_score")
    if cs is not None and (cs < 300 or cs > 850):
        errors.append(f"Row {row_index}: Credit score {cs} out of range (300-850)")

    return clean, errors


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_data_import_routes(app, get_db, get_current_user, **kwargs):
    """Register data import routes for enterprise CSV/Excel lead import.

    Provides:
      - Field mapping templates (save/load)
      - Dry-run preview with validation
      - Bulk import execution with progress tracking
      - Import rollback (soft-delete)
    """

    # ==================================================================
    # TABLE BOOTSTRAP -- ensure import tracking tables exist
    # ==================================================================

    def _ensure_tables(db: Session):
        """Create import tracking tables if they don't exist."""
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS import_field_mappings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                mappings JSONB NOT NULL DEFAULT '{}',
                created_by INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS import_jobs (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                filename VARCHAR(500),
                total_rows INTEGER DEFAULT 0,
                processed_rows INTEGER DEFAULT 0,
                imported_rows INTEGER DEFAULT 0,
                skipped_rows INTEGER DEFAULT 0,
                error_rows INTEGER DEFAULT 0,
                updated_rows INTEGER DEFAULT 0,
                duplicate_strategy VARCHAR(50) DEFAULT 'skip',
                field_mapping JSONB DEFAULT '{}',
                errors JSONB DEFAULT '[]',
                imported_lead_ids JSONB DEFAULT '[]',
                started_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                rolled_back_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        db.commit()

    # ==================================================================
    # FIELD MAPPING TEMPLATE ENDPOINTS
    # ==================================================================

    @app.post("/api/v1/imports/field-mappings", tags=["Data Import"])
    async def create_field_mapping(
        body: FieldMappingTemplate,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Save a reusable field mapping template."""
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        # Validate mapping targets
        invalid_fields = [
            v for v in body.mappings.values()
            if v not in LEAD_IMPORTABLE_FIELDS
        ]
        if invalid_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid target fields: {', '.join(invalid_fields)}",
            )

        result = db.execute(text("""
            INSERT INTO import_field_mappings (organization_id, name, description, mappings, created_by)
            VALUES (:org_id, :name, :desc, :mappings, :user_id)
            RETURNING id, name, created_at
        """), {
            "org_id": org_id,
            "name": body.name,
            "desc": body.description,
            "mappings": json.dumps(body.mappings),
            "user_id": user_id,
        })
        row = result.fetchone()
        db.commit()

        return {
            "id": row[0],
            "name": row[1],
            "description": body.description,
            "mappings": body.mappings,
            "created_at": row[2].isoformat() if row[2] else None,
        }

    @app.get("/api/v1/imports/field-mappings", tags=["Data Import"])
    async def list_field_mappings(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List saved field mapping templates for this organization."""
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0

        rows = db.execute(text("""
            SELECT id, name, description, mappings, created_at, updated_at
            FROM import_field_mappings
            WHERE organization_id = :org_id
            ORDER BY updated_at DESC
        """), {"org_id": org_id}).fetchall()

        return {
            "templates": [
                {
                    "id": r[0],
                    "name": r[1],
                    "description": r[2],
                    "mappings": r[3] if isinstance(r[3], dict) else json.loads(r[3]) if r[3] else {},
                    "created_at": r[4].isoformat() if r[4] else None,
                    "updated_at": r[5].isoformat() if r[5] else None,
                }
                for r in rows
            ]
        }

    @app.get("/api/v1/imports/field-mappings/{mapping_id}", tags=["Data Import"])
    async def get_field_mapping(
        mapping_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get a specific field mapping template."""
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0

        row = db.execute(text("""
            SELECT id, name, description, mappings, created_at, updated_at
            FROM import_field_mappings
            WHERE id = :id AND organization_id = :org_id
        """), {"id": mapping_id, "org_id": org_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Field mapping template not found")

        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "mappings": row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {},
            "created_at": row[4].isoformat() if row[4] else None,
            "updated_at": row[5].isoformat() if row[5] else None,
        }

    @app.delete("/api/v1/imports/field-mappings/{mapping_id}", tags=["Data Import"])
    async def delete_field_mapping(
        mapping_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Delete a field mapping template."""
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0

        result = db.execute(text("""
            DELETE FROM import_field_mappings
            WHERE id = :id AND organization_id = :org_id
        """), {"id": mapping_id, "org_id": org_id})
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Field mapping template not found")

        return {"deleted": True, "id": mapping_id}

    # ==================================================================
    # IMPORT PREVIEW (DRY-RUN) ENDPOINT
    # ==================================================================

    @app.post("/api/v1/imports/preview", tags=["Data Import"])
    async def preview_import(
        file: UploadFile = File(...),
        field_mapping: Optional[str] = Form(None),
        mapping_template_id: Optional[int] = Form(None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Dry-run import preview. Upload a CSV/Excel file and optionally
        provide field mappings. Returns:
          - Auto-detected or user-provided mappings
          - First 10 rows as they would be imported
          - Validation errors per row
          - Summary statistics
        """
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0

        # --- Read file ---
        content = await file.read()
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.",
            )

        try:
            headers, rows = parse_upload(content, file.filename or "upload.csv")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not headers:
            raise HTTPException(status_code=400, detail="No columns detected in file")
        if not rows:
            raise HTTPException(status_code=400, detail="File contains no data rows")

        # --- Determine mapping ---
        mapping: Dict[str, str] = {}
        if field_mapping:
            try:
                mapping = json.loads(field_mapping)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid field_mapping JSON")
        elif mapping_template_id:
            tpl = db.execute(text("""
                SELECT mappings FROM import_field_mappings
                WHERE id = :id AND organization_id = :org_id
            """), {"id": mapping_template_id, "org_id": org_id}).fetchone()
            if tpl:
                mapping = tpl[0] if isinstance(tpl[0], dict) else json.loads(tpl[0]) if tpl[0] else {}

        # Auto-detect if no mapping provided
        auto_detected = False
        if not mapping:
            mapping = auto_detect_mapping(headers)
            auto_detected = True

        # --- Preview rows ---
        preview_rows = []
        all_errors: list[str] = []
        valid_count = 0
        error_count = 0

        for i, raw_row in enumerate(rows):
            # Map source columns to lead fields
            mapped_row = {}
            for src_col, target_field in mapping.items():
                if src_col in raw_row:
                    mapped_row[target_field] = raw_row[src_col]

            clean, row_errors = validate_row(mapped_row, i + 1)

            if row_errors:
                error_count += 1
                all_errors.extend(row_errors)
            else:
                valid_count += 1

            # Include first N rows in preview
            if i < PREVIEW_ROW_COUNT:
                preview_rows.append({
                    "row_number": i + 1,
                    "original": {k: str(v) if v is not None else None for k, v in raw_row.items()},
                    "mapped": clean,
                    "errors": row_errors,
                    "valid": len(row_errors) == 0,
                })

        # Unmapped columns
        unmapped = [h for h in headers if h not in mapping]

        return {
            "filename": file.filename,
            "total_rows": len(rows),
            "valid_rows": valid_count,
            "error_rows": error_count,
            "columns_detected": headers,
            "field_mapping": mapping,
            "auto_detected": auto_detected,
            "unmapped_columns": unmapped,
            "available_target_fields": sorted(LEAD_IMPORTABLE_FIELDS),
            "preview": preview_rows,
            "errors_summary": all_errors[:50],  # cap at 50
            "ready_to_import": error_count == 0 or valid_count > 0,
        }

    # ==================================================================
    # IMPORT EXECUTION ENDPOINT
    # ==================================================================

    @app.post("/api/v1/imports/execute", tags=["Data Import"])
    async def execute_import(
        file: UploadFile = File(...),
        field_mapping: str = Form(...),
        duplicate_strategy: str = Form("skip"),
        default_stage: str = Form("New"),
        default_source: Optional[str] = Form(None),
        skip_invalid_rows: bool = Form(True),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Execute a bulk lead import from CSV/Excel.

        Parameters:
          - file: CSV or Excel file
          - field_mapping: JSON mapping of source_column -> lead_field
          - duplicate_strategy: 'skip' | 'update' | 'create'
          - default_stage: Default stage for new leads (default: 'New')
          - default_source: Default source value
          - skip_invalid_rows: If true, skip rows with errors instead of aborting

        Returns import_id for tracking progress.
        """
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        # Parse mapping
        try:
            mapping = json.loads(field_mapping)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid field_mapping JSON")

        if not mapping:
            raise HTTPException(status_code=400, detail="field_mapping is required")

        # Validate duplicate strategy
        if duplicate_strategy not in ("skip", "update", "create"):
            raise HTTPException(
                status_code=400,
                detail="duplicate_strategy must be 'skip', 'update', or 'create'",
            )

        # Read file
        content = await file.read()
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.",
            )

        try:
            headers, rows = parse_upload(content, file.filename or "upload.csv")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not rows:
            raise HTTPException(status_code=400, detail="File contains no data rows")

        # Create import job record
        import_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        db.execute(text("""
            INSERT INTO import_jobs
                (id, organization_id, created_by, status, filename,
                 total_rows, duplicate_strategy, field_mapping, started_at, created_at)
            VALUES
                (:id, :org_id, :user_id, 'processing', :filename,
                 :total, :dup, :mapping, :now, :now)
        """), {
            "id": import_id,
            "org_id": org_id,
            "user_id": user_id,
            "filename": file.filename,
            "total": len(rows),
            "dup": duplicate_strategy,
            "mapping": json.dumps(mapping),
            "now": now,
        })
        db.commit()

        # --- Process rows ---
        imported_count = 0
        skipped_count = 0
        error_count = 0
        updated_count = 0
        errors_list: list[dict] = []
        imported_ids: list[int] = []

        for i, raw_row in enumerate(rows):
            # Map columns
            mapped_row = {}
            for src_col, target_field in mapping.items():
                if src_col in raw_row:
                    mapped_row[target_field] = raw_row[src_col]

            clean, row_errors = validate_row(mapped_row, i + 1)

            if row_errors:
                error_count += 1
                errors_list.append({"row": i + 1, "errors": row_errors})
                if not skip_invalid_rows:
                    # Abort entire import
                    db.execute(text("""
                        UPDATE import_jobs
                        SET status = 'failed',
                            processed_rows = :processed,
                            error_rows = :errors,
                            errors = :error_list,
                            completed_at = :now
                        WHERE id = :id
                    """), {
                        "id": import_id,
                        "processed": i + 1,
                        "errors": error_count,
                        "error_list": json.dumps(errors_list),
                        "now": datetime.now(timezone.utc),
                    })
                    db.commit()
                    return {
                        "import_id": import_id,
                        "status": "failed",
                        "message": f"Aborted at row {i + 1} due to validation error",
                        "errors": errors_list,
                    }
                continue

            # Apply defaults
            if "stage" not in clean or not clean["stage"]:
                clean["stage"] = default_stage
            if default_source and ("source" not in clean or not clean["source"]):
                clean["source"] = default_source

            # Set organization scoping
            clean["organization_id"] = org_id

            # Duplicate check (by email within org)
            existing_id = None
            if clean.get("email") and duplicate_strategy != "create":
                dup_row = db.execute(text("""
                    SELECT id FROM leads
                    WHERE email = :email AND organization_id = :org_id
                    LIMIT 1
                """), {"email": clean["email"], "org_id": org_id}).fetchone()
                if dup_row:
                    existing_id = dup_row[0]

            if existing_id and duplicate_strategy == "skip":
                skipped_count += 1
                continue

            if existing_id and duplicate_strategy == "update":
                # Update existing lead with non-null imported values
                update_fields = {
                    k: v for k, v in clean.items()
                    if v is not None and k not in ("organization_id",)
                }
                if update_fields:
                    set_clauses = ", ".join(f"{k} = :{k}" for k in update_fields)
                    update_fields["_id"] = existing_id
                    db.execute(text(f"""
                        UPDATE leads SET {set_clauses} WHERE id = :_id
                    """), update_fields)
                updated_count += 1
                imported_ids.append(existing_id)
                continue

            # Insert new lead
            clean["created_at"] = now
            insert_cols = list(clean.keys())
            col_names = ", ".join(insert_cols)
            col_params = ", ".join(f":{c}" for c in insert_cols)

            result = db.execute(text(f"""
                INSERT INTO leads ({col_names})
                VALUES ({col_params})
                RETURNING id
            """), clean)
            new_id = result.fetchone()[0]
            imported_ids.append(new_id)
            imported_count += 1

            # Periodic progress update (every 100 rows)
            if (i + 1) % 100 == 0:
                db.execute(text("""
                    UPDATE import_jobs
                    SET processed_rows = :processed,
                        imported_rows = :imported,
                        skipped_rows = :skipped,
                        error_rows = :errors,
                        updated_rows = :updated
                    WHERE id = :id
                """), {
                    "id": import_id,
                    "processed": i + 1,
                    "imported": imported_count,
                    "skipped": skipped_count,
                    "errors": error_count,
                    "updated": updated_count,
                })
                db.commit()

        # Final update
        db.execute(text("""
            UPDATE import_jobs
            SET status = 'completed',
                processed_rows = :processed,
                imported_rows = :imported,
                skipped_rows = :skipped,
                error_rows = :errors,
                updated_rows = :updated,
                errors = :error_list,
                imported_lead_ids = :lead_ids,
                completed_at = :now
            WHERE id = :id
        """), {
            "id": import_id,
            "processed": len(rows),
            "imported": imported_count,
            "skipped": skipped_count,
            "errors": error_count,
            "updated": updated_count,
            "error_list": json.dumps(errors_list[:200]),
            "lead_ids": json.dumps(imported_ids),
            "now": datetime.now(timezone.utc),
        })
        db.commit()

        return {
            "import_id": import_id,
            "status": "completed",
            "filename": file.filename,
            "total_rows": len(rows),
            "imported": imported_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "errors": error_count,
            "error_details": errors_list[:50],
        }

    # ==================================================================
    # QUICK IMPORT (auto-detect + execute in one call)
    # ==================================================================

    @app.post("/api/v1/imports/leads", tags=["Data Import"])
    async def quick_import_leads(
        file: UploadFile = File(...),
        duplicate_strategy: str = Form("skip"),
        default_stage: str = Form("New"),
        default_source: Optional[str] = Form(None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Quick import: auto-detect field mappings from headers and import leads.
        For full control, use /preview then /execute.
        """
        _ensure_tables(db)

        content = await file.read()
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum is {MAX_FILE_SIZE_MB}MB.",
            )

        try:
            headers, rows = parse_upload(content, file.filename or "upload.csv")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not rows:
            raise HTTPException(status_code=400, detail="File contains no data rows")

        mapping = auto_detect_mapping(headers)
        if not mapping:
            raise HTTPException(
                status_code=400,
                detail="Could not auto-detect any field mappings from column headers. "
                "Please use /api/v1/imports/preview with explicit field_mapping.",
            )

        # Re-upload internally via execute_import by constructing the form data
        # Instead, inline the logic to avoid re-reading the file
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        import_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        db.execute(text("""
            INSERT INTO import_jobs
                (id, organization_id, created_by, status, filename,
                 total_rows, duplicate_strategy, field_mapping, started_at, created_at)
            VALUES
                (:id, :org_id, :user_id, 'processing', :filename,
                 :total, :dup, :mapping, :now, :now)
        """), {
            "id": import_id,
            "org_id": org_id,
            "user_id": user_id,
            "filename": file.filename,
            "total": len(rows),
            "dup": duplicate_strategy,
            "mapping": json.dumps(mapping),
            "now": now,
        })
        db.commit()

        imported_count = 0
        skipped_count = 0
        error_count = 0
        updated_count = 0
        errors_list: list[dict] = []
        imported_ids: list[int] = []

        for i, raw_row in enumerate(rows):
            mapped_row = {}
            for src_col, target_field in mapping.items():
                if src_col in raw_row:
                    mapped_row[target_field] = raw_row[src_col]

            clean, row_errors = validate_row(mapped_row, i + 1)

            if row_errors:
                error_count += 1
                errors_list.append({"row": i + 1, "errors": row_errors})
                continue

            if "stage" not in clean or not clean["stage"]:
                clean["stage"] = default_stage
            if default_source and ("source" not in clean or not clean["source"]):
                clean["source"] = default_source

            clean["organization_id"] = org_id

            # Duplicate check
            existing_id = None
            if clean.get("email") and duplicate_strategy != "create":
                dup_row = db.execute(text("""
                    SELECT id FROM leads
                    WHERE email = :email AND organization_id = :org_id
                    LIMIT 1
                """), {"email": clean["email"], "org_id": org_id}).fetchone()
                if dup_row:
                    existing_id = dup_row[0]

            if existing_id and duplicate_strategy == "skip":
                skipped_count += 1
                continue

            if existing_id and duplicate_strategy == "update":
                update_fields = {
                    k: v for k, v in clean.items()
                    if v is not None and k not in ("organization_id",)
                }
                if update_fields:
                    set_clauses = ", ".join(f"{k} = :{k}" for k in update_fields)
                    update_fields["_id"] = existing_id
                    db.execute(text(f"""
                        UPDATE leads SET {set_clauses} WHERE id = :_id
                    """), update_fields)
                updated_count += 1
                imported_ids.append(existing_id)
                continue

            clean["created_at"] = now
            insert_cols = list(clean.keys())
            col_names = ", ".join(insert_cols)
            col_params = ", ".join(f":{c}" for c in insert_cols)

            result = db.execute(text(f"""
                INSERT INTO leads ({col_names})
                VALUES ({col_params})
                RETURNING id
            """), clean)
            new_id = result.fetchone()[0]
            imported_ids.append(new_id)
            imported_count += 1

        # Final job update
        db.execute(text("""
            UPDATE import_jobs
            SET status = 'completed',
                processed_rows = :processed,
                imported_rows = :imported,
                skipped_rows = :skipped,
                error_rows = :errors,
                updated_rows = :updated,
                errors = :error_list,
                imported_lead_ids = :lead_ids,
                completed_at = :now
            WHERE id = :id
        """), {
            "id": import_id,
            "processed": len(rows),
            "imported": imported_count,
            "skipped": skipped_count,
            "errors": error_count,
            "updated": updated_count,
            "error_list": json.dumps(errors_list[:200]),
            "lead_ids": json.dumps(imported_ids),
            "now": datetime.now(timezone.utc),
        })
        db.commit()

        return {
            "import_id": import_id,
            "status": "completed",
            "auto_detected_mapping": mapping,
            "filename": file.filename,
            "total_rows": len(rows),
            "imported": imported_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "errors": error_count,
            "error_details": errors_list[:50],
        }

    # ==================================================================
    # IMPORT STATUS / PROGRESS
    # ==================================================================

    @app.get("/api/v1/imports/{import_id}/status", tags=["Data Import"])
    async def get_import_status(
        import_id: str,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get import job progress and status."""
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0

        row = db.execute(text("""
            SELECT id, status, filename, total_rows, processed_rows,
                   imported_rows, skipped_rows, error_rows, updated_rows,
                   duplicate_strategy, field_mapping, errors,
                   started_at, completed_at, rolled_back_at, created_at
            FROM import_jobs
            WHERE id = :id AND organization_id = :org_id
        """), {"id": import_id, "org_id": org_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Import job not found")

        total = row[3] or 1
        processed = row[4] or 0
        progress_pct = round((processed / total) * 100, 1) if total > 0 else 0

        errors_data = row[11]
        if isinstance(errors_data, str):
            try:
                errors_data = json.loads(errors_data)
            except json.JSONDecodeError:
                errors_data = []

        mapping_data = row[10]
        if isinstance(mapping_data, str):
            try:
                mapping_data = json.loads(mapping_data)
            except json.JSONDecodeError:
                mapping_data = {}

        return {
            "import_id": row[0],
            "status": row[1],
            "filename": row[2],
            "progress": {
                "total_rows": row[3],
                "processed_rows": processed,
                "percentage": progress_pct,
            },
            "results": {
                "imported": row[5] or 0,
                "skipped": row[6] or 0,
                "errors": row[7] or 0,
                "updated": row[8] or 0,
            },
            "duplicate_strategy": row[9],
            "field_mapping": mapping_data,
            "error_details": errors_data[:50] if isinstance(errors_data, list) else [],
            "timestamps": {
                "started_at": row[12].isoformat() if row[12] else None,
                "completed_at": row[13].isoformat() if row[13] else None,
                "rolled_back_at": row[14].isoformat() if row[14] else None,
                "created_at": row[15].isoformat() if row[15] else None,
            },
            "can_rollback": row[1] == "completed" and row[14] is None,
        }

    # ==================================================================
    # IMPORT HISTORY
    # ==================================================================

    @app.get("/api/v1/imports", tags=["Data Import"])
    async def list_imports(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        status: Optional[str] = Query(None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List import history for this organization."""
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0

        filters = ["organization_id = :org_id"]
        params: dict = {"org_id": org_id, "limit": limit, "offset": offset}

        if status:
            filters.append("status = :status")
            params["status"] = status

        where_clause = " AND ".join(filters)

        # Get total count
        count_row = db.execute(text(f"""
            SELECT COUNT(*) FROM import_jobs WHERE {where_clause}
        """), params).fetchone()
        total = count_row[0] if count_row else 0

        rows = db.execute(text(f"""
            SELECT id, status, filename, total_rows, imported_rows,
                   skipped_rows, error_rows, updated_rows,
                   duplicate_strategy, started_at, completed_at,
                   rolled_back_at, created_at
            FROM import_jobs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).fetchall()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "imports": [
                {
                    "import_id": r[0],
                    "status": r[1],
                    "filename": r[2],
                    "total_rows": r[3],
                    "imported": r[4] or 0,
                    "skipped": r[5] or 0,
                    "errors": r[6] or 0,
                    "updated": r[7] or 0,
                    "duplicate_strategy": r[8],
                    "started_at": r[9].isoformat() if r[9] else None,
                    "completed_at": r[10].isoformat() if r[10] else None,
                    "rolled_back_at": r[11].isoformat() if r[11] else None,
                    "created_at": r[12].isoformat() if r[12] else None,
                    "can_rollback": r[1] == "completed" and r[11] is None,
                }
                for r in rows
            ],
        }

    # ==================================================================
    # IMPORT ROLLBACK
    # ==================================================================

    @app.post("/api/v1/imports/{import_id}/rollback", tags=["Data Import"])
    async def rollback_import(
        import_id: str,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Rollback a completed import by soft-deleting imported leads.
        Sets stage to 'Withdrawn' and marks them as import-rolled-back
        so they can be recovered if needed.
        """
        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0

        # Get the import job
        job = db.execute(text("""
            SELECT id, status, imported_lead_ids, rolled_back_at
            FROM import_jobs
            WHERE id = :id AND organization_id = :org_id
        """), {"id": import_id, "org_id": org_id}).fetchone()

        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")

        if job[1] != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot rollback import with status '{job[1]}'. Only 'completed' imports can be rolled back.",
            )

        if job[3] is not None:
            raise HTTPException(status_code=400, detail="This import has already been rolled back")

        # Get imported lead IDs
        lead_ids_raw = job[2]
        if isinstance(lead_ids_raw, str):
            try:
                lead_ids = json.loads(lead_ids_raw)
            except json.JSONDecodeError:
                lead_ids = []
        elif isinstance(lead_ids_raw, list):
            lead_ids = lead_ids_raw
        else:
            lead_ids = []

        if not lead_ids:
            raise HTTPException(
                status_code=400,
                detail="No imported lead IDs recorded for this import. Rollback not possible.",
            )

        # Soft-delete: set stage to 'Withdrawn' and add rollback note
        rollback_note = f"[IMPORT ROLLBACK] Rolled back import {import_id} at {datetime.now(timezone.utc).isoformat()}"
        rolled_back_count = 0

        # Process in batches of 100 to avoid overly large IN clauses
        for batch_start in range(0, len(lead_ids), 100):
            batch = lead_ids[batch_start:batch_start + 100]
            placeholders = ", ".join(f":id_{j}" for j in range(len(batch)))
            params_batch: dict = {f"id_{j}": lid for j, lid in enumerate(batch)}
            params_batch["org_id"] = org_id
            params_batch["note"] = rollback_note

            result = db.execute(text(f"""
                UPDATE leads
                SET stage = 'Withdrawn',
                    notes = CASE
                        WHEN notes IS NULL THEN :note
                        ELSE notes || E'\\n' || :note
                    END
                WHERE id IN ({placeholders})
                  AND organization_id = :org_id
            """), params_batch)
            rolled_back_count += result.rowcount

        # Update import job status
        db.execute(text("""
            UPDATE import_jobs
            SET status = 'rolled_back',
                rolled_back_at = :now
            WHERE id = :id
        """), {"id": import_id, "now": datetime.now(timezone.utc)})
        db.commit()

        return {
            "import_id": import_id,
            "status": "rolled_back",
            "leads_affected": rolled_back_count,
            "total_lead_ids": len(lead_ids),
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Successfully rolled back {rolled_back_count} leads (set to Withdrawn stage)",
        }

    logger.info("Data import routes registered (10 endpoints)")
