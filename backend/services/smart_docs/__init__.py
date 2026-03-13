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
- SmartDocsLogger / ContextLogger: Structured logging with trace IDs for AI pipeline debugging
- PIIEncryptionService: Column-level encryption for SSNs, account numbers, and OCR text
- SmartDocsPIIFilter: Log filter that redacts PII from Smart Docs logger output
- MalwareScannerService: Multi-backend malware scanning (ClamAV + signature fallback)
- DocumentUploadPipeline: Orchestrated upload flow with validation, scanning, dedup, storage
- BatchOperationsService: Bulk upload/classify/export/reminder/stacking order with progress tracking
- DocumentComparisonService: Document version comparison, cross-source validation, fraud detection
- DocumentSplittingService: AI-powered PDF splitting, page classification, merge, reorder
- ChannelOptimizationService: Data-driven channel selection for borrower document outreach
- CommunicationAnalyticsService: Track and analyze all document-related communications
- AppointmentIntelligenceService: Smart scheduling for document appointments (review, signing, conditions)
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
from services.smart_docs.logging_config import (
    SmartDocsLogger,
    ContextLogger,
    get_smart_docs_logger,
    get_trace_id,
    generate_trace_id,
)
from services.smart_docs.pii_encryption_service import (
    PIIEncryptionService,
    get_pii_encryption_service,
    PIIType,
    PIIDetection,
)
from services.smart_docs.pii_log_filter import (
    SmartDocsPIIFilter,
    install_smart_docs_pii_filter,
)
from services.smart_docs.document_cache_service import (
    DocumentCacheService,
    get_document_cache_service,
)
from services.smart_docs.malware_scanner_service import (
    MalwareScannerService,
    get_malware_scanner,
)
from services.smart_docs.upload_pipeline import (
    DocumentUploadPipeline,
    get_upload_pipeline,
)
from services.smart_docs.service_registry import (
    SmartDocsServiceRegistry,
    OrgAwareService,
)
from services.smart_docs.service_context import (
    get_service_registry,
    create_registry_for_agent,
    ServiceContext,
)
from services.smart_docs.document_version_service import (
    DocumentVersionService,
    get_document_version_service,
)
from services.smart_docs.document_search_service import (
    DocumentSearchService,
    get_document_search_service,
)
from services.smart_docs.batch_operations_service import (
    BatchOperationsService,
    get_batch_operations_service,
    BatchOperationError,
    ConcurrencyLimitExceeded,
)
from services.smart_docs.document_comparison_service import (
    DocumentComparisonService,
    get_document_comparison_service,
)
from services.smart_docs.archive_management_service import (
    ArchiveManagementService,
    get_archive_management_service,
)
from services.smart_docs.document_splitting_service import (
    DocumentSplittingService,
    get_document_splitting_service,
)
from services.smart_docs.channel_optimization_service import (
    ChannelOptimizationService,
    ChannelRecommendation,
    FatigueStatus,
    ChannelAnalytics,
    ensure_tables as ensure_channel_optimization_tables,
)
from services.smart_docs.communication_analytics_service import (
    CommunicationAnalyticsService,
    get_communication_analytics_service,
    DateRange,
    VelocityMetrics,
    EngagementScore,
    ChannelMetrics,
    ProductivityMetrics,
    FunnelData,
    AnomalyAlert,
)
from services.smart_docs.appointment_intelligence_service import (
    AppointmentIntelligenceService,
    get_appointment_intelligence_service,
    DocAppointmentType,
    TimeSlot,
    AppointmentBrief,
    RescheduleResult,
    AppointmentAnalytics,
)
from services.smart_docs.smart_cadence_service import (
    SmartCadenceService,
    get_smart_cadence_service,
)
from services.smart_docs.white_label_service import (
    WhiteLabelService,
    get_white_label_service,
    RenderedEmail as WhiteLabelRenderedEmail,
    ThemeCSS,
    BrandValidationResult,
    ComplianceFooter,
    TEMPLATE_KEYS as WHITE_LABEL_TEMPLATE_KEYS,
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
    # Structured Logging
    "SmartDocsLogger",
    "ContextLogger",
    "get_smart_docs_logger",
    "get_trace_id",
    "generate_trace_id",
    # PII Encryption
    "PIIEncryptionService",
    "get_pii_encryption_service",
    "PIIType",
    "PIIDetection",
    # PII Log Filter
    "SmartDocsPIIFilter",
    "install_smart_docs_pii_filter",
    # Document Cache
    "DocumentCacheService",
    "get_document_cache_service",
    # Malware Scanner
    "MalwareScannerService",
    "get_malware_scanner",
    # Upload Pipeline
    "DocumentUploadPipeline",
    "get_upload_pipeline",
    # Service Registry (multi-tenant service factory)
    "SmartDocsServiceRegistry",
    "OrgAwareService",
    "get_service_registry",
    "create_registry_for_agent",
    "ServiceContext",
    # Document Version Control
    "DocumentVersionService",
    "get_document_version_service",
    # Document Search (full-text search via PostgreSQL tsvector)
    "DocumentSearchService",
    "get_document_search_service",
    # Batch Operations (bulk upload, classify, export, reminder, stacking order)
    "BatchOperationsService",
    "get_batch_operations_service",
    "BatchOperationError",
    "ConcurrencyLimitExceeded",
    # Document Comparison (revision diff, cross-source validation, fraud detection)
    "DocumentComparisonService",
    "get_document_comparison_service",
    # Archive Management (post-closing lifecycle, legal hold, purge, compliance)
    "ArchiveManagementService",
    "get_archive_management_service",
    # Document Splitting (AI PDF splitting, page classification, merge, reorder)
    "DocumentSplittingService",
    "get_document_splitting_service",
    # Channel Optimization (data-driven channel selection for document collection)
    "ChannelOptimizationService",
    "ChannelRecommendation",
    "FatigueStatus",
    "ChannelAnalytics",
    "ensure_channel_optimization_tables",
    # Communication Analytics (velocity, engagement, channel perf, funnel, anomalies)
    "CommunicationAnalyticsService",
    "get_communication_analytics_service",
    "DateRange",
    "VelocityMetrics",
    "EngagementScore",
    "ChannelMetrics",
    "ProductivityMetrics",
    "FunnelData",
    "AnomalyAlert",
    # Appointment Intelligence (doc appointment scheduling, briefs, analytics)
    "AppointmentIntelligenceService",
    "get_appointment_intelligence_service",
    "DocAppointmentType",
    "TimeSlot",
    "AppointmentBrief",
    "RescheduleResult",
    "AppointmentAnalytics",
    # Smart Cadence Engine (multi-channel follow-up cadence orchestration)
    "SmartCadenceService",
    "get_smart_cadence_service",
    # White-Label (per-org branding, email templates, portal theming)
    "WhiteLabelService",
    "get_white_label_service",
    "WhiteLabelRenderedEmail",
    "ThemeCSS",
    "BrandValidationResult",
    "ComplianceFooter",
    "WHITE_LABEL_TEMPLATE_KEYS",
]
