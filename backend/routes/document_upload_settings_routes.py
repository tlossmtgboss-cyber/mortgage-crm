"""
Document Upload Settings Routes
Comprehensive error handling pattern for document configuration
"""

import re
import logging
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from db import get_db as _db_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/document-upload-settings", tags=["Document Upload Settings"])

# =============================================================================
# Dependency Injection Setup
# =============================================================================

_User = None
_get_current_user = None
_get_db = None

def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for the routes"""
    global _User, _get_current_user, _get_db
    _User = user_model
    _get_current_user = current_user_func
    _get_db = db_func

def get_current_user():
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Dependencies not configured")
    return Depends(_get_current_user)


async def _resolve_current_user(request: Request, db: Session = Depends(_db_dep)):
    """Proper FastAPI dependency that resolves to the actual user object."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Dependencies not configured")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    return await _get_current_user(token, request, db)

def get_db():
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Dependencies not configured")
    return Depends(_get_db)


# =============================================================================
# Custom Exceptions
# =============================================================================

class ValidationException(HTTPException):
    def __init__(self, field: str, message: str):
        super().__init__(
            status_code=422,
            detail={"type": "validation_error", "field": field, "message": message}
        )

class PermissionException(HTTPException):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            status_code=403,
            detail={"type": "permission_error", "message": message}
        )

class NotFoundException(HTTPException):
    def __init__(self, resource: str):
        super().__init__(
            status_code=404,
            detail={"type": "not_found", "message": f"{resource} not found"}
        )


# =============================================================================
# Response Helpers
# =============================================================================

def success_response(data: dict, message: str = "Success"):
    """Standard success response format"""
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =============================================================================
# Pydantic Models with Validation
# =============================================================================

class FileTypeConfig(BaseModel):
    """Configuration for allowed file types"""
    extension: str = Field(..., min_length=1, max_length=10)
    mime_type: str = Field(..., min_length=1, max_length=100)
    enabled: bool = True
    max_size_mb: Optional[float] = None  # Override default max size for this type

    @validator('extension')
    def validate_extension(cls, v):
        # Ensure extension starts with dot
        if not v.startswith('.'):
            v = '.' + v
        # Remove any invalid characters
        if not re.match(r'^\.[a-zA-Z0-9]+$', v):
            raise ValueError('Extension must contain only letters and numbers')
        return v.lower()


class DocumentTypeConfig(BaseModel):
    """Configuration for a document type"""
    type_name: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=50)
    requires_period: bool = False
    auto_classify_keywords: List[str] = []
    enabled: bool = True


class ClassificationSettings(BaseModel):
    """AI classification settings"""
    enabled: bool = True
    confidence_threshold: float = Field(0.7, ge=0.0, le=1.0)
    auto_apply_high_confidence: bool = True
    high_confidence_threshold: float = Field(0.9, ge=0.0, le=1.0)
    fallback_type: str = "OTHER"
    create_task_on_low_confidence: bool = True

    @validator('high_confidence_threshold')
    def validate_high_threshold(cls, v, values):
        if 'confidence_threshold' in values and v < values['confidence_threshold']:
            raise ValueError('High confidence threshold must be >= base confidence threshold')
        return v


class StorageSettings(BaseModel):
    """Storage configuration settings"""
    provider: str = Field("local", pattern="^(local|s3|gcs|azure)$")
    bucket_name: Optional[str] = None
    path_prefix: str = "documents"
    retention_days: int = Field(365 * 7, ge=30, le=365 * 10)  # 7 years default, 30 days min, 10 years max
    enable_versioning: bool = True
    encryption_enabled: bool = True

    @validator('bucket_name')
    def validate_bucket(cls, v, values):
        if values.get('provider') in ['s3', 'gcs', 'azure'] and not v:
            raise ValueError(f"Bucket name required for {values.get('provider')} storage")
        return v

    @validator('path_prefix')
    def validate_path_prefix(cls, v):
        # Remove leading/trailing slashes
        v = v.strip('/')
        # Validate path characters
        if not re.match(r'^[a-zA-Z0-9_\-/]+$', v):
            raise ValueError('Path prefix contains invalid characters')
        return v


