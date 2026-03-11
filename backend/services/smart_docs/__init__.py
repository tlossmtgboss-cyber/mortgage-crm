"""
Smart Document Collection Services

Intelligent document collection, validation, and management system for mortgage applications.

Components:
- NeedsListGenerator: Generate document requirements from templates
- ScreenshotDetector: Multi-layer screenshot detection
- DateExtractor: OCR-based date extraction from documents
- FreshnessValidator: Validate document freshness against policy
- AutoRenewalScheduler: Schedule auto-renewal requests for expiring documents
- DocumentReviewPipeline: Orchestrate document processing workflow
- SmartDocsS3Service: S3 storage for document files
- SmartDocsNotificationService: Email notifications for document requests
- DocumentValidationEngine: Rule-based document validation (file security, freshness, completeness, PII)
- PDFGenerationService: PDF generation, merging, watermarking, and signature overlay
- FollowupAutomationService: Automated multi-step follow-up campaigns
- ESignFieldDetectorService: Auto-detect e-signature field placements on documents
- NotificationTemplates: Comprehensive HTML email templates for all Smart Docs events
- DocumentOCRService: Multi-format OCR and text extraction with mortgage field parsing
"""

from services.smart_docs.needs_list_generator import NeedsListGenerator
from services.smart_docs.screenshot_detector import ScreenshotDetector
from services.smart_docs.date_extractor import DateExtractor
from services.smart_docs.freshness_validator import FreshnessValidator
from services.smart_docs.auto_renewal_scheduler import AutoRenewalScheduler
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
from services.smart_docs.s3_storage_service import SmartDocsS3Service, get_smart_docs_s3_service
from services.smart_docs.notification_service import SmartDocsNotificationService
from services.smart_docs.document_validation_engine import DocumentValidationEngine, get_document_validation_engine
from services.smart_docs.pdf_generation_service import PDFGenerationService, get_pdf_generation_service
from services.smart_docs.followup_automation_service import (
    FollowupAutomationService,
    get_followup_automation_service,
)
from services.smart_docs.esign_field_detector_service import (
    ESignFieldDetectorService,
    get_esign_field_detector_service,
)
from services.smart_docs.notification_templates import (
    render_template as render_notification_template,
    send_notification as send_smart_docs_notification,
    get_available_templates,
    RenderedTemplate,
)
from services.smart_docs.document_ocr_service import (
    DocumentOCRService,
    get_document_ocr_service,
)

__all__ = [
    "NeedsListGenerator",
    "ScreenshotDetector",
    "DateExtractor",
    "FreshnessValidator",
    "AutoRenewalScheduler",
    "DocumentReviewPipeline",
    "SmartDocsS3Service",
    "get_smart_docs_s3_service",
    "SmartDocsNotificationService",
    "DocumentValidationEngine",
    "get_document_validation_engine",
    "PDFGenerationService",
    "get_pdf_generation_service",
    "FollowupAutomationService",
    "get_followup_automation_service",
    "ESignFieldDetectorService",
    "get_esign_field_detector_service",
    "render_notification_template",
    "send_smart_docs_notification",
    "get_available_templates",
    "RenderedTemplate",
    "DocumentOCRService",
    "get_document_ocr_service",
]
