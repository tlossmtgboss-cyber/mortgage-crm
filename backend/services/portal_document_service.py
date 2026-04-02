"""
Portal Document Service - Document management for the Perennia Portal.

Handles document uploads, AI extraction, property cost tracking,
and document status management for borrower portal.
"""

import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from sqlalchemy.exc import SQLAlchemyError
from models.portal_models import (
    DocumentType, DocumentStatus,
    PortalDocument, DocumentExtraction, PropertyCosts,
    PortalLoan, LoanActivityLog
)

logger = logging.getLogger(__name__)


# Document type configurations
DOCUMENT_CONFIGS = {
    DocumentType.PAYSTUB: {
        "display_name": "Pay Stub",
        "extraction_fields": ["employer_name", "gross_pay", "net_pay", "pay_period", "ytd_gross"],
        "required_for_stages": ["PREAPPROVAL", "PROCESSING"],
    },
    DocumentType.W2: {
        "display_name": "W-2 Form",
        "extraction_fields": ["employer_name", "wages", "federal_tax", "state_tax", "year"],
        "required_for_stages": ["PREAPPROVAL", "PROCESSING"],
    },
    DocumentType.TAX_RETURN: {
        "display_name": "Tax Return",
        "extraction_fields": ["tax_year", "filing_status", "adjusted_gross_income", "total_tax"],
        "required_for_stages": ["PREAPPROVAL", "PROCESSING"],
    },
    DocumentType.BANK_STATEMENT: {
        "display_name": "Bank Statement",
        "extraction_fields": ["account_type", "account_number", "ending_balance", "statement_period"],
        "required_for_stages": ["PREAPPROVAL", "PROCESSING"],
    },
    DocumentType.DRIVERS_LICENSE: {
        "display_name": "Driver's License",
        "extraction_fields": ["full_name", "address", "license_number", "expiration_date"],
        "required_for_stages": ["PREAPPROVAL"],
    },
    DocumentType.PURCHASE_CONTRACT: {
        "display_name": "Purchase Contract",
        "extraction_fields": ["purchase_price", "seller_name", "property_address", "closing_date", "earnest_money"],
        "required_for_stages": ["UNDER_CONTRACT"],
    },
    DocumentType.APPRAISAL: {
        "display_name": "Appraisal Report",
        "extraction_fields": ["appraised_value", "property_type", "square_footage", "year_built", "appraiser_name"],
        "required_for_stages": ["PROCESSING"],
    },
    DocumentType.TITLE_REPORT: {
        "display_name": "Title Report",
        "extraction_fields": ["property_address", "legal_description", "liens", "title_company"],
        "required_for_stages": ["PROCESSING", "CLEAR_TO_CLOSE"],
    },
    DocumentType.HOMEOWNERS_INSURANCE: {
        "display_name": "Homeowners Insurance",
        "extraction_fields": ["insurance_company", "policy_number", "coverage_amount", "annual_premium", "effective_date"],
        "required_for_stages": ["CLEAR_TO_CLOSE"],
    },
    DocumentType.CLOSING_DISCLOSURE: {
        "display_name": "Closing Disclosure",
        "extraction_fields": ["loan_amount", "interest_rate", "monthly_payment", "cash_to_close", "closing_costs"],
        "required_for_stages": ["CLEAR_TO_CLOSE"],
    },
}


