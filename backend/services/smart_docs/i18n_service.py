"""
Smart Docs Internationalization (i18n) Service

Provides multi-language support for all borrower-facing communications and
portal content in the Smart Docs V2 system. Spanish is the primary secondary
language (required by CFPB for LEP borrowers in the US mortgage industry).

Architecture:
- Template-based translations (no runtime machine translation)
- Structured catalogs stored as versioned dictionaries (deployable as DB rows later)
- Merge-field support with {variable} placeholders
- Per-language pluralization rules
- Locale-aware date/currency formatting
- Fallback chain: borrower preference -> org default -> English
- Org-isolated borrower language preferences via DB

Supported languages (initial):
- en (English) - default, 100% coverage
- es (Spanish) - primary secondary, comprehensive coverage

Extensible to:
- zh (Chinese), vi (Vietnamese), ko (Korean) - top LEP mortgage languages
- tl (Tagalog), ar (Arabic), ht (Haitian Creole)

Compliance:
- CFPB Reg B / ECOA: translated disclosures for LEP borrowers
- TRID: dual-language LE/CD cover letters
- HMDA: language preference tracking for fair lending analysis

Usage:
    from services.smart_docs.i18n_service import SmartDocsI18nService

    i18n = SmartDocsI18nService(db=db, org_id=42)
    text = await i18n.translate("doc_request.subject", "es", variables={"doc_type": "W-2"})
    template = await i18n.get_template("document_request_email", "es", variables={...})
    lang = await i18n.get_borrower_language(borrower_id="abc-123")
    coverage = await i18n.get_translation_coverage("es")
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS & ENUMS
# =============================================================================

# ISO 639-1 codes for supported languages
SUPPORTED_LANGUAGE_CODES = ("en", "es", "zh", "vi", "ko", "tl", "ar", "ht")

# Languages with active translation catalogs
ACTIVE_LANGUAGES = ("en", "es")

# Default fallback
DEFAULT_LANGUAGE = "en"

# Current catalog version - increment when translations change
CATALOG_VERSION = "2026.03.1"


class TranslationCategory(str, Enum):
    """Categories of translatable content."""
    DOCUMENT_REQUEST_EMAIL = "doc_request_email"
    SMS = "sms"
    PORTAL_UI = "portal_ui"
    DOCUMENT_TYPES = "document_types"
    STATUS_LABELS = "status_labels"
    ERROR_MESSAGES = "errors"
    NEEDS_LIST = "needs_list"
    UPLOAD_INSTRUCTIONS = "upload_instructions"
    COMPLIANCE_DISCLOSURES = "compliance"
    NOTIFICATIONS = "notifications"


class PluralForm(str, Enum):
    """Plural form categories."""
    ZERO = "zero"
    ONE = "one"
    FEW = "few"
    MANY = "many"
    OTHER = "other"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class LanguageInfo:
    """Information about a supported language."""
    code: str
    name_english: str
    name_native: str
    is_active: bool
    coverage_pct: float = 0.0
    is_rtl: bool = False
    locale_code: str = ""  # e.g. "es-US" for US Spanish

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name_english": self.name_english,
            "name_native": self.name_native,
            "is_active": self.is_active,
            "coverage_pct": self.coverage_pct,
            "is_rtl": self.is_rtl,
            "locale_code": self.locale_code,
        }


@dataclass
class CoverageReport:
    """Translation coverage report for a language."""
    language: str
    total_keys: int
    translated_keys: int
    missing_keys: List[str]
    coverage_pct: float
    by_category: Dict[str, Dict[str, Any]]
    catalog_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "total_keys": self.total_keys,
            "translated_keys": self.translated_keys,
            "missing_keys": self.missing_keys[:50],  # cap for response size
            "missing_count": len(self.missing_keys),
            "coverage_pct": round(self.coverage_pct, 1),
            "by_category": self.by_category,
            "catalog_version": self.catalog_version,
        }


@dataclass
class TranslationEntry:
    """A single translation entry with metadata."""
    key: str
    category: str
    en: str
    es: Optional[str] = None
    zh: Optional[str] = None
    vi: Optional[str] = None
    ko: Optional[str] = None
    tl: Optional[str] = None
    ar: Optional[str] = None
    ht: Optional[str] = None
    notes: str = ""
    compliance_reviewed: bool = False
    plural_forms: Optional[Dict[str, Dict[str, str]]] = None

    def get(self, language: str) -> Optional[str]:
        """Get translation for a language code."""
        return getattr(self, language, None)


# =============================================================================
# LANGUAGE METADATA
# =============================================================================

LANGUAGE_REGISTRY: Dict[str, LanguageInfo] = {
    "en": LanguageInfo(
        code="en", name_english="English", name_native="English",
        is_active=True, coverage_pct=100.0, locale_code="en-US",
    ),
    "es": LanguageInfo(
        code="es", name_english="Spanish", name_native="Espanol",
        is_active=True, coverage_pct=100.0, locale_code="es-US",
    ),
    "zh": LanguageInfo(
        code="zh", name_english="Chinese (Simplified)", name_native="简体中文",
        is_active=False, locale_code="zh-CN",
    ),
    "vi": LanguageInfo(
        code="vi", name_english="Vietnamese", name_native="Tiếng Việt",
        is_active=False, locale_code="vi-VN",
    ),
    "ko": LanguageInfo(
        code="ko", name_english="Korean", name_native="한국어",
        is_active=False, locale_code="ko-KR",
    ),
    "tl": LanguageInfo(
        code="tl", name_english="Tagalog", name_native="Tagalog",
        is_active=False, locale_code="tl-PH",
    ),
    "ar": LanguageInfo(
        code="ar", name_english="Arabic", name_native="العربية",
        is_active=False, is_rtl=True, locale_code="ar-SA",
    ),
    "ht": LanguageInfo(
        code="ht", name_english="Haitian Creole", name_native="Kreyòl Ayisyen",
        is_active=False, locale_code="ht-HT",
    ),
}


# =============================================================================
# PLURALIZATION RULES
# =============================================================================

def _get_plural_form_en(count: int) -> PluralForm:
    """English pluralization: 1 = one, else other."""
    return PluralForm.ONE if count == 1 else PluralForm.OTHER


def _get_plural_form_es(count: int) -> PluralForm:
    """Spanish pluralization: 1 = one, else other."""
    return PluralForm.ONE if count == 1 else PluralForm.OTHER


def _get_plural_form_zh(count: int) -> PluralForm:
    """Chinese: no plural forms, always other."""
    return PluralForm.OTHER


def _get_plural_form_ko(count: int) -> PluralForm:
    """Korean: no plural forms, always other."""
    return PluralForm.OTHER


def _get_plural_form_ar(count: int) -> PluralForm:
    """Arabic: complex pluralization (zero, one, two, few, many, other)."""
    if count == 0:
        return PluralForm.ZERO
    if count == 1:
        return PluralForm.ONE
    if count == 2:
        return PluralForm.FEW
    if 3 <= count % 100 <= 10:
        return PluralForm.FEW
    if 11 <= count % 100 <= 99:
        return PluralForm.MANY
    return PluralForm.OTHER


_PLURAL_RULES = {
    "en": _get_plural_form_en,
    "es": _get_plural_form_es,
    "zh": _get_plural_form_zh,
    "vi": _get_plural_form_en,  # Vietnamese: similar to English
    "ko": _get_plural_form_ko,
    "tl": _get_plural_form_en,  # Tagalog: similar to English
    "ar": _get_plural_form_ar,
    "ht": _get_plural_form_en,  # Haitian Creole: similar to English
}


# =============================================================================
# DATE / CURRENCY FORMATTING PER LOCALE
# =============================================================================

_DATE_FORMATS = {
    "en": "%m/%d/%Y",       # 03/12/2026
    "es": "%d/%m/%Y",       # 12/03/2026
    "zh": "%Y年%m月%d日",    # 2026年03月12日
    "vi": "%d/%m/%Y",       # 12/03/2026
    "ko": "%Y년 %m월 %d일",  # 2026년 03월 12일
    "tl": "%m/%d/%Y",       # 03/12/2026
    "ar": "%d/%m/%Y",       # 12/03/2026
    "ht": "%d/%m/%Y",       # 12/03/2026
}

_CURRENCY_FORMATS = {
    "en": {"symbol": "$", "decimal": ".", "thousands": ",", "position": "before"},
    "es": {"symbol": "$", "decimal": ".", "thousands": ",", "position": "before"},
    "zh": {"symbol": "$", "decimal": ".", "thousands": ",", "position": "before"},
    "vi": {"symbol": "$", "decimal": ".", "thousands": ",", "position": "before"},
    "ko": {"symbol": "$", "decimal": ".", "thousands": ",", "position": "before"},
    "tl": {"symbol": "$", "decimal": ".", "thousands": ",", "position": "before"},
    "ar": {"symbol": "$", "decimal": ".", "thousands": ",", "position": "before"},
    "ht": {"symbol": "$", "decimal": ".", "thousands": ",", "position": "before"},
}


def format_date_localized(dt: Union[datetime, date, None], language: str) -> str:
    """Format a date according to locale conventions."""
    if dt is None:
        return ""
    fmt = _DATE_FORMATS.get(language, _DATE_FORMATS["en"])
    if isinstance(dt, datetime):
        dt = dt.date()
    try:
        return dt.strftime(fmt)
    except ValueError:
        return dt.strftime(_DATE_FORMATS["en"])


def format_currency_localized(
    amount: Union[Decimal, float, int, None],
    language: str,
) -> str:
    """Format a currency amount according to locale conventions."""
    if amount is None:
        return "$0.00"
    fmt = _CURRENCY_FORMATS.get(language, _CURRENCY_FORMATS["en"])
    abs_amount = abs(float(amount))
    # Build formatted number with thousands separator
    whole = int(abs_amount)
    cents = round((abs_amount - whole) * 100)
    whole_str = f"{whole:,}".replace(",", fmt["thousands"])
    result = f"{whole_str}{fmt['decimal']}{cents:02d}"
    if fmt["position"] == "before":
        result = f"{fmt['symbol']}{result}"
    else:
        result = f"{result} {fmt['symbol']}"
    if float(amount) < 0:
        result = f"-{result}"
    return result


# =============================================================================
# TRANSLATION CATALOG
# Comprehensive English/Spanish translations for mortgage document workflows.
# All entries are keyed by dot-notation paths for namespacing.
# =============================================================================

_TRANSLATION_CATALOG: Dict[str, TranslationEntry] = {}


def _reg(key: str, category: str, en: str, es: str, **kwargs) -> None:
    """Register a translation entry in the catalog."""
    _TRANSLATION_CATALOG[key] = TranslationEntry(
        key=key, category=category, en=en, es=es, **kwargs,
    )


# ---------------------------------------------------------------------------
# DOCUMENT TYPE NAMES (21 entries)
# ---------------------------------------------------------------------------
_reg("doc_type.drivers_license", "document_types",
     "Driver's License", "Licencia de conducir")
_reg("doc_type.paystub", "document_types",
     "Pay Stub", "Recibo de pago (talón de cheque)")
_reg("doc_type.w2", "document_types",
     "W-2 Form", "Formulario W-2")
_reg("doc_type.tax_return", "document_types",
     "Tax Return", "Declaración de impuestos")
_reg("doc_type.business_tax_return", "document_types",
     "Business Tax Return", "Declaración de impuestos del negocio")
_reg("doc_type.profit_loss", "document_types",
     "Profit & Loss Statement", "Estado de ganancias y pérdidas")
_reg("doc_type.balance_sheet", "document_types",
     "Balance Sheet", "Balance general")
_reg("doc_type.bank_statement", "document_types",
     "Bank Statement", "Estado de cuenta bancario")
_reg("doc_type.investment_statement", "document_types",
     "Investment Account Statement", "Estado de cuenta de inversiones")
_reg("doc_type.gift_letter", "document_types",
     "Gift Letter", "Carta de regalo (donación)")
_reg("doc_type.loe", "document_types",
     "Letter of Explanation", "Carta de explicación")
_reg("doc_type.lease_agreement", "document_types",
     "Lease Agreement", "Contrato de arrendamiento")
_reg("doc_type.fha_cert", "document_types",
     "FHA Certification", "Certificación de FHA")
_reg("doc_type.va_coe", "document_types",
     "VA Certificate of Eligibility", "Certificado de elegibilidad del VA")
_reg("doc_type.dd214", "document_types",
     "DD-214 (Military Discharge)", "DD-214 (Certificado de baja militar)")
_reg("doc_type.bankruptcy_discharge", "document_types",
     "Bankruptcy Discharge Papers", "Documentos de descarga de bancarrota")
_reg("doc_type.purchase_contract", "document_types",
     "Purchase Contract", "Contrato de compraventa")
_reg("doc_type.appraisal", "document_types",
     "Appraisal Report", "Informe de avalúo")
_reg("doc_type.title_report", "document_types",
     "Title Report", "Informe de título de propiedad")
_reg("doc_type.homeowners_insurance", "document_types",
     "Homeowners Insurance", "Seguro de propietario de vivienda")
_reg("doc_type.other", "document_types",
     "Other Document", "Otro documento")


# ---------------------------------------------------------------------------
# DOCUMENT REQUEST EMAIL TEMPLATES (8 entries)
# ---------------------------------------------------------------------------
_reg("doc_request_email.subject", "doc_request_email",
     "Document Needed: {doc_type}",
     "Documento necesario: {doc_type}")
_reg("doc_request_email.greeting", "doc_request_email",
     "Hi {borrower_first_name},",
     "Hola {borrower_first_name},")
_reg("doc_request_email.body_intro", "doc_request_email",
     "We need the following document to continue processing your loan application:",
     "Necesitamos el siguiente documento para continuar procesando su solicitud de préstamo:")
_reg("doc_request_email.due_date_line", "doc_request_email",
     "Please submit by: {due_date}",
     "Por favor envíelo antes de: {due_date}")
_reg("doc_request_email.cta_button", "doc_request_email",
     "Upload Document",
     "Subir documento")
_reg("doc_request_email.cta_link_text", "doc_request_email",
     "Or use this link to upload: {portal_url}",
     "O use este enlace para subir: {portal_url}")
_reg("doc_request_email.closing", "doc_request_email",
     "If you have any questions, please don't hesitate to reach out to {lo_name}.",
     "Si tiene alguna pregunta, no dude en comunicarse con {lo_name}.")
_reg("doc_request_email.signature", "doc_request_email",
     "Thank you,\n{lo_name}\n{company_name}",
     "Gracias,\n{lo_name}\n{company_name}")

# Reminder variants
_reg("doc_request_email.reminder_subject", "doc_request_email",
     "Reminder: {doc_type} Still Needed",
     "Recordatorio: {doc_type} aún necesario")
_reg("doc_request_email.reminder_body", "doc_request_email",
     "This is a friendly reminder that we still need your {doc_type} to keep your loan on track.",
     "Este es un recordatorio amistoso de que aún necesitamos su {doc_type} para mantener su préstamo en curso.")
_reg("doc_request_email.urgent_subject", "doc_request_email",
     "Urgent: {doc_type} Needed to Avoid Delays",
     "Urgente: {doc_type} necesario para evitar retrasos")
_reg("doc_request_email.urgent_body", "doc_request_email",
     "Your {doc_type} is overdue. To avoid delays in your closing, please upload it as soon as possible.",
     "Su {doc_type} está vencido. Para evitar retrasos en su cierre, por favor súbalo lo antes posible.")


# ---------------------------------------------------------------------------
# SMS MESSAGES (6 entries)
# ---------------------------------------------------------------------------
_reg("sms.doc_request", "sms",
     "Hi {borrower_first_name}, we need your {doc_type} for your loan application. Upload here: {portal_url}",
     "Hola {borrower_first_name}, necesitamos su {doc_type} para su solicitud de préstamo. Súbalo aquí: {portal_url}")
_reg("sms.doc_reminder", "sms",
     "Reminder: Your {doc_type} is still needed. Upload at {portal_url} — {lo_name}",
     "Recordatorio: Su {doc_type} aún es necesario. Súbalo en {portal_url} — {lo_name}")
_reg("sms.doc_received", "sms",
     "We received your {doc_type}. Thank you! We'll review it shortly.",
     "Recibimos su {doc_type}. ¡Gracias! Lo revisaremos pronto.")
_reg("sms.doc_approved", "sms",
     "Great news! Your {doc_type} has been approved.",
     "¡Buenas noticias! Su {doc_type} ha sido aprobado.")
_reg("sms.doc_rejected", "sms",
     "Your {doc_type} needs attention. Please check your email for details and upload a new version.",
     "Su {doc_type} necesita atención. Revise su correo electrónico para más detalles y suba una nueva versión.")
_reg("sms.all_docs_complete", "sms",
     "All your documents have been received and approved. Your loan is moving forward!",
     "Todos sus documentos han sido recibidos y aprobados. ¡Su préstamo avanza!")


# ---------------------------------------------------------------------------
# PORTAL UI STRINGS (12 entries)
# ---------------------------------------------------------------------------
_reg("portal.page_title", "portal_ui",
     "Document Center", "Centro de documentos")
_reg("portal.welcome_message", "portal_ui",
     "Welcome, {borrower_first_name}. Here are the documents needed for your loan.",
     "Bienvenido/a, {borrower_first_name}. Aquí están los documentos necesarios para su préstamo.")
_reg("portal.upload_button", "portal_ui",
     "Choose File to Upload", "Seleccionar archivo para subir")
_reg("portal.drag_drop_hint", "portal_ui",
     "Drag and drop files here, or click to browse",
     "Arrastre y suelte archivos aquí, o haga clic para buscar")
_reg("portal.progress_label", "portal_ui",
     "{completed} of {total} documents submitted",
     "{completed} de {total} documentos enviados")
_reg("portal.status_pending", "portal_ui",
     "Pending", "Pendiente")
_reg("portal.status_in_review", "portal_ui",
     "In Review", "En revisión")
_reg("portal.status_approved", "portal_ui",
     "Approved", "Aprobado")
_reg("portal.status_rejected", "portal_ui",
     "Needs Attention", "Necesita atención")
_reg("portal.status_waived", "portal_ui",
     "Waived", "Exento")
_reg("portal.no_documents", "portal_ui",
     "No documents are required at this time.",
     "No se requieren documentos en este momento.")
_reg("portal.help_text", "portal_ui",
     "Need help? Contact {lo_name} at {lo_email} or {lo_phone}.",
     "¿Necesita ayuda? Comuníquese con {lo_name} al {lo_email} o {lo_phone}.")


# ---------------------------------------------------------------------------
# STATUS LABELS (8 entries)
# ---------------------------------------------------------------------------
_reg("status.open", "status_labels", "Open", "Abierto")
_reg("status.pending_review", "status_labels", "Pending Review", "Pendiente de revisión")
_reg("status.accepted", "status_labels", "Accepted", "Aceptado")
_reg("status.rejected", "status_labels", "Rejected", "Rechazado")
_reg("status.waived", "status_labels", "Waived", "Exento")
_reg("status.expired", "status_labels", "Expired", "Vencido")
_reg("status.uploaded", "status_labels", "Uploaded", "Subido")
_reg("status.not_started", "status_labels", "Not Started", "No iniciado")


# ---------------------------------------------------------------------------
# ERROR MESSAGES (8 entries)
# ---------------------------------------------------------------------------
_reg("error.file_too_large", "errors",
     "File is too large. Maximum size is {max_size_mb} MB.",
     "El archivo es demasiado grande. El tamaño máximo es {max_size_mb} MB.")
_reg("error.invalid_file_type", "errors",
     "This file type is not accepted. Please upload a PDF, JPG, or PNG file.",
     "Este tipo de archivo no es aceptado. Por favor suba un archivo PDF, JPG o PNG.")
_reg("error.upload_failed", "errors",
     "Upload failed. Please try again or contact your loan officer.",
     "La carga falló. Por favor intente de nuevo o comuníquese con su oficial de préstamos.")
_reg("error.session_expired", "errors",
     "Your session has expired. Please log in again.",
     "Su sesión ha expirado. Por favor inicie sesión de nuevo.")
_reg("error.document_not_found", "errors",
     "Document not found.", "Documento no encontrado.")
_reg("error.permission_denied", "errors",
     "You don't have permission to view this document.",
     "No tiene permiso para ver este documento.")
_reg("error.duplicate_document", "errors",
     "This document has already been uploaded.",
     "Este documento ya ha sido subido.")
_reg("error.virus_detected", "errors",
     "This file could not be uploaded for security reasons. Please try a different file.",
     "Este archivo no se pudo subir por razones de seguridad. Por favor intente con un archivo diferente.")


# ---------------------------------------------------------------------------
# NEEDS LIST / UPLOAD INSTRUCTIONS (12 entries)
# ---------------------------------------------------------------------------
_reg("needs_list.section_income", "needs_list",
     "Income Documentation", "Documentación de ingresos")
_reg("needs_list.section_assets", "needs_list",
     "Asset Documentation", "Documentación de activos")
_reg("needs_list.section_property", "needs_list",
     "Property Documentation", "Documentación de la propiedad")
_reg("needs_list.section_identity", "needs_list",
     "Identity Verification", "Verificación de identidad")
_reg("needs_list.section_credit", "needs_list",
     "Credit Documentation", "Documentación de crédito")

_reg("upload_instructions.paystub", "upload_instructions",
     "Please provide your most recent pay stub covering the last 30 days. Include all pages.",
     "Por favor proporcione su recibo de pago más reciente que cubra los últimos 30 días. Incluya todas las páginas.")
_reg("upload_instructions.w2", "upload_instructions",
     "Please provide W-2 forms for the last 2 years from all employers.",
     "Por favor proporcione los formularios W-2 de los últimos 2 años de todos sus empleadores.")
_reg("upload_instructions.tax_return", "upload_instructions",
     "Please provide complete tax returns (all pages, all schedules) for the last 2 years.",
     "Por favor proporcione las declaraciones de impuestos completas (todas las páginas, todos los anexos) de los últimos 2 años.")
_reg("upload_instructions.bank_statement", "upload_instructions",
     "Please provide the most recent 2 months of bank statements for all accounts. Include all pages even if blank.",
     "Por favor proporcione los 2 meses más recientes de estados de cuenta bancarios de todas las cuentas. Incluya todas las páginas aunque estén en blanco.")
_reg("upload_instructions.drivers_license", "upload_instructions",
     "Please provide a clear photo or scan of the front of your valid driver's license.",
     "Por favor proporcione una foto clara o escaneo del frente de su licencia de conducir vigente.")
_reg("upload_instructions.gift_letter", "upload_instructions",
     "The gift letter must include: donor name, relationship, gift amount, property address, and a statement that no repayment is expected.",
     "La carta de regalo debe incluir: nombre del donante, relación, monto del regalo, dirección de la propiedad, y una declaración de que no se espera reembolso.")
_reg("upload_instructions.purchase_contract", "upload_instructions",
     "Please provide the fully executed purchase contract with all addenda and amendments.",
     "Por favor proporcione el contrato de compraventa completamente ejecutado con todas las adendas y enmiendas.")


# ---------------------------------------------------------------------------
# COMPLIANCE / DISCLOSURE TRANSLATIONS (6 entries)
# ---------------------------------------------------------------------------
_reg("compliance.ecoa_notice", "compliance",
     ("The Federal Equal Credit Opportunity Act prohibits creditors from discriminating against "
      "credit applicants on the basis of race, color, religion, national origin, sex, marital status, "
      "or age. The federal agency that administers compliance is the Consumer Financial Protection Bureau."),
     ("La Ley Federal de Igualdad de Oportunidades de Crédito prohíbe a los acreedores discriminar "
      "contra los solicitantes de crédito por motivos de raza, color, religión, origen nacional, sexo, "
      "estado civil o edad. La agencia federal que administra el cumplimiento es la Oficina de Protección "
      "Financiera del Consumidor (CFPB)."),
     compliance_reviewed=True)

_reg("compliance.information_collection", "compliance",
     ("The information you provide will be used to process your mortgage application. "
      "You are not required to provide this information, but failure to do so may delay "
      "or prevent the processing of your application."),
     ("La información que proporcione se utilizará para procesar su solicitud de hipoteca. "
      "No está obligado/a a proporcionar esta información, pero no hacerlo puede retrasar "
      "o impedir el procesamiento de su solicitud."),
     compliance_reviewed=True)

_reg("compliance.privacy_notice", "compliance",
     ("Your personal information is protected under federal privacy laws. "
      "We will not share your information except as permitted by law."),
     ("Su información personal está protegida por las leyes federales de privacidad. "
      "No compartiremos su información excepto según lo permitido por la ley."),
     compliance_reviewed=True)

_reg("compliance.electronic_consent", "compliance",
     ("By uploading documents electronically, you consent to the electronic collection and storage "
      "of your documents for the purpose of processing your mortgage application."),
     ("Al subir documentos electrónicamente, usted consiente la recolección y almacenamiento electrónico "
      "de sus documentos con el fin de procesar su solicitud de hipoteca."),
     compliance_reviewed=True)

_reg("compliance.document_retention", "compliance",
     ("Documents submitted as part of your loan application will be retained in accordance with "
      "federal and state record retention requirements."),
     ("Los documentos enviados como parte de su solicitud de préstamo se conservarán de acuerdo con "
      "los requisitos federales y estatales de retención de registros."),
     compliance_reviewed=True)

_reg("compliance.dual_language_notice", "compliance",
     ("This document is provided in English and Spanish. In the event of a discrepancy, "
      "the English version shall prevail."),
     ("Este documento se proporciona en inglés y español. En caso de discrepancia, "
      "prevalecerá la versión en inglés."),
     compliance_reviewed=True)


# ---------------------------------------------------------------------------
# NOTIFICATION STRINGS (7 entries)
# ---------------------------------------------------------------------------
_reg("notification.doc_received_title", "notifications",
     "Document Received", "Documento recibido")
_reg("notification.doc_received_body", "notifications",
     "Your {doc_type} has been received and is being reviewed.",
     "Su {doc_type} ha sido recibido y está siendo revisado.")
_reg("notification.doc_approved_title", "notifications",
     "Document Approved", "Documento aprobado")
_reg("notification.doc_approved_body", "notifications",
     "Your {doc_type} has been reviewed and approved.",
     "Su {doc_type} ha sido revisado y aprobado.")
_reg("notification.doc_rejected_title", "notifications",
     "Document Needs Attention", "Documento necesita atención")
_reg("notification.doc_rejected_body", "notifications",
     "Your {doc_type} could not be accepted. Reason: {reason}. Please upload a corrected version.",
     "Su {doc_type} no pudo ser aceptado. Razón: {reason}. Por favor suba una versión corregida.")
_reg("notification.all_complete_title", "notifications",
     "All Documents Complete", "Todos los documentos completos")

# Pluralized entry example
_reg("notification.docs_remaining", "notifications",
     "{count} document remaining",
     "{count} documento restante",
     plural_forms={
         "en": {"one": "{count} document remaining", "other": "{count} documents remaining"},
         "es": {"one": "{count} documento restante", "other": "{count} documentos restantes"},
     })


# =============================================================================
# COMPOSITE TEMPLATES
# Templates that combine multiple translation keys into full messages.
# =============================================================================

_COMPOSITE_TEMPLATES: Dict[str, Dict[str, List[str]]] = {
    "document_request_email": {
        "parts": [
            "doc_request_email.greeting",
            "doc_request_email.body_intro",
            "",  # blank line separator
            "doc_request_email.due_date_line",
            "",
            "doc_request_email.cta_link_text",
            "",
            "doc_request_email.closing",
            "",
            "doc_request_email.signature",
        ],
        "subject_key": "doc_request_email.subject",
    },
    "document_reminder_email": {
        "parts": [
            "doc_request_email.greeting",
            "doc_request_email.reminder_body",
            "",
            "doc_request_email.due_date_line",
            "",
            "doc_request_email.cta_link_text",
            "",
            "doc_request_email.closing",
            "",
            "doc_request_email.signature",
        ],
        "subject_key": "doc_request_email.reminder_subject",
    },
    "document_urgent_email": {
        "parts": [
            "doc_request_email.greeting",
            "doc_request_email.urgent_body",
            "",
            "doc_request_email.cta_link_text",
            "",
            "doc_request_email.closing",
            "",
            "doc_request_email.signature",
        ],
        "subject_key": "doc_request_email.urgent_subject",
    },
}


# =============================================================================
# ACCEPT-LANGUAGE PARSER
# =============================================================================

def parse_accept_language(header: str) -> List[str]:
    """Parse HTTP Accept-Language header and return language codes in preference order.

    Examples:
        "es-US,es;q=0.9,en;q=0.8" -> ["es", "en"]
        "en-US,en;q=0.9" -> ["en"]
    """
    if not header:
        return []

    entries: List[Tuple[float, str]] = []
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue
        if ";q=" in part:
            lang_part, q_part = part.split(";q=", 1)
            try:
                quality = float(q_part.strip())
            except ValueError:
                quality = 0.0
        else:
            lang_part = part
            quality = 1.0

        # Extract base language code (e.g., "es-US" -> "es")
        lang_code = lang_part.strip().split("-")[0].lower()
        if lang_code and len(lang_code) == 2:
            entries.append((quality, lang_code))

    # Sort by quality descending, deduplicate
    entries.sort(key=lambda x: x[0], reverse=True)
    seen = set()
    result = []
    for _, code in entries:
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


# =============================================================================
# MAIN SERVICE
# =============================================================================

class SmartDocsI18nService:
    """
    Internationalization service for Smart Docs V2 borrower-facing content.

    Provides template-based translations with merge-field support, pluralization,
    locale-aware formatting, and per-borrower language preferences with org isolation.

    Args:
        db: SQLAlchemy session for language preference storage/retrieval.
        org_id: Organization ID for tenant isolation.
    """

    def __init__(self, db: Session, org_id: int):
        self.db = db
        self.org_id = org_id
        # Snapshot the catalog for this instance so runtime additions
        # in one request don't leak to another.
        self._catalog: Dict[str, TranslationEntry] = _TRANSLATION_CATALOG
        self._composite_templates = _COMPOSITE_TEMPLATES
        self._org_default_language: Optional[str] = None

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    async def translate(
        self,
        key: str,
        language: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        count: Optional[int] = None,
    ) -> str:
        """Translate a single key with optional variable interpolation and pluralization.

        Args:
            key: Dot-notation translation key (e.g., "doc_type.paystub").
            language: Target language code. Falls back through the chain if None.
            variables: Dict of merge-field values to substitute into the template.
            count: If provided and the entry has plural_forms, selects the correct form.

        Returns:
            Translated and interpolated string. Returns the English fallback
            (or the raw key) if no translation is available.
        """
        language = self._resolve_language(language)

        entry = self._catalog.get(key)
        if entry is None:
            logger.warning(
                "Translation key not found: %s (language=%s, org=%s)",
                key, language, self.org_id,
            )
            return self._interpolate(key, variables, language)

        # Handle pluralization
        if count is not None and entry.plural_forms:
            text = self._select_plural_form(entry, language, count)
        else:
            text = entry.get(language)

        # Fallback chain: requested language -> org default -> English -> key
        if text is None and language != DEFAULT_LANGUAGE:
            org_default = await self._get_org_default_language()
            if org_default and org_default != language:
                text = entry.get(org_default)
            if text is None:
                text = entry.get(DEFAULT_LANGUAGE)

        if text is None:
            text = key

        return self._interpolate(text, variables, language)

    async def get_template(
        self,
        template_name: str,
        language: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Render a composite template (multiple keys assembled into a full message).

        Args:
            template_name: Name of the composite template (e.g., "document_request_email").
            language: Target language code.
            variables: Dict of merge-field values.

        Returns:
            Dict with "subject" and "body" keys containing the rendered text.
        """
        language = self._resolve_language(language)
        template_def = self._composite_templates.get(template_name)

        if template_def is None:
            logger.warning(
                "Composite template not found: %s (org=%s)", template_name, self.org_id,
            )
            return {"subject": template_name, "body": ""}

        # Render subject
        subject_key = template_def.get("subject_key", "")
        subject = await self.translate(subject_key, language, variables) if subject_key else ""

        # Render body parts
        parts = []
        for part_key in template_def.get("parts", []):
            if not part_key:
                parts.append("")  # blank line separator
            else:
                translated = await self.translate(part_key, language, variables)
                parts.append(translated)

        body = "\n".join(parts)

        return {"subject": subject, "body": body}

    async def get_borrower_language(
        self,
        borrower_id: str,
    ) -> str:
        """Get the stored language preference for a borrower within this org.

        Falls back to org default, then English, if no preference is stored.

        Args:
            borrower_id: Borrower profile ID (UUID string).

        Returns:
            ISO 639-1 language code.
        """
        try:
            result = self.db.execute(
                text("""
                    SELECT language_preference
                    FROM borrower_language_preferences
                    WHERE organization_id = :org_id
                      AND borrower_id = :borrower_id
                """),
                {"org_id": self.org_id, "borrower_id": str(borrower_id)},
            )
            row = result.fetchone()
            if row and row[0]:
                lang = row[0]
                if lang in SUPPORTED_LANGUAGE_CODES:
                    return lang
        except Exception as e:
            # Table may not exist yet; fall back gracefully
            logger.debug(
                "Could not read borrower language preference (table may not exist): %s", e,
            )

        # Fall back to org default, then English
        org_default = await self._get_org_default_language()
        return org_default or DEFAULT_LANGUAGE

    async def set_borrower_language(
        self,
        borrower_id: str,
        language: str,
    ) -> None:
        """Store or update the language preference for a borrower.

        Args:
            borrower_id: Borrower profile ID (UUID string).
            language: ISO 639-1 language code.

        Raises:
            ValueError: If language code is not in SUPPORTED_LANGUAGE_CODES.
        """
        if language not in SUPPORTED_LANGUAGE_CODES:
            raise ValueError(
                f"Unsupported language code: {language}. "
                f"Supported: {', '.join(SUPPORTED_LANGUAGE_CODES)}"
            )

        try:
            self._ensure_preference_table()

            # Upsert via raw SQL for broad DB compatibility
            self.db.execute(
                text("""
                    INSERT INTO borrower_language_preferences
                        (organization_id, borrower_id, language_preference, updated_at)
                    VALUES (:org_id, :borrower_id, :language, NOW())
                    ON CONFLICT (organization_id, borrower_id)
                    DO UPDATE SET
                        language_preference = :language,
                        updated_at = NOW()
                """),
                {
                    "org_id": self.org_id,
                    "borrower_id": str(borrower_id),
                    "language": language,
                },
            )
            self.db.flush()
            logger.info(
                "Set borrower %s language to %s (org=%s)",
                borrower_id, language, self.org_id,
            )
        except Exception as e:
            logger.error(
                "Failed to set borrower language preference: %s", e,
            )
            raise

    async def detect_language_from_header(
        self,
        accept_language_header: str,
    ) -> str:
        """Detect best supported language from HTTP Accept-Language header.

        Args:
            accept_language_header: Raw Accept-Language header value.

        Returns:
            Best matching supported language code, or org default / English.
        """
        preferred = parse_accept_language(accept_language_header)
        for lang in preferred:
            if lang in ACTIVE_LANGUAGES:
                return lang

        org_default = await self._get_org_default_language()
        return org_default or DEFAULT_LANGUAGE

    async def get_translation_coverage(self, language: str) -> CoverageReport:
        """Calculate translation coverage for a given language.

        Args:
            language: ISO 639-1 language code to analyze.

        Returns:
            CoverageReport with per-category breakdown and list of missing keys.
        """
        total_keys = len(self._catalog)
        translated = 0
        missing: List[str] = []
        category_stats: Dict[str, Dict[str, int]] = {}

        for key, entry in self._catalog.items():
            cat = entry.category
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "translated": 0}
            category_stats[cat]["total"] += 1

            value = entry.get(language)
            if value is not None:
                translated += 1
                category_stats[cat]["translated"] += 1
            else:
                missing.append(key)

        coverage_pct = (translated / total_keys * 100) if total_keys > 0 else 0.0

        by_category = {}
        for cat, stats in category_stats.items():
            cat_pct = (stats["translated"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
            by_category[cat] = {
                "total": stats["total"],
                "translated": stats["translated"],
                "coverage_pct": round(cat_pct, 1),
            }

        return CoverageReport(
            language=language,
            total_keys=total_keys,
            translated_keys=translated,
            missing_keys=missing,
            coverage_pct=coverage_pct,
            by_category=by_category,
            catalog_version=CATALOG_VERSION,
        )

    def get_supported_languages(self) -> List[LanguageInfo]:
        """Return list of all supported languages with their metadata.

        Returns:
            List of LanguageInfo objects, active languages first.
        """
        languages = list(LANGUAGE_REGISTRY.values())
        # Calculate coverage for each
        for lang_info in languages:
            total = len(self._catalog)
            if total == 0:
                lang_info.coverage_pct = 0.0
                continue
            translated = sum(
                1 for entry in self._catalog.values()
                if entry.get(lang_info.code) is not None
            )
            lang_info.coverage_pct = round(translated / total * 100, 1)

        # Sort: active first, then by coverage descending
        languages.sort(key=lambda x: (-x.is_active, -x.coverage_pct))
        return languages

    async def translate_document_type(
        self,
        doc_type_code: str,
        language: Optional[str] = None,
    ) -> str:
        """Translate a DocType enum value to a human-readable localized name.

        Args:
            doc_type_code: DocType enum value (e.g., "PAYSTUB", "W2").
            language: Target language.

        Returns:
            Localized document type name.
        """
        key = f"doc_type.{doc_type_code.lower()}"
        return await self.translate(key, language)

    async def translate_status(
        self,
        status_code: str,
        language: Optional[str] = None,
    ) -> str:
        """Translate a RequestStatus enum value to a localized label.

        Args:
            status_code: Status code (e.g., "OPEN", "PENDING_REVIEW").
            language: Target language.

        Returns:
            Localized status label.
        """
        key = f"status.{status_code.lower()}"
        return await self.translate(key, language)

    async def get_upload_instructions(
        self,
        doc_type_code: str,
        language: Optional[str] = None,
    ) -> str:
        """Get localized upload instructions for a specific document type.

        Args:
            doc_type_code: DocType enum value (e.g., "PAYSTUB").
            language: Target language.

        Returns:
            Localized upload instructions string. Returns empty string if
            no specific instructions exist for this doc type.
        """
        key = f"upload_instructions.{doc_type_code.lower()}"
        result = await self.translate(key, language)
        # If translate returned the raw key, no instructions exist
        return "" if result == key else result

    async def get_compliance_text(
        self,
        disclosure_key: str,
        language: Optional[str] = None,
    ) -> str:
        """Get a compliance disclosure text in the requested language.

        Args:
            disclosure_key: Short key (e.g., "ecoa_notice", "privacy_notice").
            language: Target language.

        Returns:
            Localized compliance text.
        """
        full_key = f"compliance.{disclosure_key}"
        return await self.translate(full_key, language)

    async def get_dual_language_text(
        self,
        key: str,
        primary_language: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Get text in both English and the borrower's language for dual-language documents.

        Args:
            key: Translation key.
            primary_language: Borrower's preferred language.
            variables: Merge-field values.

        Returns:
            Dict with "en" and the primary language code as keys.
        """
        en_text = await self.translate(key, "en", variables)
        result = {"en": en_text}

        if primary_language != "en":
            localized_text = await self.translate(key, primary_language, variables)
            result[primary_language] = localized_text

        return result

    def format_date(
        self,
        dt: Union[datetime, date, None],
        language: Optional[str] = None,
    ) -> str:
        """Format a date according to the locale conventions.

        Args:
            dt: Date or datetime to format.
            language: Target language for date formatting.

        Returns:
            Locale-formatted date string.
        """
        language = self._resolve_language(language)
        return format_date_localized(dt, language)

    def format_currency(
        self,
        amount: Union[Decimal, float, int, None],
        language: Optional[str] = None,
    ) -> str:
        """Format a currency amount according to locale conventions.

        Args:
            amount: Dollar amount to format.
            language: Target language for currency formatting.

        Returns:
            Locale-formatted currency string (always USD).
        """
        language = self._resolve_language(language)
        return format_currency_localized(amount, language)

    def get_catalog_version(self) -> str:
        """Return the current translation catalog version string."""
        return CATALOG_VERSION

    def get_catalog_keys(self, category: Optional[str] = None) -> List[str]:
        """Return all translation keys, optionally filtered by category.

        Args:
            category: If provided, only return keys in this category.

        Returns:
            Sorted list of translation keys.
        """
        if category:
            return sorted(
                k for k, v in self._catalog.items()
                if v.category == category
            )
        return sorted(self._catalog.keys())

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _resolve_language(self, language: Optional[str]) -> str:
        """Resolve language to a valid code, defaulting to English."""
        if language and language in SUPPORTED_LANGUAGE_CODES:
            return language
        return DEFAULT_LANGUAGE

    def _interpolate(
        self,
        template: str,
        variables: Optional[Dict[str, Any]],
        language: str,
    ) -> str:
        """Substitute {variable} placeholders in a template string.

        Handles nested formatting: date and currency values are automatically
        formatted according to locale if they are date/Decimal types.
        """
        if not variables:
            return template

        formatted_vars = {}
        for var_key, var_value in variables.items():
            if isinstance(var_value, (datetime, date)):
                formatted_vars[var_key] = format_date_localized(var_value, language)
            elif isinstance(var_value, Decimal):
                formatted_vars[var_key] = format_currency_localized(var_value, language)
            else:
                formatted_vars[var_key] = str(var_value) if var_value is not None else ""

        try:
            return template.format(**formatted_vars)
        except KeyError as e:
            logger.debug(
                "Missing variable %s in template (language=%s): %s",
                e, language, template[:80],
            )
            # Partial substitution: replace what we can, leave the rest
            result = template
            for var_key, var_value in formatted_vars.items():
                result = result.replace(f"{{{var_key}}}", var_value)
            return result

    def _select_plural_form(
        self,
        entry: TranslationEntry,
        language: str,
        count: int,
    ) -> Optional[str]:
        """Select the correct plural form for a translation entry."""
        if not entry.plural_forms:
            return entry.get(language)

        lang_forms = entry.plural_forms.get(language)
        if not lang_forms:
            # Fall back to English plural forms
            lang_forms = entry.plural_forms.get("en")
        if not lang_forms:
            return entry.get(language)

        # Get the plural rule for this language
        plural_fn = _PLURAL_RULES.get(language, _get_plural_form_en)
        form = plural_fn(count)

        # Try exact form, then "other" as fallback
        text = lang_forms.get(form.value)
        if text is None:
            text = lang_forms.get(PluralForm.OTHER.value)
        return text

    async def _get_org_default_language(self) -> Optional[str]:
        """Get the organization's default language, cached per-instance."""
        if self._org_default_language is not None:
            return self._org_default_language

        try:
            result = self.db.execute(
                text("""
                    SELECT default_language
                    FROM organization_language_settings
                    WHERE organization_id = :org_id
                """),
                {"org_id": self.org_id},
            )
            row = result.fetchone()
            if row and row[0]:
                self._org_default_language = row[0]
            else:
                self._org_default_language = DEFAULT_LANGUAGE
        except Exception as _exc:  # noqa: BLE001
            # Table may not exist; fall back to English
            logger.exception("unhandled exception")
            self._org_default_language = DEFAULT_LANGUAGE

        return self._org_default_language

    def _ensure_preference_table(self) -> None:
        """Create the borrower_language_preferences table if it does not exist.

        Uses checkfirst=True semantics via IF NOT EXISTS.
        """
        try:
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS borrower_language_preferences (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    borrower_id VARCHAR(36) NOT NULL,
                    language_preference VARCHAR(10) NOT NULL DEFAULT 'en',
                    detected_from VARCHAR(50),
                    set_by VARCHAR(20) DEFAULT 'system',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE (organization_id, borrower_id)
                )
            """))
            self.db.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_blp_org_borrower
                ON borrower_language_preferences (organization_id, borrower_id)
            """))
            self.db.flush()
        except Exception as e:
            logger.debug("borrower_language_preferences table check: %s", e)