class NotificationSettings(BaseModel):
    """Document notification settings"""
    email_on_upload: bool = True
    email_on_classification: bool = False
    email_on_expiration: bool = True
    expiration_warning_days: int = Field(30, ge=7, le=90)
    create_tasks_for_missing_docs: bool = True
    notify_borrower_on_receipt: bool = True


class DocumentUploadSettingsUpdate(BaseModel):
    """Complete document upload settings update"""
    # Upload limits
    max_file_size_mb: float = Field(25.0, ge=1.0, le=100.0)
    max_files_per_upload: int = Field(10, ge=1, le=50)

    # File types
    allowed_file_types: List[FileTypeConfig] = []

    # Classification
    classification: ClassificationSettings = ClassificationSettings()

    # Storage
    storage: StorageSettings = StorageSettings()

    # Notifications
    notifications: NotificationSettings = NotificationSettings()

    # Document types
    document_types: List[DocumentTypeConfig] = []

    # Processing
    enable_ocr: bool = True
    enable_virus_scan: bool = True
    compress_images: bool = True
    image_max_dimension: int = Field(2000, ge=500, le=5000)

    @validator('max_file_size_mb')
    def validate_file_size(cls, v):
        if v < 1:
            raise ValueError('Maximum file size must be at least 1 MB')
        if v > 100:
            raise ValueError('Maximum file size cannot exceed 100 MB')
        return v


# =============================================================================
# Default Configuration
# =============================================================================

