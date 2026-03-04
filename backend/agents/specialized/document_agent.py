"""
Document Agent

Specialized agent for document processing and management with 8 tools:
1. get_required_documents - Get list of required documents for a loan
2. get_document_status - Get status of documents for an entity
3. request_document - Send document request to borrower
4. upload_document - Process and categorize uploaded document
5. get_missing_documents - Get missing/incomplete documents
6. verify_document - Verify document completeness/validity
7. get_document_history - Get document upload/request history
8. expire_document - Mark document as expired (needs renewal)
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class GetRequiredDocumentsInput(BaseModel):
    """Input schema for get_required_documents tool"""
    loan_type: str = Field(..., description="Loan type: conventional, fha, va, usda, jumbo")
    employment_type: Optional[str] = Field(None, description="Employment type: w2, self_employed, retired")
    property_type: Optional[str] = Field(None, description="Property type: single_family, condo, multi_family")


class GetDocumentStatusInput(BaseModel):
    """Input schema for get_document_status tool"""
    entity_type: str = Field(..., description="Entity type: lead or loan")
    entity_id: int = Field(..., description="Entity ID")
    category: Optional[str] = Field(None, description="Filter by category: income, asset, identity, property")


class RequestDocumentInput(BaseModel):
    """Input schema for request_document tool"""
    entity_type: str = Field(..., description="Entity type: lead or loan")
    entity_id: int = Field(..., description="Entity ID")
    document_types: List[str] = Field(..., description="Document types to request")
    due_date: Optional[str] = Field(None, description="Due date for documents (ISO format)")
    send_email: bool = Field(default=True, description="Send email notification to borrower")
    message: Optional[str] = Field(None, description="Custom message to include")


class UploadDocumentInput(BaseModel):
    """Input schema for upload_document tool"""
    entity_type: str = Field(..., description="Entity type: lead or loan")
    entity_id: int = Field(..., description="Entity ID")
    document_type: str = Field(..., description="Document type (e.g., W2, paystub, bank_statement)")
    file_name: str = Field(..., description="Original file name")
    file_path: str = Field(..., description="Path to uploaded file")
    category: Optional[str] = Field(None, description="Document category")


class GetMissingDocumentsInput(BaseModel):
    """Input schema for get_missing_documents tool"""
    entity_type: str = Field(..., description="Entity type: lead or loan")
    entity_id: int = Field(..., description="Entity ID")
    include_expired: bool = Field(default=True, description="Include expired documents as missing")


class VerifyDocumentInput(BaseModel):
    """Input schema for verify_document tool"""
    document_id: int = Field(..., description="Document ID to verify")
    status: str = Field(..., description="Verification status: approved, rejected, needs_review")
    notes: Optional[str] = Field(None, description="Verification notes")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection if rejected")


class GetDocumentHistoryInput(BaseModel):
    """Input schema for get_document_history tool"""
    entity_type: str = Field(..., description="Entity type: lead or loan")
    entity_id: int = Field(..., description="Entity ID")
    limit: int = Field(default=50, description="Maximum records to return")


class ExpireDocumentInput(BaseModel):
    """Input schema for expire_document tool"""
    document_id: int = Field(..., description="Document ID to expire")
    reason: str = Field(..., description="Reason for expiration: age, superseded, invalid")
    request_replacement: bool = Field(default=True, description="Automatically request replacement")


# ============================================================================
# DOCUMENT AGENT
# ============================================================================

@AgentRegistry.register
class DocumentAgent(SpecializedAgent):
    """
    Specialized agent for document management.

    Handles document requirements, tracking, verification,
    and borrower communication for document collection.
    """

    @property
    def name(self) -> str:
        return "DocumentAgent"

    @property
    def description(self) -> str:
        return "Manages loan documents including requirements, collection, verification, and tracking"

    def _register_tools(self):
        """Register all document management tools"""

        # Tool 1: Get Required Documents
        self.register_tool(AgentTool(
            name="get_required_documents",
            description="Get list of required documents based on loan type and borrower profile. "
                       "Essential for setting up document collection.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_required_documents,
            input_schema=GetRequiredDocumentsInput
        ))

        # Tool 2: Get Document Status
        self.register_tool(AgentTool(
            name="get_document_status",
            description="Get current status of all documents for a lead or loan. "
                       "Shows received, pending, and verified documents.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_document_status,
            input_schema=GetDocumentStatusInput
        ))

        # Tool 3: Request Document
        self.register_tool(AgentTool(
            name="request_document",
            description="Send document request to borrower via email. "
                       "Creates tracking record and sets due date.",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._request_document,
            input_schema=RequestDocumentInput
        ))

        # Tool 4: Upload Document
        self.register_tool(AgentTool(
            name="upload_document",
            description="Process and categorize an uploaded document. "
                       "Associates with entity and updates tracking.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._upload_document,
            input_schema=UploadDocumentInput
        ))

        # Tool 5: Get Missing Documents
        self.register_tool(AgentTool(
            name="get_missing_documents",
            description="Get list of missing or incomplete documents for an entity. "
                       "Includes expired documents if specified.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_missing_documents,
            input_schema=GetMissingDocumentsInput
        ))

        # Tool 6: Verify Document
        self.register_tool(AgentTool(
            name="verify_document",
            description="Update document verification status. "
                       "Mark as approved, rejected, or needs review.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._verify_document,
            input_schema=VerifyDocumentInput
        ))

        # Tool 7: Get Document History
        self.register_tool(AgentTool(
            name="get_document_history",
            description="Get document upload and request history for an entity. "
                       "Shows timeline of document activity.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_document_history,
            input_schema=GetDocumentHistoryInput
        ))

        # Tool 8: Expire Document
        self.register_tool(AgentTool(
            name="expire_document",
            description="Mark a document as expired and optionally request replacement. "
                       "Used for aged or superseded documents.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._expire_document,
            input_schema=ExpireDocumentInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _get_required_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get required documents based on loan type"""

        loan_type = input_data["loan_type"].lower()
        employment_type = input_data.get("employment_type", "w2").lower()

        # Base documents for all loans
        base_documents = {
            "identity": [
                {"type": "government_id", "name": "Government-issued ID", "required": True},
                {"type": "ssn_card", "name": "Social Security Card", "required": False}
            ],
            "income": [],
            "asset": [
                {"type": "bank_statements", "name": "Bank Statements (2 months)", "required": True},
                {"type": "investment_statements", "name": "Investment Account Statements", "required": False}
            ],
            "property": [
                {"type": "purchase_contract", "name": "Purchase Contract", "required": True},
                {"type": "homeowners_insurance", "name": "Homeowners Insurance", "required": True}
            ]
        }

        # Income documents based on employment type
        if employment_type == "w2":
            base_documents["income"] = [
                {"type": "w2", "name": "W-2 Forms (2 years)", "required": True},
                {"type": "paystubs", "name": "Recent Paystubs (30 days)", "required": True},
                {"type": "tax_returns", "name": "Tax Returns (2 years)", "required": False}
            ]
        elif employment_type == "self_employed":
            base_documents["income"] = [
                {"type": "tax_returns", "name": "Personal Tax Returns (2 years)", "required": True},
                {"type": "business_tax_returns", "name": "Business Tax Returns (2 years)", "required": True},
                {"type": "profit_loss", "name": "Year-to-Date P&L Statement", "required": True},
                {"type": "business_license", "name": "Business License", "required": True}
            ]
        elif employment_type == "retired":
            base_documents["income"] = [
                {"type": "social_security_award", "name": "Social Security Award Letter", "required": True},
                {"type": "pension_statement", "name": "Pension Statement", "required": False},
                {"type": "retirement_statements", "name": "Retirement Account Statements", "required": True}
            ]

        # Loan-type specific additions
        if loan_type == "va":
            base_documents["identity"].append(
                {"type": "dd214", "name": "DD-214 or Certificate of Eligibility", "required": True}
            )
        elif loan_type == "fha":
            base_documents["property"].append(
                {"type": "fha_case_number", "name": "FHA Case Number Assignment", "required": True}
            )

        # Count totals
        total_required = 0
        total_optional = 0
        for category, docs in base_documents.items():
            for doc in docs:
                if doc["required"]:
                    total_required += 1
                else:
                    total_optional += 1

        return ToolResult(
            success=True,
            data={
                "loan_type": loan_type,
                "employment_type": employment_type,
                "documents_by_category": base_documents,
                "total_required": total_required,
                "total_optional": total_optional
            },
            message=f"Required documents for {loan_type.upper()} loan: {total_required} required, {total_optional} optional"
        )

    async def _get_document_status(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get document status for an entity"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            entity_type = input_data["entity_type"]
            entity_id = input_data["entity_id"]
            org_id = self.context.get("organization_id")

            # Verify entity belongs to org
            if org_id:
                table = "leads" if entity_type == "lead" else "loans"
                owner_check = db.execute(
                    text(f"SELECT id FROM {table} WHERE id = :entity_id AND organization_id = :org_id"),
                    {"entity_id": entity_id, "org_id": org_id}
                ).fetchone()
                if not owner_check:
                    return ToolResult(success=False, error=f"{entity_type.title()} {entity_id} not found")

            params = {
                "entity_type": entity_type,
                "entity_id": entity_id
            }

            category_filter = ""
            if input_data.get("category"):
                category_filter = "AND category = :category"
                params["category"] = input_data["category"]

            query = text(f"""
                SELECT
                    id, document_type, category, file_name,
                    status, verification_status, uploaded_at,
                    verified_at, expires_at,
                    CASE
                        WHEN expires_at IS NOT NULL AND expires_at < CURRENT_DATE THEN true
                        ELSE false
                    END as is_expired
                FROM documents
                WHERE entity_type = :entity_type
                    AND entity_id = :entity_id
                    {category_filter}
                ORDER BY category, document_type
            """)

            results = db.execute(query, params).fetchall()

            documents = []
            status_counts = {"received": 0, "verified": 0, "rejected": 0, "pending": 0, "expired": 0}

            for r in results:
                if r.is_expired:
                    status_counts["expired"] += 1
                elif r.verification_status == "approved":
                    status_counts["verified"] += 1
                elif r.verification_status == "rejected":
                    status_counts["rejected"] += 1
                elif r.status == "received":
                    status_counts["received"] += 1
                else:
                    status_counts["pending"] += 1

                documents.append({
                    "id": r.id,
                    "type": r.document_type,
                    "category": r.category,
                    "file_name": r.file_name,
                    "status": r.status,
                    "verification_status": r.verification_status,
                    "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                    "verified_at": r.verified_at.isoformat() if r.verified_at else None,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "is_expired": r.is_expired
                })

            # Group by category
            by_category = {}
            for doc in documents:
                cat = doc["category"] or "uncategorized"
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(doc)

            self.audit_log("get_document_status", "document", details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "document_count": len(documents),
            })

            return ToolResult(
                success=True,
                data={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "documents": documents,
                    "by_category": by_category,
                    "status_counts": status_counts,
                    "total": len(documents)
                },
                message=f"Document status: {status_counts['verified']} verified, {status_counts['received']} pending review, {status_counts['expired']} expired"
            )

        except Exception as e:
            logger.exception(f"get_document_status failed for {entity_type} {entity_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _request_document(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Request documents from borrower"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            entity_type = input_data["entity_type"]
            entity_id = input_data["entity_id"]
            org_id = self.context.get("organization_id")

            # Verify entity belongs to org
            if org_id:
                table = "leads" if entity_type == "lead" else "loans"
                owner_check = db.execute(
                    text(f"SELECT id FROM {table} WHERE id = :entity_id AND organization_id = :org_id"),
                    {"entity_id": entity_id, "org_id": org_id}
                ).fetchone()
                if not owner_check:
                    return ToolResult(success=False, error=f"{entity_type.title()} {entity_id} not found")

            due_date = input_data.get("due_date")
            if not due_date:
                due_date = (date.today() + timedelta(days=7)).isoformat()

            # Create document requests
            created_requests = []
            for doc_type in input_data["document_types"]:
                query = text("""
                    INSERT INTO document_requests (
                        entity_type, entity_id, document_type,
                        due_date, status, message,
                        created_by, created_at
                    ) VALUES (
                        :entity_type, :entity_id, :document_type,
                        :due_date, 'pending', :message,
                        :created_by, CURRENT_TIMESTAMP
                    )
                    RETURNING id, document_type
                """)

                result = db.execute(query, {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "document_type": doc_type,
                    "due_date": due_date,
                    "message": input_data.get("message"),
                    "created_by": context.get("user_id", 1)
                }).fetchone()

                created_requests.append({
                    "request_id": result.id,
                    "document_type": result.document_type
                })

            # Send email notification if requested
            email_sent = False
            if input_data.get("send_email", True):
                # In production, integrate with email service
                # For now, log communication
                comm_query = text("""
                    INSERT INTO communications (
                        type, direction, entity_type, entity_id,
                        subject, content, status, created_by, created_at
                    ) VALUES (
                        'email', 'outbound', :entity_type, :entity_id,
                        :subject, :content, 'sent', :created_by, CURRENT_TIMESTAMP
                    )
                """)

                doc_list = ", ".join(input_data["document_types"])
                db.execute(comm_query, {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "subject": "Document Request",
                    "content": f"Documents requested: {doc_list}. Due by: {due_date}",
                    "created_by": context.get("user_id", 1)
                })
                email_sent = True

            db.commit()

            self.audit_log("request_document", "document", details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "document_types": input_data["document_types"],
                "due_date": due_date,
                "email_sent": email_sent,
            })

            return ToolResult(
                success=True,
                data={
                    "requests": created_requests,
                    "count": len(created_requests),
                    "due_date": due_date,
                    "email_sent": email_sent
                },
                message=f"Requested {len(created_requests)} document(s), due {due_date}"
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"request_document failed for {entity_type} {entity_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _upload_document(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Process uploaded document"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            entity_type = input_data["entity_type"]
            entity_id = input_data["entity_id"]
            org_id = self.context.get("organization_id")

            # Verify entity belongs to org
            if org_id:
                table = "leads" if entity_type == "lead" else "loans"
                owner_check = db.execute(
                    text(f"SELECT id FROM {table} WHERE id = :entity_id AND organization_id = :org_id"),
                    {"entity_id": entity_id, "org_id": org_id}
                ).fetchone()
                if not owner_check:
                    return ToolResult(success=False, error=f"{entity_type.title()} {entity_id} not found")

            # Determine category from document type
            doc_type = input_data["document_type"].lower()
            category = input_data.get("category")

            if not category:
                category_mapping = {
                    "w2": "income", "paystub": "income", "tax_return": "income",
                    "bank_statement": "asset", "investment": "asset",
                    "id": "identity", "license": "identity", "ssn": "identity",
                    "contract": "property", "appraisal": "property", "insurance": "property"
                }
                for key, cat in category_mapping.items():
                    if key in doc_type:
                        category = cat
                        break
                if not category:
                    category = "other"

            # Calculate expiration for certain document types
            expires_at = None
            if doc_type in ["paystub", "bank_statement"]:
                expires_at = (date.today() + timedelta(days=90)).isoformat()
            elif doc_type in ["tax_return", "w2"]:
                expires_at = (date.today() + timedelta(days=365)).isoformat()

            query = text("""
                INSERT INTO documents (
                    entity_type, entity_id, document_type, category,
                    file_name, file_path, status, verification_status,
                    expires_at, uploaded_by, uploaded_at
                ) VALUES (
                    :entity_type, :entity_id, :document_type, :category,
                    :file_name, :file_path, 'received', 'pending',
                    :expires_at, :uploaded_by, CURRENT_TIMESTAMP
                )
                RETURNING id, document_type, category
            """)

            result = db.execute(query, {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "document_type": input_data["document_type"],
                "category": category,
                "file_name": input_data["file_name"],
                "file_path": input_data["file_path"],
                "expires_at": expires_at,
                "uploaded_by": context.get("user_id", 1)
            }).fetchone()

            # Update any pending requests for this document type
            db.execute(
                text("""
                    UPDATE document_requests
                    SET status = 'fulfilled', fulfilled_at = CURRENT_TIMESTAMP
                    WHERE entity_type = :entity_type
                        AND entity_id = :entity_id
                        AND document_type = :document_type
                        AND status = 'pending'
                """),
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "document_type": input_data["document_type"]
                }
            )

            db.commit()

            self.audit_log("upload_document", "document", entity_id=result.id, details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "document_type": input_data["document_type"],
                "file_name": input_data["file_name"],
            })

            return ToolResult(
                success=True,
                data={
                    "document_id": result.id,
                    "type": result.document_type,
                    "category": result.category,
                    "expires_at": expires_at,
                    "status": "received",
                    "verification_status": "pending"
                },
                message=f"Document '{input_data['file_name']}' uploaded successfully"
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"upload_document failed for {entity_type} {entity_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_missing_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get missing documents for an entity"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            # Get loan type to determine requirements
            entity_type = input_data["entity_type"]
            entity_id = input_data["entity_id"]
            org_id = self.context.get("organization_id")

            if entity_type == "loan":
                org_clause = "AND organization_id = :org_id" if org_id else ""
                params = {"id": entity_id}
                if org_id:
                    params["org_id"] = org_id

                loan = db.execute(
                    text(f"SELECT program, employment_type FROM loans WHERE id = :id {org_clause}"),
                    params
                ).fetchone()

                if not loan:
                    return ToolResult(success=False, error=f"Loan {entity_id} not found")

                # Map program to loan type
                program = (loan.program or "").lower()
                if "fha" in program:
                    loan_type = "fha"
                elif "va" in program:
                    loan_type = "va"
                else:
                    loan_type = "conventional"

                employment_type = loan.employment_type or "w2"
            else:
                # For leads, verify org ownership
                if org_id:
                    lead_check = db.execute(
                        text("SELECT id FROM leads WHERE id = :id AND organization_id = :org_id"),
                        {"id": entity_id, "org_id": org_id}
                    ).fetchone()
                    if not lead_check:
                        return ToolResult(success=False, error=f"Lead {entity_id} not found")
                loan_type = "conventional"
                employment_type = "w2"

            # Get required documents
            required_result = await self._get_required_documents(
                {"loan_type": loan_type, "employment_type": employment_type},
                context
            )

            if not required_result.success:
                return required_result

            required_docs = []
            for category, docs in required_result.data["documents_by_category"].items():
                for doc in docs:
                    if doc["required"]:
                        required_docs.append({
                            "type": doc["type"],
                            "name": doc["name"],
                            "category": category
                        })

            # Get received documents
            include_expired = input_data.get("include_expired", True)
            expired_condition = ""
            if include_expired:
                expired_condition = "AND (expires_at IS NULL OR expires_at >= CURRENT_DATE)"

            received_query = text(f"""
                SELECT document_type, verification_status, expires_at
                FROM documents
                WHERE entity_type = :entity_type
                    AND entity_id = :entity_id
                    AND status = 'received'
                    AND verification_status != 'rejected'
                    {expired_condition}
            """)

            received = db.execute(received_query, {
                "entity_type": entity_type,
                "entity_id": entity_id
            }).fetchall()

            received_types = {r.document_type.lower() for r in received}

            # Find missing
            missing = []
            for doc in required_docs:
                if doc["type"].lower() not in received_types:
                    missing.append(doc)

            # Get expired documents if including
            expired = []
            if include_expired:
                expired_query = text("""
                    SELECT id, document_type, category, expires_at
                    FROM documents
                    WHERE entity_type = :entity_type
                        AND entity_id = :entity_id
                        AND expires_at < CURRENT_DATE
                        AND verification_status != 'rejected'
                """)
                expired_results = db.execute(expired_query, {
                    "entity_type": entity_type,
                    "entity_id": entity_id
                }).fetchall()

                expired = [
                    {
                        "id": e.id,
                        "type": e.document_type,
                        "category": e.category,
                        "expired_at": e.expires_at.isoformat() if e.expires_at else None
                    }
                    for e in expired_results
                ]

            self.audit_log("get_missing_documents", "document", details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "missing_count": len(missing),
                "expired_count": len(expired),
            })

            return ToolResult(
                success=True,
                data={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "missing": missing,
                    "expired": expired,
                    "missing_count": len(missing),
                    "expired_count": len(expired)
                },
                message=f"Missing: {len(missing)} required documents, {len(expired)} expired"
            )

        except Exception as e:
            logger.exception(f"get_missing_documents failed for {entity_type} {entity_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _verify_document(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Verify document status"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            document_id = input_data["document_id"]
            status = input_data["status"]
            org_id = self.context.get("organization_id")
            valid_statuses = ["approved", "rejected", "needs_review"]

            if status not in valid_statuses:
                return ToolResult(
                    success=False,
                    error=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                )

            # Verify document's parent entity belongs to org
            if org_id:
                doc_check = db.execute(
                    text("SELECT entity_type, entity_id FROM documents WHERE id = :doc_id"),
                    {"doc_id": document_id}
                ).fetchone()
                if not doc_check:
                    return ToolResult(success=False, error=f"Document {document_id} not found")
                table = "leads" if doc_check.entity_type == "lead" else "loans"
                owner_check = db.execute(
                    text(f"SELECT id FROM {table} WHERE id = :entity_id AND organization_id = :org_id"),
                    {"entity_id": doc_check.entity_id, "org_id": org_id}
                ).fetchone()
                if not owner_check:
                    return ToolResult(success=False, error=f"Document {document_id} not found")

            query = text("""
                UPDATE documents
                SET verification_status = :status,
                    verification_notes = :notes,
                    rejection_reason = :rejection_reason,
                    verified_by = :verified_by,
                    verified_at = CURRENT_TIMESTAMP
                WHERE id = :document_id
                RETURNING id, document_type, entity_type, entity_id
            """)

            result = db.execute(query, {
                "document_id": document_id,
                "status": status,
                "notes": input_data.get("notes"),
                "rejection_reason": input_data.get("rejection_reason") if status == "rejected" else None,
                "verified_by": context.get("user_id", 1)
            }).fetchone()

            if not result:
                return ToolResult(success=False, error=f"Document {document_id} not found")

            db.commit()

            self.audit_log("verify_document", "document", entity_id=document_id, details={
                "verification_status": status,
                "entity_type": result.entity_type,
                "entity_id": result.entity_id,
            })

            return ToolResult(
                success=True,
                data={
                    "document_id": result.id,
                    "type": result.document_type,
                    "status": status,
                    "entity_type": result.entity_type,
                    "entity_id": result.entity_id
                },
                message=f"Document {result.id} marked as {status}"
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"verify_document failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_document_history(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get document history for an entity"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            entity_type = input_data["entity_type"]
            entity_id = input_data["entity_id"]
            org_id = self.context.get("organization_id")

            # Verify entity belongs to org
            if org_id:
                table = "leads" if entity_type == "lead" else "loans"
                owner_check = db.execute(
                    text(f"SELECT id FROM {table} WHERE id = :entity_id AND organization_id = :org_id"),
                    {"entity_id": entity_id, "org_id": org_id}
                ).fetchone()
                if not owner_check:
                    return ToolResult(success=False, error=f"{entity_type.title()} {entity_id} not found")

            # Get uploads
            uploads_query = text("""
                SELECT
                    'upload' as event_type,
                    id, document_type, file_name, status,
                    verification_status, uploaded_at as event_date
                FROM documents
                WHERE entity_type = :entity_type
                    AND entity_id = :entity_id
                ORDER BY uploaded_at DESC
                LIMIT :limit
            """)

            uploads = db.execute(uploads_query, {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "limit": input_data.get("limit", 50)
            }).fetchall()

            # Get requests
            requests_query = text("""
                SELECT
                    'request' as event_type,
                    id, document_type, status, due_date,
                    created_at as event_date
                FROM document_requests
                WHERE entity_type = :entity_type
                    AND entity_id = :entity_id
                ORDER BY created_at DESC
                LIMIT :limit
            """)

            requests = db.execute(requests_query, {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "limit": input_data.get("limit", 50)
            }).fetchall()

            # Combine and sort by date
            history = []

            for u in uploads:
                history.append({
                    "event_type": "upload",
                    "id": u.id,
                    "document_type": u.document_type,
                    "file_name": u.file_name,
                    "status": u.status,
                    "verification_status": u.verification_status,
                    "date": u.event_date.isoformat() if u.event_date else None
                })

            for r in requests:
                history.append({
                    "event_type": "request",
                    "id": r.id,
                    "document_type": r.document_type,
                    "status": r.status,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "date": r.event_date.isoformat() if r.event_date else None
                })

            # Sort by date descending
            history.sort(key=lambda x: x["date"] or "", reverse=True)

            self.audit_log("get_document_history", "document", details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "upload_count": len(uploads),
                "request_count": len(requests),
            })

            return ToolResult(
                success=True,
                data={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "history": history[:input_data.get("limit", 50)],
                    "upload_count": len(uploads),
                    "request_count": len(requests)
                },
                message=f"Document history: {len(uploads)} uploads, {len(requests)} requests"
            )

        except Exception as e:
            logger.exception(f"get_document_history failed for {entity_type} {entity_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _expire_document(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Mark document as expired"""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.context.get("organization_id")

        db = SessionLocal()
        try:
            # Get document info
            doc = db.execute(
                text("SELECT * FROM documents WHERE id = :id"),
                {"id": document_id}
            ).fetchone()

            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found")

            # Verify document's parent entity belongs to org
            if org_id:
                table = "leads" if doc.entity_type == "lead" else "loans"
                owner_check = db.execute(
                    text(f"SELECT id FROM {table} WHERE id = :entity_id AND organization_id = :org_id"),
                    {"entity_id": doc.entity_id, "org_id": org_id}
                ).fetchone()
                if not owner_check:
                    return ToolResult(success=False, error=f"Document {document_id} not found")

            # Update document status
            query = text("""
                UPDATE documents
                SET verification_status = 'expired',
                    expires_at = CURRENT_DATE,
                    verification_notes = COALESCE(verification_notes, '') || :note
                WHERE id = :document_id
                RETURNING id, document_type, entity_type, entity_id
            """)

            result = db.execute(query, {
                "document_id": document_id,
                "note": f"\n[{datetime.now().isoformat()}] Expired: {input_data['reason']}"
            }).fetchone()

            # Request replacement if specified
            replacement_requested = False
            if input_data.get("request_replacement", True):
                request_query = text("""
                    INSERT INTO document_requests (
                        entity_type, entity_id, document_type,
                        due_date, status, message, created_by, created_at
                    ) VALUES (
                        :entity_type, :entity_id, :document_type,
                        :due_date, 'pending', :message, :created_by, CURRENT_TIMESTAMP
                    )
                """)

                db.execute(request_query, {
                    "entity_type": result.entity_type,
                    "entity_id": result.entity_id,
                    "document_type": result.document_type,
                    "due_date": (date.today() + timedelta(days=7)).isoformat(),
                    "message": f"Previous document expired: {input_data['reason']}",
                    "created_by": context.get("user_id", 1)
                })
                replacement_requested = True

            db.commit()

            self.audit_log("expire_document", "document", entity_id=document_id, details={
                "reason": input_data["reason"],
                "replacement_requested": replacement_requested,
                "document_type": result.document_type,
                "entity_type": result.entity_type,
                "entity_id": result.entity_id,
            })

            return ToolResult(
                success=True,
                data={
                    "document_id": result.id,
                    "type": result.document_type,
                    "reason": input_data["reason"],
                    "replacement_requested": replacement_requested
                },
                message=f"Document {result.id} expired. {'Replacement requested.' if replacement_requested else ''}"
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"expire_document failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
