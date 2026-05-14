"""
Data Import Routes - CSV/Excel Lead Import with Field Mapping, Preview, and Rollback

Enterprise Readiness Domain 10 (Migration & Data Import):
  - Check 10.8:  Generic CSV lead/contact import
  - Check 10.9:  Field mapping UI support (save/load templates)
  - Check 10.10: Import validation with dry-run/preview mode
  - Check 10.11: Import rollback capability (with hard-delete option)
  - Check 10.14: Bulk import progress tracking

Endpoints:
  POST   /api/v1/imports/preview              - Dry-run preview of import
  POST   /api/v1/imports/execute              - Execute import (streaming + savepoints)
  POST   /api/v1/imports/csv                  - Stream CSV import with field mapping
  POST   /api/v1/imports/excel                - Stream Excel import
  POST   /api/v1/imports/leads                - Quick import (auto-map + execute)
  GET    /api/v1/imports                      - List import history (audit trail)
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

MAX_FILE_SIZE_MB = 50
MAX_ROWS = 100_000
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
        from services.import_service import check_file_size, stream_csv_rows, stream_excel_rows
        from utils.validators import validate_upload_mime_type, ALLOWED_IMPORT_MIME_TYPES

        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0

        # --- Validate MIME type ---
        claimed_type = file.content_type or "application/octet-stream"
        filename = file.filename or "upload.csv"
        is_valid, mime_error = validate_upload_mime_type(filename, claimed_type, ALLOWED_IMPORT_MIME_TYPES)
        if not is_valid:
            raise HTTPException(status_code=400, detail=mime_error)

        # --- Check file size without reading into memory ---
        try:
            check_file_size(file.file, MAX_FILE_SIZE_MB * 1024 * 1024)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # --- Stream rows for preview ---
        is_excel = filename.lower().endswith((".xlsx", ".xls"))

        try:
            if is_excel:
                row_gen = stream_excel_rows(file.file)
            else:
                row_gen = stream_csv_rows(file.file)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        headers = None
        rows: list[dict] = []
        try:
            for hdrs, row_dict, row_num in row_gen:
                if headers is None:
                    headers = hdrs
                rows.append(row_dict)
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
    # IMPORT EXECUTION ENDPOINT (transaction-safe with savepoints)
    # ==================================================================

    @app.post("/api/v1/imports/execute", tags=["Data Import"])
    async def execute_import(
        file: UploadFile = File(...),
        field_mapping: str = Form(...),
        duplicate_strategy: str = Form("skip"),
        default_stage: str = Form("New"),
        default_source: Optional[str] = Form(None),
        skip_invalid_rows: bool = Form(True),
        async_mode: Optional[str] = Form(None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Execute a bulk lead import from CSV/Excel with transaction safety.

        Uses savepoints for batch-level atomicity: if the import fails,
        all changes are rolled back. Records are processed in streaming
        chunks of 100 rows, never loading the entire file into memory.

        **Async background mode**: When the file exceeds 5 MB or an
        estimated 5,000 rows (or when ``async_mode=force`` is passed),
        the import is saved to a temp file and processed in a background
        thread. The endpoint returns immediately with a job_id and a
        polling URL (``GET /api/v1/imports/{import_id}/status``).

        Parameters:
          - file: CSV or Excel file (max 50MB)
          - field_mapping: JSON mapping of source_column -> lead_field
          - duplicate_strategy: 'skip' | 'update' | 'create'
          - default_stage: Default stage for new leads (default: 'New')
          - default_source: Default source value
          - skip_invalid_rows: If true, skip rows with errors instead of aborting
          - async_mode: 'auto' (default) | 'force' | 'sync'

        Returns import_id for tracking progress.
        """
        from concurrent.futures import ThreadPoolExecutor

        from services.import_service import (
            ImportService,
            check_file_size,
            estimate_row_count,
            run_background_import,
            save_upload_to_temp,
            should_run_async,
        )
        from utils.validators import validate_upload_mime_type, ALLOWED_IMPORT_MIME_TYPES

        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        # Validate MIME type before processing
        filename = file.filename or "upload.csv"
        claimed_type = file.content_type or "application/octet-stream"
        is_valid, mime_error = validate_upload_mime_type(filename, claimed_type, ALLOWED_IMPORT_MIME_TYPES)
        if not is_valid:
            raise HTTPException(status_code=400, detail=mime_error)

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

        # Check file size without reading entire file into memory
        try:
            file_size = check_file_size(file.file, MAX_FILE_SIZE_MB * 1024 * 1024)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # ---------------------------------------------------------------
        # Decide sync vs. async
        # ---------------------------------------------------------------
        effective_async = async_mode or "auto"
        if effective_async == "force":
            use_async = True
        elif effective_async == "sync":
            use_async = False
        else:
            # Auto: check file size and estimated row count
            estimated_rows = estimate_row_count(file.file, filename)
            use_async = should_run_async(file_size, estimated_rows)

        # ---------------------------------------------------------------
        # ASYNC PATH: save file, create queued job, dispatch to thread
        # ---------------------------------------------------------------
        if use_async:
            import_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            try:
                tmp_path = save_upload_to_temp(file.file, filename)
            except Exception as e:
                logger.exception("Failed to save upload to temp file: %s", e)
                raise HTTPException(status_code=500, detail="Failed to stage file for background import")

            # Create a queued import_jobs record so status polling works
            # immediately.
            db.execute(text("""
                INSERT INTO import_jobs
                    (id, organization_id, created_by, status, filename,
                     total_rows, duplicate_strategy, field_mapping, created_at)
                VALUES
                    (:id, :org_id, :user_id, 'queued', :filename,
                     0, :dup, :mapping, :created)
            """), {
                "id": import_id,
                "org_id": org_id,
                "user_id": user_id,
                "filename": filename,
                "dup": duplicate_strategy,
                "mapping": json.dumps(mapping),
                "created": now,
            })
            db.commit()

            # Dispatch to a daemon thread via ThreadPoolExecutor
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="import")
            executor.submit(
                run_background_import,
                import_id=import_id,
                tmp_path=tmp_path,
                filename=filename,
                user_id=user_id,
                organization_id=org_id,
                field_mapping=mapping,
                duplicate_strategy=duplicate_strategy,
                default_stage=default_stage,
                default_source=default_source,
                skip_invalid_rows=skip_invalid_rows,
                validate_row_fn=validate_row,
                transform_value_fn=transform_value,
            )
            # Allow the executor to shut down when the thread finishes
            executor.shutdown(wait=False)

            return {
                "import_id": import_id,
                "status": "queued",
                "async": True,
                "filename": filename,
                "message": (
                    "Import is too large for synchronous processing. "
                    "It has been queued for background processing."
                ),
                "poll_url": f"/api/v1/imports/{import_id}/status",
            }

        # ---------------------------------------------------------------
        # SYNC PATH: original behavior
        # ---------------------------------------------------------------
        svc = ImportService(db=db, user_id=user_id, organization_id=org_id)
        is_excel = filename.lower().endswith((".xlsx", ".xls"))

        try:
            if is_excel:
                result = svc.import_excel(
                    file_stream=file.file,
                    entity_type="leads",
                    field_mapping=mapping,
                    filename=filename,
                    duplicate_strategy=duplicate_strategy,
                    default_stage=default_stage,
                    default_source=default_source,
                    skip_invalid_rows=skip_invalid_rows,
                    validate_row_fn=validate_row,
                    transform_value_fn=transform_value,
                )
            else:
                result = svc.import_csv(
                    file_stream=file.file,
                    entity_type="leads",
                    field_mapping=mapping,
                    filename=filename,
                    duplicate_strategy=duplicate_strategy,
                    default_stage=default_stage,
                    default_source=default_source,
                    skip_invalid_rows=skip_invalid_rows,
                    validate_row_fn=validate_row,
                    transform_value_fn=transform_value,
                )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {
            "import_id": result.import_id,
            "status": result.status,
            "async": False,
            "filename": result.filename,
            "total_rows": result.total_rows,
            "imported": result.imported,
            "updated": result.updated,
            "skipped": result.skipped,
            "duplicate_rows": result.duplicate_rows,
            "errors": result.errors,
            "error_details": result.error_details[:50],
            "message": result.message,
        }

    # ==================================================================
    # STREAMING CSV IMPORT ENDPOINT
    # ==================================================================

    @app.post("/api/v1/imports/csv", tags=["Data Import"])
    async def import_csv(
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
        Stream-process a CSV file with transaction safety.

        Processes the file row-by-row using a streaming CSV parser.
        Each batch of 100 rows is wrapped in a database savepoint.
        On failure, all changes are atomically rolled back.

        Parameters:
          - file: CSV file (max 50MB)
          - field_mapping: JSON mapping of source_column -> lead_field
          - duplicate_strategy: 'skip' | 'update' | 'create'
          - default_stage: Default stage for new leads
          - default_source: Default source value
          - skip_invalid_rows: If true, skip invalid rows
        """
        from services.import_service import ImportService, check_file_size
        from utils.validators import validate_upload_mime_type, ALLOWED_IMPORT_MIME_TYPES

        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        # Validate MIME type
        claimed_type = file.content_type or "application/octet-stream"
        is_valid, mime_error = validate_upload_mime_type(
            file.filename or "upload.csv", claimed_type, ALLOWED_IMPORT_MIME_TYPES
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=mime_error)

        try:
            mapping = json.loads(field_mapping)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid field_mapping JSON")

        if not mapping:
            raise HTTPException(status_code=400, detail="field_mapping is required")

        try:
            check_file_size(file.file, MAX_FILE_SIZE_MB * 1024 * 1024)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        svc = ImportService(db=db, user_id=user_id, organization_id=org_id)

        try:
            result = svc.import_csv(
                file_stream=file.file,
                entity_type="leads",
                field_mapping=mapping,
                filename=file.filename or "upload.csv",
                duplicate_strategy=duplicate_strategy,
                default_stage=default_stage,
                default_source=default_source,
                skip_invalid_rows=skip_invalid_rows,
                validate_row_fn=validate_row,
                transform_value_fn=transform_value,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {
            "import_id": result.import_id,
            "status": result.status,
            "filename": result.filename,
            "total_rows": result.total_rows,
            "imported": result.imported,
            "updated": result.updated,
            "skipped": result.skipped,
            "duplicate_rows": result.duplicate_rows,
            "errors": result.errors,
            "error_details": result.error_details[:50],
            "message": result.message,
        }

    # ==================================================================
    # STREAMING EXCEL IMPORT ENDPOINT
    # ==================================================================

    @app.post("/api/v1/imports/excel", tags=["Data Import"])
    async def import_excel(
        file: UploadFile = File(...),
        field_mapping: str = Form(...),
        sheet_name: Optional[str] = Form(None),
        duplicate_strategy: str = Form("skip"),
        default_stage: str = Form("New"),
        default_source: Optional[str] = Form(None),
        skip_invalid_rows: bool = Form(True),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Stream-process an Excel file with transaction safety.

        Uses openpyxl read_only mode for memory-efficient streaming.
        Each batch of 100 rows is wrapped in a database savepoint.

        Parameters:
          - file: Excel file (.xlsx/.xls, max 50MB)
          - field_mapping: JSON mapping of source_column -> lead_field
          - sheet_name: Specific sheet name (None = active sheet)
          - duplicate_strategy: 'skip' | 'update' | 'create'
          - default_stage: Default stage for new leads
          - default_source: Default source value
          - skip_invalid_rows: If true, skip invalid rows
        """
        from services.import_service import ImportService, check_file_size
        from utils.validators import validate_upload_mime_type, ALLOWED_IMPORT_MIME_TYPES

        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        # Validate MIME type
        claimed_type = file.content_type or "application/octet-stream"
        is_valid, mime_error = validate_upload_mime_type(
            file.filename or "upload.xlsx", claimed_type, ALLOWED_IMPORT_MIME_TYPES
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=mime_error)

        try:
            mapping = json.loads(field_mapping)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid field_mapping JSON")

        if not mapping:
            raise HTTPException(status_code=400, detail="field_mapping is required")

        try:
            check_file_size(file.file, MAX_FILE_SIZE_MB * 1024 * 1024)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        svc = ImportService(db=db, user_id=user_id, organization_id=org_id)

        try:
            result = svc.import_excel(
                file_stream=file.file,
                entity_type="leads",
                field_mapping=mapping,
                filename=file.filename or "upload.xlsx",
                sheet_name=sheet_name,
                duplicate_strategy=duplicate_strategy,
                default_stage=default_stage,
                default_source=default_source,
                skip_invalid_rows=skip_invalid_rows,
                validate_row_fn=validate_row,
                transform_value_fn=transform_value,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {
            "import_id": result.import_id,
            "status": result.status,
            "filename": result.filename,
            "total_rows": result.total_rows,
            "imported": result.imported,
            "updated": result.updated,
            "skipped": result.skipped,
            "duplicate_rows": result.duplicate_rows,
            "errors": result.errors,
            "error_details": result.error_details[:50],
            "message": result.message,
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
        Uses streaming + savepoints for transaction safety.
        For full control, use /preview then /execute.
        """
        from services.import_service import ImportService, check_file_size, stream_csv_rows, stream_excel_rows
        from utils.validators import validate_upload_mime_type, ALLOWED_IMPORT_MIME_TYPES

        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        # Validate MIME type
        filename = file.filename or "upload.csv"
        claimed_type = file.content_type or "application/octet-stream"
        is_valid, mime_error = validate_upload_mime_type(filename, claimed_type, ALLOWED_IMPORT_MIME_TYPES)
        if not is_valid:
            raise HTTPException(status_code=400, detail=mime_error)

        # Check file size
        try:
            check_file_size(file.file, MAX_FILE_SIZE_MB * 1024 * 1024)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        is_excel = filename.lower().endswith((".xlsx", ".xls"))

        # Read a small preview to detect headers for auto-mapping
        # (We need headers before we can start the import)
        try:
            if is_excel:
                gen = stream_excel_rows(file.file)
            else:
                gen = stream_csv_rows(file.file)

            # Get first row to extract headers
            headers, first_row, _ = next(gen)
        except StopIteration:
            raise HTTPException(status_code=400, detail="File contains no data rows")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        mapping = auto_detect_mapping(headers)
        if not mapping:
            raise HTTPException(
                status_code=400,
                detail="Could not auto-detect any field mappings from column headers. "
                "Please use /api/v1/imports/preview with explicit field_mapping.",
            )

        # Reset file to beginning for full import
        file.file.seek(0)

        svc = ImportService(db=db, user_id=user_id, organization_id=org_id)

        try:
            if is_excel:
                result = svc.import_excel(
                    file_stream=file.file,
                    entity_type="leads",
                    field_mapping=mapping,
                    filename=filename,
                    duplicate_strategy=duplicate_strategy,
                    default_stage=default_stage,
                    default_source=default_source,
                    skip_invalid_rows=True,
                    validate_row_fn=validate_row,
                    transform_value_fn=transform_value,
                )
            else:
                result = svc.import_csv(
                    file_stream=file.file,
                    entity_type="leads",
                    field_mapping=mapping,
                    filename=filename,
                    duplicate_strategy=duplicate_strategy,
                    default_stage=default_stage,
                    default_source=default_source,
                    skip_invalid_rows=True,
                    validate_row_fn=validate_row,
                    transform_value_fn=transform_value,
                )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {
            "import_id": result.import_id,
            "status": result.status,
            "auto_detected_mapping": mapping,
            "filename": result.filename,
            "total_rows": result.total_rows,
            "imported": result.imported,
            "updated": result.updated,
            "skipped": result.skipped,
            "duplicate_rows": result.duplicate_rows,
            "errors": result.errors,
            "error_details": result.error_details[:50],
            "message": result.message,
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
        """Get import job progress and status.

        For active imports, returns real-time in-memory progress.
        For completed imports, returns the persisted record.
        """
        from services.import_service import ImportService

        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        svc = ImportService(db=db, user_id=user_id, organization_id=org_id)
        result = svc.get_import_status(import_id)

        if not result:
            raise HTTPException(status_code=404, detail="Import job not found")

        return result

    # ==================================================================
    # IMPORT HISTORY (Audit Trail)
    # ==================================================================

    @app.get("/api/v1/imports", tags=["Data Import"])
    @app.get("/api/v1/imports/history", tags=["Data Import"])
    async def list_imports(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        status: Optional[str] = Query(None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List import history for this organization (audit trail).

        Returns who imported what, when, and how many records were affected.
        """
        from services.import_service import ImportService

        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        svc = ImportService(db=db, user_id=user_id, organization_id=org_id)
        return svc.get_import_history(
            limit=limit,
            offset=offset,
            status_filter=status,
        )

    # ==================================================================
    # IMPORT ROLLBACK (soft-delete or hard-delete)
    # ==================================================================

    @app.post("/api/v1/imports/{import_id}/rollback", tags=["Data Import"])
    async def rollback_import(
        import_id: str,
        hard_delete: bool = Query(False, description="If true, permanently delete records instead of soft-delete"),
        confirm: bool = Query(False, description="Required for hard-delete rollbacks. Set to true to confirm permanent deletion."),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Rollback a completed import.

        By default, performs soft-delete (sets stage to 'Withdrawn' with
        a rollback note). Pass ?hard_delete=true to permanently remove
        the imported records.

        Hard-delete requires ?confirm=true. Without it, the endpoint
        returns the count of records that would be deleted so the caller
        can prompt the user for confirmation.

        The operation is wrapped in a savepoint for safety.
        """
        from services.import_service import ImportService

        _ensure_tables(db)
        org_id = getattr(current_user, "organization_id", None) or 0
        user_id = getattr(current_user, "id", None)

        # ---------------------------------------------------------------
        # Hard-delete confirmation gate
        # ---------------------------------------------------------------
        if hard_delete and not confirm:
            # Look up the import job to report how many records would be
            # permanently deleted, without actually deleting anything.
            job = db.execute(text("""
                SELECT imported_lead_ids, filename
                FROM import_jobs
                WHERE id = :id AND organization_id = :org_id
            """), {"id": import_id, "org_id": org_id}).fetchone()

            if not job:
                raise HTTPException(status_code=404, detail=f"Import job {import_id} not found")

            lead_ids_raw = job[0]
            if isinstance(lead_ids_raw, str):
                try:
                    lead_ids = json.loads(lead_ids_raw)
                except json.JSONDecodeError:
                    lead_ids = []
            elif isinstance(lead_ids_raw, list):
                lead_ids = lead_ids_raw
            else:
                lead_ids = []

            raise HTTPException(
                status_code=400,
                detail={
                    "message": (
                        f"Hard-delete will permanently remove {len(lead_ids)} "
                        f"lead(s) imported from '{job[1] or 'unknown'}'. "
                        "This action cannot be undone. "
                        "Re-submit with ?hard_delete=true&confirm=true to proceed."
                    ),
                    "records_to_delete": len(lead_ids),
                    "import_id": import_id,
                    "requires_confirmation": True,
                },
            )

        svc = ImportService(db=db, user_id=user_id, organization_id=org_id)

        try:
            result = svc.rollback_import(
                batch_id=import_id,
                hard_delete=hard_delete,
            )

            # Log hard-delete rollbacks to audit trail
            if hard_delete:
                logger.warning(
                    "AUDIT: Hard-delete rollback executed — import_id=%s, "
                    "user_id=%s, org_id=%s, leads_affected=%s",
                    import_id,
                    user_id,
                    org_id,
                    result.get("leads_affected", 0),
                )

            return result
        except ValueError as e:
            status_code = 404 if "not found" in str(e).lower() else 400
            raise HTTPException(status_code=status_code, detail=str(e))

    logger.info("Data import routes registered (13 endpoints)")