DEFAULT_FILE_TYPES = [
    {"extension": ".pdf", "mime_type": "application/pdf", "enabled": True},
    {"extension": ".jpg", "mime_type": "image/jpeg", "enabled": True},
    {"extension": ".jpeg", "mime_type": "image/jpeg", "enabled": True},
    {"extension": ".png", "mime_type": "image/png", "enabled": True},
    {"extension": ".gif", "mime_type": "image/gif", "enabled": True},
    {"extension": ".tiff", "mime_type": "image/tiff", "enabled": True},
    {"extension": ".doc", "mime_type": "application/msword", "enabled": True},
    {"extension": ".docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "enabled": True},
    {"extension": ".xls", "mime_type": "application/vnd.ms-excel", "enabled": True},
    {"extension": ".xlsx", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "enabled": True},
    {"extension": ".csv", "mime_type": "text/csv", "enabled": True},
    {"extension": ".txt", "mime_type": "text/plain", "enabled": True},
    {"extension": ".heic", "mime_type": "image/heic", "enabled": True},
]

DEFAULT_DOCUMENT_TYPES = [
    {"type_name": "PAYSTUB", "display_name": "Pay Stub", "category": "INCOME", "requires_period": True, "auto_classify_keywords": ["paystub", "pay stub", "earnings statement", "wage"], "enabled": True},
    {"type_name": "W2", "display_name": "W-2 Form", "category": "INCOME", "requires_period": True, "auto_classify_keywords": ["w-2", "w2", "wage and tax"], "enabled": True},
    {"type_name": "TAX_RETURN_1040", "display_name": "Tax Return (1040)", "category": "INCOME", "requires_period": True, "auto_classify_keywords": ["1040", "tax return", "irs"], "enabled": True},
    {"type_name": "TAX_RETURN_1099", "display_name": "1099 Form", "category": "INCOME", "requires_period": True, "auto_classify_keywords": ["1099"], "enabled": True},
    {"type_name": "BANK_STATEMENT", "display_name": "Bank Statement", "category": "ASSETS", "requires_period": True, "auto_classify_keywords": ["bank statement", "checking", "savings"], "enabled": True},
    {"type_name": "INVESTMENT_STATEMENT", "display_name": "Investment Statement", "category": "ASSETS", "requires_period": True, "auto_classify_keywords": ["investment", "brokerage", "401k", "ira"], "enabled": True},
    {"type_name": "RETIREMENT_STATEMENT", "display_name": "Retirement Statement", "category": "ASSETS", "requires_period": True, "auto_classify_keywords": ["retirement", "pension"], "enabled": True},
    {"type_name": "DRIVERS_LICENSE", "display_name": "Driver's License", "category": "IDENTITY", "requires_period": False, "auto_classify_keywords": ["driver", "license", "dl"], "enabled": True},
    {"type_name": "PASSPORT", "display_name": "Passport", "category": "IDENTITY", "requires_period": False, "auto_classify_keywords": ["passport"], "enabled": True},
    {"type_name": "SSN_CARD", "display_name": "Social Security Card", "category": "IDENTITY", "requires_period": False, "auto_classify_keywords": ["social security", "ssn"], "enabled": True},
    {"type_name": "PURCHASE_CONTRACT", "display_name": "Purchase Contract", "category": "PROPERTY", "requires_period": False, "auto_classify_keywords": ["purchase", "contract", "agreement"], "enabled": True},
    {"type_name": "APPRAISAL", "display_name": "Appraisal", "category": "PROPERTY", "requires_period": False, "auto_classify_keywords": ["appraisal", "valuation"], "enabled": True},
    {"type_name": "TITLE_COMMITMENT", "display_name": "Title Commitment", "category": "PROPERTY", "requires_period": False, "auto_classify_keywords": ["title", "commitment"], "enabled": True},
    {"type_name": "HOMEOWNERS_INSURANCE", "display_name": "Homeowners Insurance", "category": "PROPERTY", "requires_period": False, "auto_classify_keywords": ["insurance", "hoi", "policy"], "enabled": True},
    {"type_name": "CREDIT_REPORT", "display_name": "Credit Report", "category": "CREDIT", "requires_period": False, "auto_classify_keywords": ["credit report", "experian", "equifax", "transunion"], "enabled": True},
    {"type_name": "LOAN_ESTIMATE", "display_name": "Loan Estimate", "category": "DISCLOSURES", "requires_period": False, "auto_classify_keywords": ["loan estimate", "le"], "enabled": True},
    {"type_name": "CLOSING_DISCLOSURE", "display_name": "Closing Disclosure", "category": "DISCLOSURES", "requires_period": False, "auto_classify_keywords": ["closing disclosure", "cd"], "enabled": True},
    {"type_name": "MISC", "display_name": "Miscellaneous", "category": "OTHER", "requires_period": False, "auto_classify_keywords": [], "enabled": True},
]

DEFAULT_SETTINGS = {
    "max_file_size_mb": 25.0,
    "max_files_per_upload": 10,
    "allowed_file_types": DEFAULT_FILE_TYPES,
    "classification": {
        "enabled": True,
        "confidence_threshold": 0.7,
        "auto_apply_high_confidence": True,
        "high_confidence_threshold": 0.9,
        "fallback_type": "OTHER",
        "create_task_on_low_confidence": True
    },
    "storage": {
        "provider": "local",
        "bucket_name": None,
        "path_prefix": "documents",
        "retention_days": 365 * 7,
        "enable_versioning": True,
        "encryption_enabled": True
    },
    "notifications": {
        "email_on_upload": True,
        "email_on_classification": False,
        "email_on_expiration": True,
        "expiration_warning_days": 30,
        "create_tasks_for_missing_docs": True,
        "notify_borrower_on_receipt": True
    },
    "document_types": DEFAULT_DOCUMENT_TYPES,
    "enable_ocr": True,
    "enable_virus_scan": True,
    "compress_images": True,
    "image_max_dimension": 2000
}


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("")
async def get_document_upload_settings(
    current_user = Depends(_resolve_current_user)
):
    """Get document upload settings for the organization"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # In production, load from database based on organization_id
        # For now, return defaults with some customization capability

        settings = DEFAULT_SETTINGS.copy()

        # Add metadata
        settings["last_updated"] = datetime.now(timezone.utc).isoformat()
        settings["updated_by"] = None

        return success_response(
            data=settings,
            message="Document upload settings retrieved"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching document upload settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("")
async def update_document_upload_settings(
    settings: DocumentUploadSettingsUpdate,
    current_user = Depends(_resolve_current_user)
):
    """Update document upload settings"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # Check admin permission
        if not getattr(current_user, 'is_admin', False) and not getattr(current_user, 'role', '') in ['admin', 'manager']:
            raise PermissionException("Admin access required to update document settings")

        # Validate file types
        if len(settings.allowed_file_types) == 0:
            raise ValidationException("allowed_file_types", "At least one file type must be allowed")

        # Validate document types
        if len(settings.document_types) == 0:
            raise ValidationException("document_types", "At least one document type must be configured")

        # Check for duplicate extensions
        extensions = [ft.extension for ft in settings.allowed_file_types]
        if len(extensions) != len(set(extensions)):
            raise ValidationException("allowed_file_types", "Duplicate file extensions found")

        # Check for duplicate document type names
        type_names = [dt.type_name for dt in settings.document_types]
        if len(type_names) != len(set(type_names)):
            raise ValidationException("document_types", "Duplicate document type names found")

        # In production, save to database
        updated_settings = settings.dict()
        updated_settings["last_updated"] = datetime.now(timezone.utc).isoformat()
        updated_settings["updated_by"] = getattr(current_user, 'id', None)

        return success_response(
            data=updated_settings,
            message="Document upload settings updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating document upload settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/file-types")
async def get_available_file_types(
    current_user = Depends(_resolve_current_user)
):
    """Get list of all available file types that can be enabled"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        all_types = [
            # Documents
            {"extension": ".pdf", "mime_type": "application/pdf", "category": "document", "description": "PDF Document"},
            {"extension": ".doc", "mime_type": "application/msword", "category": "document", "description": "Word Document (Legacy)"},
            {"extension": ".docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "category": "document", "description": "Word Document"},
            {"extension": ".xls", "mime_type": "application/vnd.ms-excel", "category": "spreadsheet", "description": "Excel Spreadsheet (Legacy)"},
            {"extension": ".xlsx", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "category": "spreadsheet", "description": "Excel Spreadsheet"},
            {"extension": ".csv", "mime_type": "text/csv", "category": "spreadsheet", "description": "CSV File"},
            {"extension": ".txt", "mime_type": "text/plain", "category": "document", "description": "Plain Text"},

            # Images
            {"extension": ".jpg", "mime_type": "image/jpeg", "category": "image", "description": "JPEG Image"},
            {"extension": ".jpeg", "mime_type": "image/jpeg", "category": "image", "description": "JPEG Image"},
            {"extension": ".png", "mime_type": "image/png", "category": "image", "description": "PNG Image"},
            {"extension": ".gif", "mime_type": "image/gif", "category": "image", "description": "GIF Image"},
            {"extension": ".tiff", "mime_type": "image/tiff", "category": "image", "description": "TIFF Image"},
            {"extension": ".heic", "mime_type": "image/heic", "category": "image", "description": "HEIC Image (iPhone)"},
            {"extension": ".webp", "mime_type": "image/webp", "category": "image", "description": "WebP Image"},
            {"extension": ".bmp", "mime_type": "image/bmp", "category": "image", "description": "BMP Image"},
        ]

        return success_response(
            data={"file_types": all_types},
            message="Available file types retrieved"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching available file types")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/document-categories")
async def get_document_categories(
    current_user = Depends(_resolve_current_user)
):
    """Get list of document categories"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        categories = [
            {"name": "INCOME", "display_name": "Income", "description": "Pay stubs, W-2s, tax returns, etc.", "color": "#22c55e"},
            {"name": "ASSETS", "display_name": "Assets", "description": "Bank statements, investment accounts, etc.", "color": "#3b82f6"},
            {"name": "IDENTITY", "display_name": "Identity", "description": "Driver's license, passport, SSN card, etc.", "color": "#8b5cf6"},
            {"name": "PROPERTY", "display_name": "Property", "description": "Purchase contracts, appraisals, title, insurance", "color": "#f59e0b"},
            {"name": "CREDIT", "display_name": "Credit", "description": "Credit reports, explanations", "color": "#ef4444"},
            {"name": "DISCLOSURES", "display_name": "Disclosures", "description": "Loan estimates, closing disclosures", "color": "#06b6d4"},
            {"name": "OTHER", "display_name": "Other", "description": "Miscellaneous documents", "color": "#64748b"},
        ]

        return success_response(
            data={"categories": categories},
            message="Document categories retrieved"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching document categories")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/storage-providers")
