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
"""

from services.smart_docs.needs_list_generator import NeedsListGenerator
from services.smart_docs.screenshot_detector import ScreenshotDetector
from services.smart_docs.date_extractor import DateExtractor
from services.smart_docs.freshness_validator import FreshnessValidator
from services.smart_docs.auto_renewal_scheduler import AutoRenewalScheduler
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline

__all__ = [
    "NeedsListGenerator",
    "ScreenshotDetector",
    "DateExtractor",
    "FreshnessValidator",
    "AutoRenewalScheduler",
    "DocumentReviewPipeline",
]