class PortalDocumentService:
    """Service for managing portal documents."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # DOCUMENT UPLOAD & MANAGEMENT
    # =========================================================================

    def upload_document(
        self,
        loan_id: int,
        document_type: DocumentType,
        file_name: str,
        file_path: str,
        file_size: int,
        mime_type: str,
        uploaded_by: Optional[str] = None,
        is_borrower_upload: bool = False,
    ) -> Dict[str, Any]:
        """Register a document upload."""
        document = PortalDocument(
            loan_id=loan_id,
            document_type=document_type,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            status=DocumentStatus.PENDING,
            uploaded_by=uploaded_by,
            is_borrower_upload=is_borrower_upload,
            is_visible_to_borrower=True,
        )
        self.db.add(document)

        # Log activity
        activity = LoanActivityLog(
            loan_id=loan_id,
            activity_type="document_uploaded",
            description=f"{DOCUMENT_CONFIGS.get(document_type, {}).get('display_name', document_type.value)} uploaded",
            metadata={
                "document_type": document_type.value,
                "file_name": file_name,
                "uploaded_by": uploaded_by,
            },
            actor=uploaded_by,
            is_visible_to_borrower=True,
        )
        self.db.add(activity)

        self.db.commit()
        self.db.refresh(document)

        logger.info(f"Document uploaded for loan {loan_id}: {document_type.value}")

        return {
            "success": True,
            "document_id": document.id,
            "document_type": document_type.value,
            "status": document.status.value,
        }

    def get_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Get document details."""
        doc = self.db.query(PortalDocument).filter(
            PortalDocument.id == document_id
        ).first()

        if not doc:
            return None

        config = DOCUMENT_CONFIGS.get(doc.document_type, {})

        return {
            "id": doc.id,
            "loan_id": doc.loan_id,
            "document_type": doc.document_type.value,
            "display_name": config.get("display_name", doc.document_type.value),
            "file_name": doc.file_name,
            "file_path": doc.file_path,
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "status": doc.status.value,
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            "uploaded_by": doc.uploaded_by,
            "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
            "reviewed_by": doc.reviewed_by,
            "rejection_reason": doc.rejection_reason,
            "has_extraction": doc.extraction is not None,
        }

    def get_loan_documents(
        self,
        loan_id: int,
        document_type: Optional[DocumentType] = None,
        status: Optional[DocumentStatus] = None,
        borrower_view: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get all documents for a loan."""
        query = self.db.query(PortalDocument).filter(
            PortalDocument.loan_id == loan_id
        )

        if document_type:
            query = query.filter(PortalDocument.document_type == document_type)

        if status:
            query = query.filter(PortalDocument.status == status)

        if borrower_view:
            query = query.filter(PortalDocument.is_visible_to_borrower == True)

        documents = query.order_by(PortalDocument.uploaded_at.desc()).all()

        return [
            {
                "id": doc.id,
                "document_type": doc.document_type.value,
                "display_name": DOCUMENT_CONFIGS.get(doc.document_type, {}).get("display_name", doc.document_type.value),
                "file_name": doc.file_name,
                "file_size": doc.file_size,
                "status": doc.status.value,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "is_borrower_upload": doc.is_borrower_upload,
            }
            for doc in documents
        ]

    def update_document_status(
        self,
        document_id: int,
        status: DocumentStatus,
        reviewed_by: Optional[str] = None,
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update document status."""
        doc = self.db.query(PortalDocument).filter(
            PortalDocument.id == document_id
        ).first()

        if not doc:
            return {"success": False, "error": "Document not found"}

        old_status = doc.status
        doc.status = status

        if status in [DocumentStatus.APPROVED, DocumentStatus.REJECTED]:
            doc.reviewed_at = datetime.now(timezone.utc)
            doc.reviewed_by = reviewed_by

        if status == DocumentStatus.REJECTED and rejection_reason:
            doc.rejection_reason = rejection_reason

        # Log activity
        activity = LoanActivityLog(
            loan_id=doc.loan_id,
            activity_type="document_status_changed",
            description=f"{doc.file_name} {status.value}",
            metadata={
                "document_id": document_id,
                "old_status": old_status.value,
                "new_status": status.value,
                "rejection_reason": rejection_reason,
            },
            actor=reviewed_by,
            is_visible_to_borrower=True,
        )
        self.db.add(activity)

        self.db.commit()

        return {
            "success": True,
            "document_id": document_id,
            "old_status": old_status.value,
            "new_status": status.value,
        }

    def delete_document(self, document_id: int) -> Dict[str, Any]:
        """Delete a document."""
        doc = self.db.query(PortalDocument).filter(
            PortalDocument.id == document_id
        ).first()

        if not doc:
            return {"success": False, "error": "Document not found"}

        # Delete extraction if exists
        if doc.extraction:
            self.db.delete(doc.extraction)

        self.db.delete(doc)
        self.db.commit()

        return {"success": True}

    # =========================================================================
    # DOCUMENT EXTRACTION (AI)
    # =========================================================================

    def extract_document_data(
        self,
        document_id: int,
        extracted_data: Dict[str, Any],
        confidence_score: float,
        extracted_by: str = "claude_ai",
        raw_response: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Store AI extraction results for a document."""
        doc = self.db.query(PortalDocument).filter(
            PortalDocument.id == document_id
        ).first()

        if not doc:
            return {"success": False, "error": "Document not found"}

        # Check for existing extraction
        extraction = self.db.query(DocumentExtraction).filter(
            DocumentExtraction.document_id == document_id
        ).first()

        if extraction:
            extraction.extracted_data = extracted_data
            extraction.confidence_score = confidence_score
            extraction.extracted_by = extracted_by
            extraction.raw_response = raw_response
            extraction.is_verified = False
        else:
            extraction = DocumentExtraction(
                document_id=document_id,
                extracted_data=extracted_data,
                confidence_score=confidence_score,
                extracted_by=extracted_by,
                raw_response=raw_response,
                is_verified=False,
            )
            self.db.add(extraction)

        # Update document status
        doc.status = DocumentStatus.PROCESSING

        self.db.commit()
        self.db.refresh(extraction)

        logger.info(f"Extraction completed for document {document_id}, confidence: {confidence_score}")

        return {
            "success": True,
            "extraction_id": extraction.id,
            "extracted_fields": list(extracted_data.keys()),
            "confidence_score": confidence_score,
        }

    def get_extraction(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Get extraction data for a document."""
        extraction = self.db.query(DocumentExtraction).filter(
            DocumentExtraction.document_id == document_id
        ).first()

        if not extraction:
            return None

        return {
            "id": extraction.id,
            "extracted_data": extraction.extracted_data,
            "confidence_score": extraction.confidence_score,
            "extracted_by": extraction.extracted_by,
            "extracted_at": extraction.extracted_at.isoformat() if extraction.extracted_at else None,
            "is_verified": extraction.is_verified,
            "verified_by": extraction.verified_by,
        }

    def verify_extraction(
        self,
        extraction_id: int,
        verified_by: str,
        corrections: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Mark extraction as verified, optionally with corrections."""
        extraction = self.db.query(DocumentExtraction).filter(
            DocumentExtraction.id == extraction_id
        ).first()

        if not extraction:
            return {"success": False, "error": "Extraction not found"}

        if corrections:
            extraction.extracted_data = {**extraction.extracted_data, **corrections}

        extraction.is_verified = True
        extraction.verified_by = verified_by
        extraction.verified_at = datetime.now(timezone.utc)

        # Update document status to approved
        extraction.document.status = DocumentStatus.APPROVED

        self.db.commit()

        return {"success": True, "extraction_id": extraction_id}

    # =========================================================================
    # PROPERTY COSTS
    # =========================================================================

    def set_property_costs(
        self,
        loan_id: int,
        monthly_property_tax: Optional[Decimal] = None,
        monthly_hoi: Optional[Decimal] = None,
        monthly_hoa: Optional[Decimal] = None,
        monthly_pmi: Optional[Decimal] = None,
        monthly_flood_insurance: Optional[Decimal] = None,
        monthly_other: Optional[Decimal] = None,
        data_source: str = "manual",
    ) -> Dict[str, Any]:
        """Set or update property costs for a loan."""
        costs = self.db.query(PropertyCosts).filter(
            PropertyCosts.loan_id == loan_id
        ).first()

        if costs:
            if monthly_property_tax is not None:
                costs.monthly_property_tax = monthly_property_tax
            if monthly_hoi is not None:
                costs.monthly_hoi = monthly_hoi
            if monthly_hoa is not None:
                costs.monthly_hoa = monthly_hoa
            if monthly_pmi is not None:
                costs.monthly_pmi = monthly_pmi
            if monthly_flood_insurance is not None:
                costs.monthly_flood_insurance = monthly_flood_insurance
            if monthly_other is not None:
                costs.monthly_other = monthly_other
            costs.data_source = data_source
            costs.last_updated = datetime.now(timezone.utc)
        else:
            costs = PropertyCosts(
                loan_id=loan_id,
                monthly_property_tax=monthly_property_tax or Decimal("0"),
                monthly_hoi=monthly_hoi or Decimal("0"),
                monthly_hoa=monthly_hoa or Decimal("0"),
                monthly_pmi=monthly_pmi or Decimal("0"),
                monthly_flood_insurance=monthly_flood_insurance or Decimal("0"),
                monthly_other=monthly_other or Decimal("0"),
                data_source=data_source,
            )
            self.db.add(costs)

        self.db.commit()
        self.db.refresh(costs)

        return {
            "success": True,
            "costs_id": costs.id,
            "total_monthly": float(costs.total_monthly_costs),
        }

    def get_property_costs(self, loan_id: int) -> Optional[Dict[str, Any]]:
        """Get property costs for a loan."""
        costs = self.db.query(PropertyCosts).filter(
            PropertyCosts.loan_id == loan_id
        ).first()

        if not costs:
            return None

        return {
            "id": costs.id,
            "monthly_property_tax": float(costs.monthly_property_tax or 0),
            "monthly_hoi": float(costs.monthly_hoi or 0),
            "monthly_hoa": float(costs.monthly_hoa or 0),
            "monthly_pmi": float(costs.monthly_pmi or 0),
            "monthly_flood_insurance": float(costs.monthly_flood_insurance or 0),
            "monthly_other": float(costs.monthly_other or 0),
            "total_monthly": float(costs.total_monthly_costs),
            "annual_total": float(costs.total_monthly_costs * 12),
            "data_source": costs.data_source,
            "last_updated": costs.last_updated.isoformat() if costs.last_updated else None,
        }

    def extract_costs_from_documents(self, loan_id: int) -> Dict[str, Any]:
        """Extract property costs from uploaded documents."""
        updates = {}

        # Try to extract from HOI document
        hoi_doc = self.db.query(PortalDocument).filter(
            and_(
                PortalDocument.loan_id == loan_id,
                PortalDocument.document_type == DocumentType.HOMEOWNERS_INSURANCE,
                PortalDocument.status == DocumentStatus.APPROVED
            )
        ).first()

        if hoi_doc and hoi_doc.extraction:
            annual_premium = hoi_doc.extraction.extracted_data.get("annual_premium")
            if annual_premium:
                updates["monthly_hoi"] = Decimal(str(annual_premium)) / 12

        # Try to extract from Closing Disclosure
        cd_doc = self.db.query(PortalDocument).filter(
            and_(
                PortalDocument.loan_id == loan_id,
                PortalDocument.document_type == DocumentType.CLOSING_DISCLOSURE,
                PortalDocument.status == DocumentStatus.APPROVED
            )
        ).first()

        if cd_doc and cd_doc.extraction:
            extracted = cd_doc.extraction.extracted_data
            # CD typically has escrow breakdown
            if "monthly_taxes" in extracted:
                updates["monthly_property_tax"] = Decimal(str(extracted["monthly_taxes"]))
            if "monthly_insurance" in extracted:
                updates["monthly_hoi"] = Decimal(str(extracted["monthly_insurance"]))

        if updates:
            return self.set_property_costs(loan_id, data_source="extracted", **updates)

        return {"success": False, "message": "No cost data found in documents"}

    # =========================================================================
    # DOCUMENT CHECKLIST
    # =========================================================================

    def get_document_checklist(
        self,
        loan_id: int,
        lifecycle_stage: str,
    ) -> List[Dict[str, Any]]:
        """Get document checklist for current lifecycle stage."""
        checklist = []

        # Get existing documents for loan
        existing_docs = self.db.query(PortalDocument).filter(
            PortalDocument.loan_id == loan_id
        ).all()

        existing_by_type = {}
        for doc in existing_docs:
            if doc.document_type not in existing_by_type:
                existing_by_type[doc.document_type] = []
            existing_by_type[doc.document_type].append(doc)

        # Build checklist based on stage requirements
        for doc_type, config in DOCUMENT_CONFIGS.items():
            required_stages = config.get("required_for_stages", [])
            is_required = lifecycle_stage in required_stages

            existing = existing_by_type.get(doc_type, [])
            approved = [d for d in existing if d.status == DocumentStatus.APPROVED]
            pending = [d for d in existing if d.status in [DocumentStatus.PENDING, DocumentStatus.PROCESSING]]
            rejected = [d for d in existing if d.status == DocumentStatus.REJECTED]

            status = "not_uploaded"
            if approved:
                status = "approved"
            elif pending:
                status = "pending"
            elif rejected:
                status = "rejected"

            checklist.append({
                "document_type": doc_type.value,
                "display_name": config["display_name"],
                "is_required": is_required,
                "status": status,
                "uploaded_count": len(existing),
                "approved_count": len(approved),
                "latest_upload": existing[-1].uploaded_at.isoformat() if existing else None,
                "rejection_reason": rejected[-1].rejection_reason if rejected else None,
            })

        # Sort: required first, then by status
        status_order = {"not_uploaded": 0, "rejected": 1, "pending": 2, "approved": 3}
        checklist.sort(key=lambda x: (not x["is_required"], status_order.get(x["status"], 0)))

        return checklist

    def get_document_summary(self, loan_id: int) -> Dict[str, Any]:
        """Get document upload summary for a loan."""
        resolved_loan_id = loan_id

        try:
            # Resolve loan_id to portal_loan.id
            from models.portal_models import PortalLoan
            portal_loan = self.db.query(PortalLoan).filter(
                PortalLoan.crm_deal_id == loan_id
            ).first()
            if not portal_loan:
                portal_loan = self.db.query(PortalLoan).filter(
                    PortalLoan.id == loan_id
                ).first()
            resolved_loan_id = portal_loan.id if portal_loan else loan_id
        except SQLAlchemyError as e:
            logger.warning(f"Could not resolve loan_id {loan_id} for document summary: {e}")
            self.db.rollback()

        by_status = {
            "pending": 0,
            "processing": 0,
            "approved": 0,
            "rejected": 0,
        }

        try:
            docs = self.db.query(PortalDocument).filter(
                PortalDocument.loan_id == resolved_loan_id
            ).all()

            for doc in docs:
                # Determine status from extraction_status and is_verified
                if hasattr(doc, 'is_verified') and doc.is_verified:
                    by_status["approved"] += 1
                elif hasattr(doc, 'extraction_status') and doc.extraction_status and doc.extraction_status.value in ["PROCESSING"]:
                    by_status["processing"] += 1
                elif hasattr(doc, 'extraction_status') and doc.extraction_status and doc.extraction_status.value == "FAILED":
                    by_status["rejected"] += 1
                else:
                    by_status["pending"] += 1
        except SQLAlchemyError as e:
            logger.warning(f"Could not get documents for loan {loan_id}: {e}")
            self.db.rollback()
            docs = []

        total = len(docs) if docs else 0
        return {
            "total": total,
            "by_status": by_status,
            "pending_review": by_status["pending"] + by_status["processing"],
            "needs_reupload": by_status["rejected"],
            "completion_rate": round((by_status["approved"] / total * 100) if total > 0 else 0, 1),
        }