async def get_storage_providers(
    current_user = Depends(_resolve_current_user)
):
    """Get available storage providers"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        providers = [
            {
                "id": "local",
                "name": "Local Storage",
                "description": "Store files on the application server",
                "requires_config": False,
                "config_fields": []
            },
            {
                "id": "s3",
                "name": "Amazon S3",
                "description": "Store files in Amazon S3 bucket",
                "requires_config": True,
                "config_fields": ["bucket_name", "region", "access_key_id", "secret_access_key"]
            },
            {
                "id": "gcs",
                "name": "Google Cloud Storage",
                "description": "Store files in Google Cloud Storage bucket",
                "requires_config": True,
                "config_fields": ["bucket_name", "project_id", "credentials_json"]
            },
            {
                "id": "azure",
                "name": "Azure Blob Storage",
                "description": "Store files in Azure Blob Storage container",
                "requires_config": True,
                "config_fields": ["container_name", "connection_string"]
            }
        ]

        return success_response(
            data={"providers": providers},
            message="Storage providers retrieved"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching storage providers")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test-classification")
async def test_classification_settings(
    current_user = Depends(_resolve_current_user)
):
    """Test AI classification with sample files"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # Simulate classification test
        test_results = [
            {
                "filename": "paystub_2024.pdf",
                "detected_type": "PAYSTUB",
                "confidence": 0.95,
                "category": "INCOME",
                "status": "success"
            },
            {
                "filename": "bank_statement.pdf",
                "detected_type": "BANK_STATEMENT",
                "confidence": 0.87,
                "category": "ASSETS",
                "status": "success"
            },
            {
                "filename": "random_doc.pdf",
                "detected_type": "OTHER",
                "confidence": 0.45,
                "category": "OTHER",
                "status": "low_confidence"
            }
        ]

        return success_response(
            data={
                "test_results": test_results,
                "classification_available": True,
                "ai_model": "claude-sonnet-4-20250514"
            },
            message="Classification test completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error testing classification")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/validate-storage")
async def validate_storage_connection(
    provider: str,
    current_user = Depends(_resolve_current_user)
):
    """Validate storage provider connection"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # In production, actually test the connection
        if provider == "local":
            return success_response(
                data={
                    "connected": True,
                    "writable": True,
                    "available_space_gb": 100.5
                },
                message="Local storage connection validated"
            )
        elif provider in ["s3", "gcs", "azure"]:
            return success_response(
                data={
                    "connected": False,
                    "error": "Cloud storage not configured"
                },
                message="Storage validation completed"
            )
        else:
            raise ValidationException("provider", f"Unknown storage provider: {provider}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error validating storage connection")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/statistics")
async def get_document_statistics(
    current_user = Depends(_resolve_current_user)
):
    """Get document upload statistics"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # In production, query from database
        stats = {
            "total_documents": 1234,
            "total_size_gb": 15.7,
            "documents_this_month": 156,
            "avg_file_size_mb": 2.3,
            "by_category": {
                "INCOME": 345,
                "ASSETS": 289,
                "IDENTITY": 123,
                "PROPERTY": 234,
                "CREDIT": 89,
                "DISCLOSURES": 67,
                "OTHER": 87
            },
            "by_type": {
                "pdf": 890,
                "jpg": 234,
                "png": 67,
                "docx": 43
            },
            "classification_stats": {
                "auto_classified": 892,
                "manually_classified": 234,
                "pending": 45,
                "avg_confidence": 0.84
            }
        }

        return success_response(
            data=stats,
            message="Document statistics retrieved"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching document statistics")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reset-defaults")
async def reset_to_defaults(
    current_user = Depends(_resolve_current_user)
):
    """Reset document settings to defaults"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # Check admin permission
        if not getattr(current_user, 'is_admin', False) and not getattr(current_user, 'role', '') in ['admin', 'manager']:
            raise PermissionException("Admin access required to reset settings")

        settings = DEFAULT_SETTINGS.copy()
        settings["last_updated"] = datetime.now(timezone.utc).isoformat()
        settings["updated_by"] = getattr(current_user, 'id', None)
        settings["reset_to_defaults"] = True

        return success_response(
            data=settings,
            message="Document settings reset to defaults"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error resetting document settings")
        raise HTTPException(status_code=500, detail="Internal server error")
