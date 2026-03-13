"""
Smart Docs V2 API Reference
============================

Comprehensive OpenAPI/Swagger documentation enhancements for all Smart Docs V2
endpoints. Import this module from route files to attach rich descriptions,
response examples, and schema metadata to FastAPI auto-docs.

Usage in route files:

    from docs.smart_docs_api_reference import (
        RESPONSE_EXAMPLES,
        REQUEST_EXAMPLES,
        get_api_docs_config,
    )

    @router.post(
        "/needs-list/generate",
        responses=RESPONSE_EXAMPLES["needs_list_generate"],
    )
    async def generate_needs_list(...):
        ...

Endpoint Groups
---------------
1.  Document Management      /api/v1/smart-docs/*
2.  Income Calculation        /api/smart-docs/income/*
3.  E-Signature               /api/v1/esign/*
4.  Document Requests         /api/v1/smart-docs/needs-list/*
5.  Bank Statement Analysis   /api/smart-docs/bank-analysis/*
6.  Document Intelligence     /api/smart-docs/doc-intel/*
7.  Follow-up & Scheduling    /api/smart-docs/followup/*
8.  Document Security         /api/smart-docs/doc-security/*
9.  Document Analytics        /api/smart-docs/doc-analytics/*
10. Borrower Portal           /api/smart-docs/portal/docs/*
11. Document Review           /api/smart-docs/doc-review/*
12. Enterprise Config         /api/smart-docs/config/*
13. eClosing                  /api/smart-docs/eclosing/*
14. Plaid Verification        /api/smart-docs/plaid/*
15. AUS Integration           /api/smart-docs/aus/*
16. MISMO Data Mapping        /api/smart-docs/mismo/*
17. IRS Transcript            /api/smart-docs/transcript/*
18. Monitoring & Health       /api/smart-docs/monitoring/*

Authentication
--------------
- Internal endpoints: Bearer JWT via ``Authorization: Bearer <token>``
- Portal endpoints:   Portal JWT via ``X-Portal-Token`` header, ``Authorization:
  Bearer``, or ``?token=`` query parameter
- Admin endpoints:    Require ``permission_role`` of ``admin`` or ``site_admin``
- API key endpoints:  ``X-API-Key`` header (bypasses CSRF middleware)

Multi-Tenant Isolation
----------------------
All endpoints enforce organization-level tenant isolation. The authenticated
user's ``organization_id`` is matched against the loan's ``organization_id``
via ``_verify_loan_tenant()``. Platform admins bypass this check. Portal tokens
encode ``loan_id`` and ``org_id`` directly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# =============================================================================
# API METADATA / TAGS
# =============================================================================

API_TITLE = "Smart Docs V2 API"
API_VERSION = "2.0.0"
API_DESCRIPTION = __doc__

TAGS_METADATA: List[Dict[str, str]] = [
    {
        "name": "Smart Documents",
        "description": (
            "Core document management: upload, classify, approve, reject, "
            "delete, merge, download, needs-list generation, and freshness "
            "tracking."
        ),
    },
    {
        "name": "Income Calculation",
        "description": (
            "AI-assisted income calculation from paystubs, W-2s, and tax "
            "returns. Includes maker-checker approval workflow, verification "
            "task management, income source overrides, and DTI analysis."
        ),
    },
    {
        "name": "E-Signature",
        "description": (
            "Built-in e-signature system: envelope management, signing "
            "sessions (token-based, no login required), field placement, "
            "KBA authentication, UETA/ESIGN consent, templates, and "
            "cryptographic audit trail."
        ),
    },
    {
        "name": "Bank Statement Analysis",
        "description": (
            "AI-powered bank statement analysis: large deposit detection, "
            "NSF/overdraft tracking, IRS payment identification, income "
            "verification from deposits, undisclosed debt detection, risk "
            "scoring, and PDF report generation."
        ),
    },
    {
        "name": "Document Intelligence",
        "description": (
            "AI document classification, POS-to-document analysis, call "
            "transcript document need detection, configurable requirement "
            "rules, batch classification, and classification feedback."
        ),
    },
    {
        "name": "Document Follow-up",
        "description": (
            "Automated follow-up campaigns for outstanding document requests, "
            "borrower appointment scheduling, and reusable message templates."
        ),
    },
    {
        "name": "Document Security",
        "description": (
            "SOC 2 / regulatory compliance: access audit logging, integrity "
            "verification (SHA-256), fraud analysis, retention policy "
            "management (TRID, state-specific), forensic watermarking, "
            "encryption status, and suspicious activity detection."
        ),
    },
    {
        "name": "Document Analytics",
        "description": (
            "Comprehensive analytics dashboard: pipeline completeness, SLA "
            "compliance, AI classification performance, follow-up "
            "effectiveness, processor productivity, loan timelines, trends, "
            "and bottleneck identification."
        ),
    },
    {
        "name": "Document Portal",
        "description": (
            "Borrower-facing portal endpoints: document checklist, upload, "
            "re-upload, preview, LOE submission, e-signature requests, "
            "appointment viewing, LO messaging, and progress tracking. "
            "Authenticated via portal JWT tokens."
        ),
    },
    {
        "name": "Document Review",
        "description": (
            "AI document review queue: single and batch AI review, queue "
            "management (get, claim, release), pre-upload validation, "
            "cross-document consistency, review history, auto-review "
            "settings, and loan completeness tracking."
        ),
    },
    {
        "name": "business-rules",
        "description": (
            "Business rules configuration: view and manage threshold values, "
            "limits, and settings that control document processing behavior "
            "without code deploys. Admin only."
        ),
    },
]


# =============================================================================
# ENUM DESCRIPTIONS
# =============================================================================

DOC_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "DRIVERS_LICENSE": "Government-issued photo ID (driver's license, state ID, passport).",
    "PAYSTUB": "Recent pay stub showing YTD earnings, deductions, and pay period dates.",
    "W2": "IRS Form W-2 Wage and Tax Statement.",
    "TAX_RETURN": "Federal personal tax return (Form 1040) with all schedules.",
    "BUSINESS_TAX_RETURN": "Federal business tax return (1065, 1120, 1120S).",
    "PROFIT_LOSS": "Year-to-date profit and loss statement for self-employed borrowers.",
    "BALANCE_SHEET": "Current balance sheet for business entities.",
    "BANK_STATEMENT": "Bank account statement (checking, savings, money market).",
    "INVESTMENT_STATEMENT": "Investment / retirement account statement (401k, IRA, brokerage).",
    "GIFT_LETTER": "Gift letter documenting source and amount of gift funds.",
    "LOE": "Letter of Explanation for credit events, employment gaps, or address discrepancies.",
    "LEASE_AGREEMENT": "Signed lease agreement for rental properties.",
    "FHA_CERT": "FHA certification documents.",
    "VA_COE": "VA Certificate of Eligibility.",
    "DD214": "DD-214 Certificate of Release or Discharge from Active Duty.",
    "BANKRUPTCY_DISCHARGE": "Bankruptcy discharge papers with case number.",
    "PURCHASE_CONTRACT": "Signed purchase agreement / sales contract.",
    "APPRAISAL": "Completed appraisal report with comparable sales.",
    "TITLE_REPORT": "Preliminary title report or title commitment.",
    "HOMEOWNERS_INSURANCE": "Evidence of homeowners insurance (HOI binder or declaration page).",
    "OTHER": "Document type not in the standard classification list.",
}

REQUEST_STATUS_DESCRIPTIONS: Dict[str, str] = {
    "OPEN": "Document has been requested but not yet uploaded by the borrower.",
    "PENDING_REVIEW": "Document uploaded and awaiting LO or AI review.",
    "ACCEPTED": "Document reviewed and accepted as meeting the requirement.",
    "REJECTED": "Document rejected; borrower must re-upload.",
    "WAIVED": "Requirement waived by an authorized user with a documented reason.",
}

DOCUMENT_STATUS_DESCRIPTIONS: Dict[str, str] = {
    "UPLOADED": "File received and stored; awaiting processing.",
    "SCANNING": "Document is being scanned for screenshot detection and quality.",
    "PROCESSING": "AI extraction and classification in progress.",
    "APPROVED": "Document passed review and is accepted.",
    "REJECTED": "Document failed review; reason and fix instructions provided.",
    "EXPIRED": "Document date exceeds freshness window (e.g., paystub > 30 days).",
    "DELETED": "Soft-deleted; can be restored by admin.",
    "SUPERSEDED": "Replaced by a newer version of the same document.",
}

REJECTION_CATEGORY_DESCRIPTIONS: Dict[str, str] = {
    "SCREENSHOT": "Document appears to be a screenshot rather than an original PDF or scan.",
    "EXPIRED": "Document date is outside the acceptable freshness window.",
    "POOR_QUALITY": "Image quality too low to read or verify content.",
    "INCOMPLETE": "Document is missing pages, signatures, or required sections.",
    "WRONG_TYPE": "Document does not match the requested document type.",
    "OTHER": "Rejected for a reason not covered by standard categories.",
}

ENVELOPE_STATUS_DESCRIPTIONS: Dict[str, str] = {
    "DRAFT": "Envelope created but not yet sent to recipients.",
    "SENT": "Envelope sent; waiting for recipients to sign.",
    "COMPLETED": "All recipients have signed; document is fully executed.",
    "DECLINED": "One or more recipients declined to sign.",
    "VOIDED": "Envelope voided by the sender before completion.",
    "EXPIRED": "Signing deadline passed without all signatures.",
}

CAMPAIGN_STATUS_DESCRIPTIONS: Dict[str, str] = {
    "PENDING": "Campaign created but first message not yet sent.",
    "ACTIVE": "Campaign is running; messages being delivered on schedule.",
    "PAUSED": "Campaign temporarily paused by user.",
    "COMPLETED": "All campaign steps have been executed.",
    "CANCELLED": "Campaign cancelled before completion.",
    "RESPONDED": "Borrower responded; campaign auto-paused.",
}


# =============================================================================
# AUTHENTICATION DOCUMENTATION
# =============================================================================

AUTH_SCHEMES: Dict[str, Dict[str, Any]] = {
    "bearer_jwt": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Standard JWT authentication for internal API users (loan officers, "
            "processors, admins). Token issued via ``POST /api/v1/auth/login``. "
            "Include in the ``Authorization`` header as ``Bearer <token>``. "
            "Tokens are RS256-signed and contain ``user_id``, "
            "``organization_id``, ``permission_role``, and ``exp`` claims."
        ),
    },
    "portal_token": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Portal JWT for borrower-facing endpoints. Issued via magic link "
            "or ``POST /api/smart-docs/portal/v2/magic-link``. Can be passed "
            "as ``X-Portal-Token`` header, ``Authorization: Bearer``, or "
            "``?token=`` query parameter. Contains ``loan_id``, "
            "``borrower_email``, ``org_id``, and ``scope`` (read_only or "
            "read_write) claims. Write operations require ``read_write`` scope."
        ),
    },
    "api_key": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": (
            "API key authentication for server-to-server integrations and "
            "webhook callbacks. Bypasses CSRF middleware when token length "
            "is under 50 characters. Used primarily by eClosing webhooks "
            "and external integrations."
        ),
    },
}

ENDPOINT_AUTH_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    # Document Management
    "needs_list_generate": {
        "auth": "bearer_jwt",
        "roles": ["loan_officer", "processor", "admin", "site_admin"],
        "description": "Requires authenticated user with access to the loan's organization.",
    },
    "document_upload": {
        "auth": "bearer_jwt",
        "roles": ["loan_officer", "processor", "admin", "site_admin"],
        "description": "Requires authenticated user. Tenant isolation enforced via loan_id.",
    },
    "document_approve": {
        "auth": "bearer_jwt",
        "roles": ["processor", "admin", "site_admin"],
        "description": "Requires authenticated user with review permissions.",
    },
    "document_delete": {
        "auth": "bearer_jwt",
        "roles": ["processor", "admin", "site_admin"],
        "description": "Requires authenticated user. Soft-delete only.",
    },

    # Portal
    "portal_upload": {
        "auth": "portal_token",
        "scope": "read_write",
        "description": "Requires portal token with read_write scope. Rate limited.",
    },
    "portal_checklist": {
        "auth": "portal_token",
        "scope": "read_only",
        "description": "Requires portal token with at least read_only scope.",
    },

    # Admin
    "admin_s3_test": {
        "auth": "bearer_jwt",
        "roles": ["admin", "site_admin"],
        "description": "Platform or site admin only.",
    },

    # E-Signature signing
    "esign_signing_session": {
        "auth": "signing_token",
        "description": (
            "Token-based authentication for signing sessions. No login "
            "required. Token is generated when the envelope is sent and "
            "contains recipient_id and envelope_id. Passed as query "
            "parameter ``?token=``."
        ),
    },
}


# =============================================================================
# RATE LIMITING DOCUMENTATION
# =============================================================================

RATE_LIMITS: Dict[str, Dict[str, Any]] = {
    "portal_upload": {
        "limit": "10 requests per minute per borrower",
        "scope": "Per portal token (borrower + loan combination)",
        "description": (
            "Upload rate limiting prevents abuse of the borrower portal. "
            "Each unique borrower/loan combination is limited to 10 uploads "
            "per minute. Exceeding the limit returns HTTP 429."
        ),
        "headers": {
            "X-RateLimit-Limit": "Maximum requests allowed in the window.",
            "X-RateLimit-Remaining": "Requests remaining in the current window.",
            "X-RateLimit-Reset": "Unix timestamp when the window resets.",
            "Retry-After": "Seconds to wait before retrying (on 429 only).",
        },
    },
    "esign_signing": {
        "limit": "30 requests per minute per signing token",
        "scope": "Per signing session token",
        "description": (
            "Signing session requests are rate-limited to prevent automated "
            "abuse. Each signing token is limited to 30 requests per minute."
        ),
    },
    "ai_classification": {
        "limit": "60 requests per minute per organization",
        "scope": "Per organization_id",
        "description": (
            "AI classification endpoints are rate-limited per organization "
            "to manage compute costs. Batch classification counts as one "
            "request regardless of document count."
        ),
    },
    "bank_analysis": {
        "limit": "20 requests per minute per organization",
        "scope": "Per organization_id",
        "description": (
            "Bank statement analysis is computationally intensive. Rate "
            "limited per organization. Cached results are returned without "
            "counting against the limit."
        ),
    },
    "default": {
        "limit": "120 requests per minute per user",
        "scope": "Per authenticated user_id",
        "description": "Default rate limit for all other Smart Docs endpoints.",
    },
}


# =============================================================================
# ERROR CODE REFERENCE
# =============================================================================

ERROR_CODES: Dict[str, Dict[str, str]] = {
    # 400 Bad Request
    "INVALID_DOC_TYPE": {
        "status": "400",
        "description": "The provided doc_type is not a valid DocType enum value.",
        "troubleshooting": (
            "Use one of the valid DocType values: DRIVERS_LICENSE, PAYSTUB, W2, "
            "TAX_RETURN, BUSINESS_TAX_RETURN, PROFIT_LOSS, BALANCE_SHEET, "
            "BANK_STATEMENT, INVESTMENT_STATEMENT, GIFT_LETTER, LOE, "
            "LEASE_AGREEMENT, FHA_CERT, VA_COE, DD214, BANKRUPTCY_DISCHARGE, "
            "PURCHASE_CONTRACT, APPRAISAL, TITLE_REPORT, HOMEOWNERS_INSURANCE, OTHER."
        ),
    },
    "INVALID_PROFILE_TYPE": {
        "status": "400",
        "description": "profile_type must be 'lead' or 'loan'.",
        "troubleshooting": "Only 'lead' and 'loan' are accepted as profile types for field extraction.",
    },
    "EXTRACTION_UNAVAILABLE": {
        "status": "400",
        "description": "Unable to retrieve document content for extraction.",
        "troubleshooting": (
            "Ensure the document has been uploaded to S3 and the storage_key "
            "is valid. Check S3 connectivity with GET /admin/s3-test."
        ),
    },
    "DISALLOWED_FIELD": {
        "status": "400",
        "description": "A field_name maps to a DB column not in the allowed whitelist.",
        "troubleshooting": "Only fields defined in FIELD_TO_LEAD_MAPPING or FIELD_TO_LOAN_MAPPING can be applied.",
    },
    "FILE_TOO_LARGE": {
        "status": "400",
        "description": "Uploaded file exceeds the maximum allowed size (default 50MB).",
        "troubleshooting": "Reduce file size or split multi-page documents.",
    },
    "UNSUPPORTED_MIME_TYPE": {
        "status": "400",
        "description": "File type is not in the allowed list for document upload.",
        "troubleshooting": (
            "Accepted types: application/pdf, image/jpeg, image/png, image/tiff, "
            "image/webp, application/vnd.openxmlformats-officedocument.wordprocessingml.document."
        ),
    },

    # 401 Unauthorized
    "TOKEN_EXPIRED": {
        "status": "401",
        "description": "The JWT token has expired.",
        "troubleshooting": "Obtain a new token via the login or magic-link endpoint.",
    },
    "TOKEN_INVALID": {
        "status": "401",
        "description": "The JWT token is malformed or has an invalid signature.",
        "troubleshooting": "Ensure the token is correctly copied and has not been truncated.",
    },
    "PORTAL_TOKEN_REQUIRED": {
        "status": "401",
        "description": "Portal endpoints require a portal JWT token.",
        "troubleshooting": (
            "Pass the portal token via X-Portal-Token header, "
            "Authorization: Bearer header, or ?token= query parameter."
        ),
    },

    # 403 Forbidden
    "ADMIN_REQUIRED": {
        "status": "403",
        "description": "Endpoint requires admin or site_admin permission_role.",
        "troubleshooting": "Contact your administrator for elevated access.",
    },
    "WRITE_SCOPE_REQUIRED": {
        "status": "403",
        "description": "Portal token has read_only scope; this operation requires read_write.",
        "troubleshooting": "Request a new portal link with write permissions.",
    },
    "MAKER_CHECKER_VIOLATION": {
        "status": "403",
        "description": "The approver cannot be the same user who created the calculation.",
        "troubleshooting": "A different user must approve the income calculation.",
    },

    # 404 Not Found
    "LOAN_NOT_FOUND": {
        "status": "404",
        "description": "Loan not found or not accessible by the current user's organization.",
        "troubleshooting": (
            "Verify the loan_id exists and belongs to the authenticated user's "
            "organization. Note: tenant isolation may return 404 instead of 403 "
            "to prevent information disclosure."
        ),
    },
    "DOCUMENT_NOT_FOUND": {
        "status": "404",
        "description": "Document not found by the given document_id.",
        "troubleshooting": "Verify the document_id. Deleted documents return 404.",
    },
    "REQUEST_NOT_FOUND": {
        "status": "404",
        "description": "Document request not found by the given request_id.",
        "troubleshooting": "Verify the request_id. Ensure it belongs to an accessible loan.",
    },
    "EXTRACTION_NOT_FOUND": {
        "status": "404",
        "description": "No extraction found for this document. Trigger extraction first.",
        "troubleshooting": "Call POST /document/{document_id}/extract before accessing extraction data.",
    },
    "ANALYSIS_NOT_FOUND": {
        "status": "404",
        "description": "No bank statement analysis found for this loan.",
        "troubleshooting": "Run POST /bank-analysis/analyze/{loan_id} first.",
    },
    "ENVELOPE_NOT_FOUND": {
        "status": "404",
        "description": "E-signature envelope not found.",
        "troubleshooting": "Verify the envelope_id is correct.",
    },

    # 422 Unprocessable Entity
    "ANALYSIS_FAILED": {
        "status": "422",
        "description": "Bank statement analysis could not complete.",
        "troubleshooting": (
            "Ensure bank statement documents are uploaded for the loan and "
            "are in a supported format (PDF). Re-upload if documents are corrupt."
        ),
    },
    "INCOME_CALC_FAILED": {
        "status": "422",
        "description": "Income calculation could not complete.",
        "troubleshooting": "Ensure paystubs, W-2s, or tax returns are uploaded and classified.",
    },
    "CLASSIFICATION_FAILED": {
        "status": "422",
        "description": "AI classification could not determine document type.",
        "troubleshooting": "Try re-uploading a clearer version of the document.",
    },

    # 429 Too Many Requests
    "RATE_LIMITED": {
        "status": "429",
        "description": "Request rate limit exceeded.",
        "troubleshooting": (
            "Wait for the duration specified in the Retry-After header before "
            "retrying. See the Rate Limiting section for per-endpoint limits."
        ),
    },

    # 500 Internal Server Error
    "EXTRACTION_FAILED": {
        "status": "500",
        "description": "Document data extraction failed due to an internal error.",
        "troubleshooting": "Retry the extraction. If the issue persists, contact support.",
    },
    "S3_UPLOAD_FAILED": {
        "status": "500",
        "description": "Failed to upload file to S3 storage.",
        "troubleshooting": "Check S3 connectivity with GET /admin/s3-test. Retry the upload.",
    },

    # 501 Not Implemented
    "SERVICE_UNAVAILABLE": {
        "status": "501",
        "description": "Required service module is not yet deployed.",
        "troubleshooting": (
            "This feature depends on a service that is not available in the "
            "current deployment. Contact the platform team."
        ),
    },
}


# =============================================================================
# WEBHOOK EVENT DOCUMENTATION
# =============================================================================

WEBHOOK_EVENTS: Dict[str, Dict[str, Any]] = {
    "document.uploaded": {
        "description": "Fired when a new document is uploaded (via internal API or portal).",
        "payload_example": {
            "event": "document.uploaded",
            "timestamp": "2026-03-12T14:30:00Z",
            "data": {
                "document_id": 1042,
                "loan_id": 146,
                "borrower_id": 574,
                "doc_type": "PAYSTUB",
                "file_name": "march_paystub.pdf",
                "file_size": 245760,
                "upload_source": "WEB",
                "organization_id": 12,
            },
        },
    },
    "document.approved": {
        "description": "Fired when a document is approved by a reviewer or auto-approved by AI.",
        "payload_example": {
            "event": "document.approved",
            "timestamp": "2026-03-12T15:00:00Z",
            "data": {
                "document_id": 1042,
                "loan_id": 146,
                "request_id": 305,
                "reviewed_by": "jsmith",
                "auto_approved": False,
                "organization_id": 12,
            },
        },
    },
    "document.rejected": {
        "description": "Fired when a document is rejected with a reason and fix instructions.",
        "payload_example": {
            "event": "document.rejected",
            "timestamp": "2026-03-12T15:05:00Z",
            "data": {
                "document_id": 1043,
                "loan_id": 146,
                "request_id": 306,
                "rejection_category": "SCREENSHOT",
                "rejection_reason": "Document appears to be a screenshot. Please upload the original PDF.",
                "fix_instructions": "Download the original PDF from your payroll provider and upload it directly.",
                "organization_id": 12,
            },
        },
    },
    "document.expired": {
        "description": "Fired when a document's freshness window expires (e.g., paystub older than 30 days).",
        "payload_example": {
            "event": "document.expired",
            "timestamp": "2026-03-12T06:00:00Z",
            "data": {
                "document_id": 980,
                "loan_id": 146,
                "request_id": 290,
                "doc_type": "PAYSTUB",
                "expired_at": "2026-03-12T00:00:00Z",
                "days_overdue": 2,
                "auto_renewal_request_created": True,
                "new_request_id": 320,
                "organization_id": 12,
            },
        },
    },
    "needs_list.generated": {
        "description": "Fired when a needs list is generated for a loan.",
        "payload_example": {
            "event": "needs_list.generated",
            "timestamp": "2026-03-12T10:00:00Z",
            "data": {
                "loan_id": 146,
                "borrower_id": 574,
                "loan_program": "CONVENTIONAL",
                "request_count": 12,
                "critical_count": 3,
                "organization_id": 12,
            },
        },
    },
    "esign.envelope_completed": {
        "description": "Fired when all recipients have signed an e-signature envelope.",
        "payload_example": {
            "event": "esign.envelope_completed",
            "timestamp": "2026-03-12T16:45:00Z",
            "data": {
                "envelope_id": 55,
                "loan_id": 146,
                "title": "Initial Disclosure Package",
                "recipient_count": 2,
                "completed_at": "2026-03-12T16:45:00Z",
                "organization_id": 12,
            },
        },
    },
    "followup.campaign_completed": {
        "description": "Fired when a follow-up campaign completes all scheduled steps.",
        "payload_example": {
            "event": "followup.campaign_completed",
            "timestamp": "2026-03-12T09:00:00Z",
            "data": {
                "campaign_id": 78,
                "loan_id": 146,
                "campaign_type": "GENTLE_REMINDER",
                "total_steps": 4,
                "responses_received": 1,
                "organization_id": 12,
            },
        },
    },
    "income.calculation_approved": {
        "description": "Fired when an income calculation is approved via the maker-checker workflow.",
        "payload_example": {
            "event": "income.calculation_approved",
            "timestamp": "2026-03-12T11:30:00Z",
            "data": {
                "calculation_id": 42,
                "loan_id": 146,
                "borrower_id": 574,
                "total_monthly_income": 8750.00,
                "approved_by": "mwilliams",
                "organization_id": 12,
            },
        },
    },
    "bank_analysis.completed": {
        "description": "Fired when bank statement analysis completes for a loan.",
        "payload_example": {
            "event": "bank_analysis.completed",
            "timestamp": "2026-03-12T13:15:00Z",
            "data": {
                "loan_id": 146,
                "borrower_id": 574,
                "risk_score": 35.2,
                "risk_level": "medium",
                "large_deposit_count": 2,
                "nsf_event_count": 0,
                "organization_id": 12,
            },
        },
    },
}

WEBHOOK_SECURITY = {
    "signature_verification": {
        "header": "X-Webhook-Signature",
        "algorithm": "HMAC-SHA256",
        "description": (
            "Each webhook request includes an ``X-Webhook-Signature`` header "
            "containing an HMAC-SHA256 signature of the raw request body. "
            "Verify by computing ``HMAC-SHA256(webhook_secret, raw_body)`` "
            "and comparing to the header value using constant-time comparison."
        ),
        "example_verification": (
            "import hmac, hashlib\n"
            "expected = hmac.new(webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()\n"
            "is_valid = hmac.compare_digest(expected, request.headers['X-Webhook-Signature'])"
        ),
    },
    "retry_policy": {
        "max_retries": 5,
        "backoff": "Exponential: 1s, 2s, 4s, 8s, 16s",
        "timeout": "10 seconds per attempt",
        "success_codes": [200, 201, 202, 204],
        "description": (
            "Failed webhook deliveries are retried up to 5 times with "
            "exponential backoff. A delivery is considered failed if the "
            "endpoint returns a non-2xx status code or the request times out."
        ),
    },
}


# =============================================================================
# RESPONSE EXAMPLES
# =============================================================================

RESPONSE_EXAMPLES: Dict[str, Dict[int, Dict[str, Any]]] = {

    # -------------------------------------------------------------------------
    # Document Management
    # -------------------------------------------------------------------------
    "needs_list_generate": {
        200: {
            "description": "Needs list generated successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "loan_id": 146,
                        "borrower_id": 574,
                        "loan_program": "CONVENTIONAL",
                        "occupancy_type": "PRIMARY",
                        "income_type": "W2",
                        "requests_created": 12,
                        "requests": [
                            {
                                "id": 301,
                                "doc_type": "DRIVERS_LICENSE",
                                "title": "Government Photo ID",
                                "description": "Valid government-issued photo ID (driver's license, passport, or state ID).",
                                "priority": "CRITICAL",
                                "applies_to": "BORROWER",
                                "freshness_days": None,
                                "auto_renew": False,
                                "status": "OPEN",
                            },
                            {
                                "id": 302,
                                "doc_type": "PAYSTUB",
                                "title": "Most Recent Paystub",
                                "description": "Most recent 30-day paystub showing YTD earnings.",
                                "priority": "CRITICAL",
                                "applies_to": "BORROWER",
                                "freshness_days": 30,
                                "auto_renew": True,
                                "status": "OPEN",
                            },
                            {
                                "id": 303,
                                "doc_type": "W2",
                                "title": "W-2 (Most Recent Year)",
                                "description": "Most recent year W-2 form from all employers.",
                                "priority": "HIGH",
                                "applies_to": "BORROWER",
                                "freshness_days": 365,
                                "auto_renew": False,
                                "status": "OPEN",
                            },
                            {
                                "id": 304,
                                "doc_type": "BANK_STATEMENT",
                                "title": "Bank Statements (2 Months)",
                                "description": "Most recent 2 months of bank statements for all accounts.",
                                "priority": "HIGH",
                                "applies_to": "BORROWER",
                                "freshness_days": 60,
                                "auto_renew": True,
                                "status": "OPEN",
                            },
                        ],
                    },
                },
            },
        },
        422: {
            "description": "Invalid loan program or missing required fields.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "loc": ["body", "loan_program"],
                                "msg": "value is not a valid enumeration member",
                                "type": "value_error",
                            }
                        ],
                    },
                },
            },
        },
    },

    "document_upload": {
        200: {
            "description": "Document uploaded and processed successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "document_id": 1042,
                        "loan_id": 146,
                        "borrower_id": 574,
                        "file_name": "march_paystub.pdf",
                        "file_size": 245760,
                        "mime_type": "application/pdf",
                        "storage_key": "org_12/loan_146/borrower_574/1042_march_paystub.pdf",
                        "doc_type": "PAYSTUB",
                        "status": "PROCESSING",
                        "processing_result": {
                            "detected_doc_type": "PAYSTUB",
                            "classification_confidence": 0.97,
                            "detected_is_screenshot": False,
                            "screenshot_confidence": 0.05,
                            "extracted_dates": {
                                "payDate": "2026-03-01",
                                "periodStart": "2026-02-16",
                                "periodEnd": "2026-02-28",
                            },
                            "doc_date": "2026-03-01",
                            "is_expired": False,
                            "days_until_expiration": 19,
                            "decision": "ACCEPT",
                            "decision_reasons": ["Valid document type", "Within freshness window", "Not a screenshot"],
                        },
                        "request_id": 302,
                        "request_status": "PENDING_REVIEW",
                    },
                },
            },
        },
        400: {
            "description": "Invalid file or missing required parameters.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "File type 'text/plain' is not supported. Accepted: application/pdf, image/jpeg, image/png, image/tiff.",
                    },
                },
            },
        },
    },

    "document_approve": {
        200: {
            "description": "Document approved successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "document_id": 1042,
                        "status": "APPROVED",
                        "approved_by": "jsmith",
                        "approved_at": "2026-03-12T15:00:00.000000",
                        "notes": "Income verified against W-2.",
                        "message": "Document approved successfully",
                    },
                },
            },
        },
        404: {
            "description": "Document not found.",
            "content": {
                "application/json": {
                    "example": {"detail": "Document not found"},
                },
            },
        },
    },

    "document_reject": {
        200: {
            "description": "Document rejected with reason.",
            "content": {
                "application/json": {
                    "example": {
                        "document_id": 1043,
                        "status": "REJECTED",
                        "rejection_reason": "Document appears to be a screenshot. Please upload the original PDF from your payroll provider.",
                        "rejection_category": "SCREENSHOT",
                        "rejected_by": "mwilliams",
                        "rejected_at": "2026-03-12T15:05:00.000000",
                        "message": "Document rejected successfully",
                    },
                },
            },
        },
    },

    "document_delete": {
        200: {
            "description": "Document soft-deleted.",
            "content": {
                "application/json": {
                    "example": {
                        "document_id": 1043,
                        "status": "DELETED",
                        "previous_status": "REJECTED",
                        "deleted_by": "jsmith",
                        "deleted_at": "2026-03-12T15:10:00.000000",
                        "message": "Document deleted successfully",
                    },
                },
            },
        },
    },

    "document_re_request": {
        200: {
            "description": "Document re-requested, linked documents superseded.",
            "content": {
                "application/json": {
                    "example": {
                        "request_id": 302,
                        "status": "OPEN",
                        "previous_status": "REJECTED",
                        "re_requested_by": "jsmith",
                        "re_requested_at": "2026-03-12T15:15:00.000000",
                        "due_date": "2026-03-19T15:15:00.000000",
                        "superseded_documents": 1,
                        "notification_sent": True,
                        "notes": "Paystub was a screenshot; requested original.",
                        "message": "Document re-requested successfully",
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Income Calculation
    # -------------------------------------------------------------------------
    "income_calculate": {
        200: {
            "description": "Income calculated successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "calculation_id": 42,
                        "loan_id": 146,
                        "borrower_id": 574,
                        "status": "PENDING_REVIEW",
                        "total_monthly_income": 8750.00,
                        "sources": [
                            {
                                "source_type": "W2",
                                "employer_name": "Acme Corporation",
                                "annual_amount": 95000.00,
                                "monthly_amount": 7916.67,
                                "confidence": 0.95,
                                "document_ids": [1042, 1044],
                            },
                            {
                                "source_type": "OVERTIME",
                                "employer_name": "Acme Corporation",
                                "annual_amount": 10000.00,
                                "monthly_amount": 833.33,
                                "confidence": 0.88,
                                "note": "2-year average used per Fannie Mae guidelines.",
                                "document_ids": [1042],
                            },
                        ],
                        "dti_analysis": {
                            "monthly_income": 8750.00,
                            "monthly_debt": 2100.00,
                            "front_end_ratio": 24.0,
                            "back_end_ratio": 24.0,
                            "qualifying_ratio": 24.0,
                        },
                    },
                },
            },
        },
    },

    "income_approve": {
        200: {
            "description": "Income calculation approved.",
            "content": {
                "application/json": {
                    "example": {
                        "calculation_id": 42,
                        "status": "APPROVED",
                        "approved_by": "mwilliams",
                        "approved_at": "2026-03-12T16:00:00Z",
                        "total_monthly_income": 8750.00,
                        "message": "Income calculation approved",
                    },
                },
            },
        },
        403: {
            "description": "Maker-checker violation: approver is the same user who calculated.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Cannot approve your own calculation. A different user must review.",
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # E-Signature
    # -------------------------------------------------------------------------
    "esign_create_envelope": {
        201: {
            "description": "Envelope created successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "envelope_id": 55,
                        "status": "DRAFT",
                        "title": "Initial Disclosure Package",
                        "loan_id": 146,
                        "created_by": "jsmith",
                        "created_at": "2026-03-12T10:00:00Z",
                        "recipients": [
                            {
                                "recipient_id": 101,
                                "email": "john.borrower@email.com",
                                "name": "John Borrower",
                                "role": "SIGNER",
                                "order": 1,
                                "status": "PENDING",
                                "auth_method": "EMAIL",
                            },
                            {
                                "recipient_id": 102,
                                "email": "jane.coborrower@email.com",
                                "name": "Jane Co-Borrower",
                                "role": "SIGNER",
                                "order": 2,
                                "status": "PENDING",
                                "auth_method": "KBA",
                            },
                        ],
                        "fields": [
                            {
                                "field_id": 201,
                                "field_type": "SIGNATURE",
                                "page": 3,
                                "x": 72,
                                "y": 600,
                                "width": 200,
                                "height": 50,
                                "recipient_id": 101,
                                "required": True,
                            },
                        ],
                        "signing_urls": None,
                        "message": "Envelope created. Send to generate signing URLs.",
                    },
                },
            },
        },
    },

    "esign_send_envelope": {
        200: {
            "description": "Envelope sent to all recipients.",
            "content": {
                "application/json": {
                    "example": {
                        "envelope_id": 55,
                        "status": "SENT",
                        "sent_at": "2026-03-12T10:05:00Z",
                        "recipients": [
                            {
                                "recipient_id": 101,
                                "email": "john.borrower@email.com",
                                "signing_url": "https://api.perenniaai.com/api/v1/esign/sign?token=eyJ...",
                                "notification_sent": True,
                            },
                        ],
                        "expires_at": "2026-03-19T10:05:00Z",
                    },
                },
            },
        },
    },

    "esign_signing_session": {
        200: {
            "description": "Signing session loaded with document and fields.",
            "content": {
                "application/json": {
                    "example": {
                        "envelope_id": 55,
                        "recipient_id": 101,
                        "recipient_name": "John Borrower",
                        "title": "Initial Disclosure Package",
                        "document_url": "https://perennia-smart-docs.s3.amazonaws.com/...",
                        "fields": [
                            {
                                "field_id": 201,
                                "field_type": "SIGNATURE",
                                "page": 3,
                                "x": 72,
                                "y": 600,
                                "width": 200,
                                "height": 50,
                                "required": True,
                                "completed": False,
                            },
                        ],
                        "consent_required": True,
                        "kba_required": False,
                    },
                },
            },
        },
    },

    "esign_audit_trail": {
        200: {
            "description": "Cryptographic audit trail for the envelope.",
            "content": {
                "application/json": {
                    "example": {
                        "envelope_id": 55,
                        "events": [
                            {
                                "event_type": "CREATED",
                                "timestamp": "2026-03-12T10:00:00Z",
                                "actor": "jsmith",
                                "ip_address": "192.168.1.100",
                                "details": "Envelope created with 2 recipients.",
                            },
                            {
                                "event_type": "SENT",
                                "timestamp": "2026-03-12T10:05:00Z",
                                "actor": "jsmith",
                                "ip_address": "192.168.1.100",
                                "details": "Envelope sent to 2 recipients.",
                            },
                            {
                                "event_type": "VIEWED",
                                "timestamp": "2026-03-12T11:00:00Z",
                                "actor": "john.borrower@email.com",
                                "ip_address": "203.0.113.42",
                                "user_agent": "Mozilla/5.0...",
                                "details": "Recipient viewed the document.",
                            },
                            {
                                "event_type": "SIGNED",
                                "timestamp": "2026-03-12T11:05:00Z",
                                "actor": "john.borrower@email.com",
                                "ip_address": "203.0.113.42",
                                "details": "Recipient signed all required fields.",
                                "signature_hash": "sha256:a1b2c3d4...",
                            },
                        ],
                        "certificate_hash": "sha256:e5f6g7h8...",
                        "tamper_proof": True,
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Bank Statement Analysis
    # -------------------------------------------------------------------------
    "bank_analysis_analyze": {
        200: {
            "description": "Bank statement analysis completed.",
            "content": {
                "application/json": {
                    "example": {
                        "loan_id": 146,
                        "borrower_id": 574,
                        "analysis": {
                            "statement_count": 4,
                            "months_covered": 2,
                            "large_deposits": [
                                {
                                    "index": 0,
                                    "date": "2026-02-15",
                                    "amount": 5000.00,
                                    "description": "WIRE TRANSFER FROM SAVINGS",
                                    "risk_level": "medium",
                                    "sourcing_status": "unsourced",
                                },
                            ],
                            "nsf_events": [],
                            "irs_payments": [],
                            "payroll_deposits": [
                                {
                                    "date": "2026-03-01",
                                    "amount": 3958.33,
                                    "employer_match": "ACME CORP",
                                    "frequency": "semimonthly",
                                },
                            ],
                            "recurring_obligations": [],
                            "risk_score": 22.5,
                            "risk_level": "low",
                            "risk_flags": [],
                            "estimated_monthly_income": 7916.66,
                            "income_consistency_rating": "excellent",
                        },
                        "analyzed_at": "2026-03-12T13:15:00Z",
                    },
                },
            },
        },
    },

    "bank_analysis_large_deposits": {
        200: {
            "description": "Large deposits requiring sourcing.",
            "content": {
                "application/json": {
                    "example": {
                        "loan_id": 146,
                        "deposits": [
                            {
                                "index": 0,
                                "date": "2026-02-15",
                                "amount": 5000.00,
                                "description": "WIRE TRANSFER FROM SAVINGS",
                                "risk_level": "medium",
                                "sourcing_status": "unsourced",
                            },
                            {
                                "index": 1,
                                "date": "2026-01-20",
                                "amount": 3200.00,
                                "description": "CHECK DEPOSIT",
                                "risk_level": "low",
                                "sourcing_status": "sourced",
                                "explanation": "Tax refund deposit",
                                "sourced_by": "jsmith",
                            },
                        ],
                        "total_count": 2,
                        "total_unsourced_count": 1,
                        "total_unsourced_amount": 5000.00,
                    },
                },
            },
        },
    },

    "bank_analysis_risk_summary": {
        200: {
            "description": "Overall risk summary from bank analysis.",
            "content": {
                "application/json": {
                    "example": {
                        "loan_id": 146,
                        "overall_risk_score": 35.2,
                        "risk_level": "medium",
                        "flags": [
                            {
                                "flag_type": "large_unsourced_deposit",
                                "severity": "medium",
                                "description": "1 large deposit totaling $5,000.00 requires sourcing documentation.",
                                "recommendation": "Obtain gift letter or bank transfer records.",
                            },
                        ],
                        "recommendations": [
                            "Source the $5,000 wire transfer deposit from 02/15/2026.",
                        ],
                        "large_deposit_count": 2,
                        "nsf_event_count": 0,
                        "irs_payment_count": 0,
                        "undisclosed_debt_count": 0,
                        "income_consistency": "excellent",
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Document Intelligence
    # -------------------------------------------------------------------------
    "doc_intel_classify": {
        200: {
            "description": "Document classified successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "document_id": 1042,
                        "classification": {
                            "doc_type": "PAYSTUB",
                            "confidence": 0.97,
                            "alternatives": [
                                {"doc_type": "W2", "confidence": 0.02},
                                {"doc_type": "OTHER", "confidence": 0.01},
                            ],
                        },
                        "extracted_metadata": {
                            "employer_name": "Acme Corporation",
                            "pay_period_end": "2026-02-28",
                            "gross_pay": 3958.33,
                        },
                        "model": "gpt-4o-mini",
                    },
                },
            },
        },
    },

    "doc_intel_analyze_application": {
        200: {
            "description": "POS application analyzed for required documents.",
            "content": {
                "application/json": {
                    "example": {
                        "loan_id": 146,
                        "loan_program": "FHA",
                        "analysis": {
                            "required_documents": [
                                {
                                    "doc_type": "FHA_CERT",
                                    "reason": "FHA loan program requires FHA certification.",
                                    "priority": "CRITICAL",
                                },
                                {
                                    "doc_type": "PROFIT_LOSS",
                                    "reason": "Self-employment detected; YTD P&L required.",
                                    "priority": "HIGH",
                                },
                            ],
                            "total_required": 14,
                            "already_on_file": 3,
                            "new_requests_needed": 11,
                        },
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Document Security
    # -------------------------------------------------------------------------
    "doc_security_fraud_check": {
        200: {
            "description": "Fraud analysis completed.",
            "content": {
                "application/json": {
                    "example": {
                        "document_id": 1042,
                        "risk_score": 15.0,
                        "risk_level": "low",
                        "indicators": [],
                        "metadata_analysis": {
                            "creation_tool": "ADP Payroll",
                            "creation_date": "2026-03-01T08:00:00Z",
                            "modification_date": None,
                            "is_digitally_signed": True,
                            "font_consistency": True,
                        },
                        "checked_at": "2026-03-12T14:30:00Z",
                    },
                },
            },
        },
    },

    "doc_security_access_log": {
        200: {
            "description": "Access log retrieved.",
            "content": {
                "application/json": {
                    "example": {
                        "document_id": 1042,
                        "total_accesses": 5,
                        "accesses": [
                            {
                                "access_type": "VIEW",
                                "user_id": "jsmith",
                                "ip_address": "192.168.1.100",
                                "user_agent": "Mozilla/5.0...",
                                "accessed_at": "2026-03-12T14:30:00Z",
                            },
                            {
                                "access_type": "DOWNLOAD",
                                "user_id": "mwilliams",
                                "ip_address": "192.168.1.101",
                                "user_agent": "Mozilla/5.0...",
                                "accessed_at": "2026-03-12T15:00:00Z",
                            },
                        ],
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Document Analytics
    # -------------------------------------------------------------------------
    "doc_analytics_dashboard": {
        200: {
            "description": "Main document analytics dashboard.",
            "content": {
                "application/json": {
                    "example": {
                        "period": {"start": "2026-02-12", "end": "2026-03-12"},
                        "summary": {
                            "total_documents": 342,
                            "documents_uploaded": 128,
                            "documents_approved": 95,
                            "documents_rejected": 18,
                            "documents_pending": 15,
                            "approval_rate": 84.1,
                            "avg_review_time_hours": 4.2,
                        },
                        "needs_list": {
                            "total_requests": 456,
                            "fulfilled": 380,
                            "open": 52,
                            "waived": 14,
                            "overdue": 10,
                            "fulfillment_rate": 83.3,
                        },
                        "ai_performance": {
                            "auto_approved": 72,
                            "auto_rejected": 8,
                            "sent_to_review": 48,
                            "auto_approval_rate": 56.3,
                            "classification_accuracy": 94.7,
                        },
                    },
                },
            },
        },
    },

    "doc_analytics_sla_compliance": {
        200: {
            "description": "Document SLA compliance metrics.",
            "content": {
                "application/json": {
                    "example": {
                        "period": {"start": "2026-02-12", "end": "2026-03-12"},
                        "sla_target_hours": 24,
                        "total_reviews": 113,
                        "within_sla": 98,
                        "sla_compliance_pct": 86.7,
                        "avg_review_hours": 6.8,
                        "p50_review_hours": 3.2,
                        "p95_review_hours": 18.5,
                        "by_doc_type": [
                            {"doc_type": "PAYSTUB", "avg_hours": 2.1, "compliance_pct": 95.0},
                            {"doc_type": "TAX_RETURN", "avg_hours": 12.4, "compliance_pct": 78.0},
                        ],
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Follow-up & Scheduling
    # -------------------------------------------------------------------------
    "followup_create_campaign": {
        201: {
            "description": "Follow-up campaign created.",
            "content": {
                "application/json": {
                    "example": {
                        "campaign_id": 78,
                        "loan_id": 146,
                        "campaign_type": "GENTLE_REMINDER",
                        "status": "PENDING",
                        "steps": [
                            {"step": 1, "channel": "email", "delay_hours": 0, "template": "gentle_reminder_1"},
                            {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_reminder_sms"},
                            {"step": 3, "channel": "email", "delay_hours": 120, "template": "gentle_reminder_2"},
                        ],
                        "max_reminders": 5,
                        "created_at": "2026-03-12T10:00:00Z",
                    },
                },
            },
        },
    },

    "followup_create_appointment": {
        201: {
            "description": "Document appointment created.",
            "content": {
                "application/json": {
                    "example": {
                        "appointment_id": 33,
                        "loan_id": 146,
                        "appointment_type": "DOCUMENT_REVIEW",
                        "title": "Document Review - Missing Bank Statements",
                        "scheduled_at": "2026-03-15T14:00:00Z",
                        "duration_minutes": 30,
                        "location_type": "VIDEO",
                        "meeting_url": "https://meet.perenniaai.com/doc-review/abc123",
                        "status": "SCHEDULED",
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Borrower Portal
    # -------------------------------------------------------------------------
    "portal_checklist": {
        200: {
            "description": "Borrower document checklist with progress.",
            "content": {
                "application/json": {
                    "example": {
                        "loan_id": 146,
                        "borrower_name": "John Borrower",
                        "progress": {
                            "total_requests": 12,
                            "completed": 8,
                            "pending": 3,
                            "rejected": 1,
                            "waived": 0,
                            "completion_pct": 66.7,
                        },
                        "categories": {
                            "identity": {
                                "label": "Identity Documents",
                                "items": [
                                    {
                                        "request_id": 301,
                                        "title": "Government Photo ID",
                                        "status": "ACCEPTED",
                                        "doc_type": "DRIVERS_LICENSE",
                                        "uploaded_document": {
                                            "document_id": 1040,
                                            "file_name": "drivers_license.jpg",
                                            "status": "APPROVED",
                                        },
                                    },
                                ],
                            },
                            "income": {
                                "label": "Income Documents",
                                "items": [
                                    {
                                        "request_id": 302,
                                        "title": "Most Recent Paystub",
                                        "status": "REJECTED",
                                        "rejection_reason": "Screenshot detected. Please upload the original PDF.",
                                        "doc_type": "PAYSTUB",
                                    },
                                ],
                            },
                        },
                    },
                },
            },
        },
        401: {
            "description": "Invalid or missing portal token.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid or expired portal token."},
                },
            },
        },
    },

    "portal_upload": {
        200: {
            "description": "Document uploaded via portal.",
            "content": {
                "application/json": {
                    "example": {
                        "document_id": 1045,
                        "request_id": 302,
                        "file_name": "paystub_march_2026.pdf",
                        "status": "PROCESSING",
                        "message": "Document uploaded successfully. We will review it shortly.",
                    },
                },
            },
        },
        429: {
            "description": "Upload rate limit exceeded.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Upload rate limit exceeded. Please wait before uploading again.",
                    },
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Enterprise Config
    # -------------------------------------------------------------------------
    "config_list_rules": {
        200: {
            "description": "Business rules for the organization.",
            "content": {
                "application/json": {
                    "example": {
                        "rules": [
                            {
                                "rule_key": "paystub_freshness_days",
                                "category": "freshness",
                                "value": 30,
                                "description": "Maximum age in days for paystub documents.",
                                "source": "fannie_mae",
                                "effective_date": "2026-01-01",
                                "expiration_date": None,
                            },
                            {
                                "rule_key": "bank_statement_freshness_days",
                                "category": "freshness",
                                "value": 60,
                                "description": "Maximum age in days for bank statement documents.",
                                "source": "fannie_mae",
                                "effective_date": "2026-01-01",
                                "expiration_date": None,
                            },
                            {
                                "rule_key": "screenshot_rejection_threshold",
                                "category": "validation",
                                "value": 0.85,
                                "description": "Confidence threshold above which screenshots are auto-rejected.",
                                "source": "internal",
                                "effective_date": "2026-01-01",
                                "expiration_date": None,
                            },
                            {
                                "rule_key": "large_deposit_threshold_pct",
                                "category": "bank_analysis",
                                "value": 50,
                                "description": "Percentage of qualifying monthly income above which deposits require sourcing.",
                                "source": "fannie_mae",
                                "effective_date": "2026-01-01",
                                "expiration_date": None,
                            },
                        ],
                        "total": 4,
                    },
                },
            },
        },
    },

    "config_update_rule": {
        200: {
            "description": "Business rule updated.",
            "content": {
                "application/json": {
                    "example": {
                        "rule_key": "paystub_freshness_days",
                        "previous_value": 30,
                        "new_value": 45,
                        "updated_by": "admin@company.com",
                        "effective_date": "2026-04-01",
                        "message": "Rule updated successfully.",
                    },
                },
            },
        },
        403: {
            "description": "Admin access required.",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required"},
                },
            },
        },
    },

    # -------------------------------------------------------------------------
    # Common Error Responses
    # -------------------------------------------------------------------------
    "common_401": {
        401: {
            "description": "Authentication failed.",
            "content": {
                "application/json": {
                    "example": {"detail": "Could not validate credentials."},
                },
            },
        },
    },

    "common_403": {
        403: {
            "description": "Insufficient permissions.",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required"},
                },
            },
        },
    },

    "common_404": {
        404: {
            "description": "Resource not found (or tenant isolation).",
            "content": {
                "application/json": {
                    "example": {"detail": "Not found"},
                },
            },
        },
    },

    "common_429": {
        429: {
            "description": "Rate limit exceeded.",
            "content": {
                "application/json": {
                    "example": {"detail": "Rate limit exceeded. Retry after 30 seconds."},
                },
            },
        },
    },
}


# =============================================================================
# REQUEST BODY EXAMPLES
# =============================================================================

REQUEST_EXAMPLES: Dict[str, Dict[str, Any]] = {

    "generate_needs_list": {
        "summary": "Generate a conventional purchase needs list",
        "value": {
            "loan_id": 146,
            "loan_program": "CONVENTIONAL",
            "occupancy_type": "PRIMARY",
            "income_type": "W2",
            "borrower_id": 574,
            "co_borrower_id": 575,
            "has_gift_funds": False,
            "is_self_employed": False,
            "has_bankruptcy": False,
            "property_type": "SINGLE_FAMILY",
        },
    },

    "generate_needs_list_fha_self_employed": {
        "summary": "Generate an FHA self-employed needs list",
        "value": {
            "loan_id": 147,
            "loan_program": "FHA",
            "occupancy_type": "PRIMARY",
            "income_type": "SELF_EMPLOYED",
            "borrower_id": 576,
            "co_borrower_id": None,
            "has_gift_funds": True,
            "is_self_employed": True,
            "has_bankruptcy": True,
            "property_type": "CONDO",
        },
    },

    "generate_needs_list_va": {
        "summary": "Generate a VA purchase needs list",
        "value": {
            "loan_id": 148,
            "loan_program": "VA",
            "occupancy_type": "PRIMARY",
            "income_type": "W2",
            "borrower_id": 577,
            "has_gift_funds": False,
            "is_self_employed": False,
            "has_bankruptcy": False,
        },
    },

    "add_custom_request": {
        "summary": "Add a custom document request with notification",
        "value": {
            "title": "Divorce Decree",
            "description": "Final divorce decree with property settlement agreement.",
            "instructions": "Upload all pages including the judge's signature page.",
            "priority": "HIGH",
            "due_date": "2026-03-19T00:00:00Z",
            "send_notification": True,
            "borrower_email": "john.borrower@email.com",
            "borrower_name": "John Borrower",
        },
    },

    "waive_request": {
        "summary": "Waive a document requirement",
        "value": {
            "reason": "Borrower provided verbal VOE; written VOE waived per underwriter approval.",
            "waived_by": "mwilliams",
        },
    },

    "reject_document": {
        "summary": "Reject a document with category",
        "value": {
            "reviewer": "mwilliams",
            "reason": "Document appears to be a screenshot of a mobile banking app. Please upload the official bank statement PDF.",
            "rejection_category": "SCREENSHOT",
        },
    },

    "approve_document_with_review": {
        "summary": "Approve a document and apply extracted fields",
        "value": {
            "reviewer": "mwilliams",
            "assigned_owner": "BORROWER",
            "apply_fields": {
                "profile_type": "lead",
                "profile_id": 1234,
                "fields_to_apply": [
                    {"field_name": "employer_name", "action": "replace", "value": "Acme Corporation"},
                    {"field_name": "annual_income", "action": "add", "value": "95000"},
                    {"field_name": "ssn", "action": "ignore"},
                ],
            },
            "notes": "Income verified against paystub and W-2.",
        },
    },

    "create_esign_envelope": {
        "summary": "Create an e-signature envelope",
        "value": {
            "loan_id": 146,
            "title": "Initial Disclosure Package",
            "message": "Please review and sign the attached disclosures.",
            "recipients": [
                {
                    "email": "john.borrower@email.com",
                    "name": "John Borrower",
                    "role": "SIGNER",
                    "order": 1,
                    "auth_method": "EMAIL",
                },
                {
                    "email": "jane.coborrower@email.com",
                    "name": "Jane Co-Borrower",
                    "role": "SIGNER",
                    "order": 2,
                    "auth_method": "KBA",
                },
            ],
            "document_ids": [1042, 1044],
            "expiration_days": 7,
        },
    },

    "source_large_deposit": {
        "summary": "Mark a large deposit as sourced",
        "value": {
            "explanation": "Wire transfer from borrower's savings account at Chase Bank. Account statement attached.",
            "supporting_document_id": 1050,
            "sourced_by": "jsmith",
        },
    },

    "compare_income": {
        "summary": "Compare stated vs deposit income",
        "value": {
            "stated_monthly_income": 8500.00,
        },
    },

    "create_followup_campaign": {
        "summary": "Create a gentle reminder campaign",
        "value": {
            "loan_id": 146,
            "borrower_id": 574,
            "campaign_type": "GENTLE_REMINDER",
            "request_ids": [302, 304],
            "trigger_source": "manual",
            "max_reminders": 5,
        },
    },

    "create_appointment": {
        "summary": "Schedule a document review appointment",
        "value": {
            "loan_id": 146,
            "borrower_id": 574,
            "appointment_type": "DOCUMENT_REVIEW",
            "title": "Review Missing Bank Statements",
            "description": "Walk through remaining document requirements.",
            "scheduled_at": "2026-03-15T14:00:00Z",
            "duration_minutes": 30,
            "location_type": "VIDEO",
        },
    },

    "update_business_rule": {
        "summary": "Update paystub freshness requirement",
        "value": {
            "value": 45,
            "effective_date": "2026-04-01",
            "expiration_date": None,
            "source": "internal_policy_update",
            "description": "Extended freshness window for Q2 2026 volume push.",
        },
    },

    "log_document_access": {
        "summary": "Log a document access event",
        "value": {
            "document_id": 1042,
            "document_type": "smart_document",
            "access_type": "VIEW",
            "accessed_by": "jsmith",
            "reason": "Reviewing for income verification.",
        },
    },

    "sync_application_documents": {
        "summary": "Sync document requirements from loan application",
        "value": {
            "loan_id": 146,
            "workspace_slug": "borrower-portal-abc",
            "borrower_first_name": "John",
            "co_borrower_first_name": "Jane",
            "documents": [
                {
                    "id": "paystubs",
                    "name": "Recent Paystubs",
                    "description": "Most recent 30 days of paystubs.",
                    "category": "income",
                    "stage": "APPLICATION",
                },
                {
                    "id": "bank_statements",
                    "name": "Bank Statements",
                    "description": "2 most recent months.",
                    "category": "assets",
                    "stage": "APPLICATION",
                },
            ],
        },
    },
}


# =============================================================================
# SCHEMA DESCRIPTIONS
# =============================================================================

SCHEMA_FIELD_DESCRIPTIONS: Dict[str, Dict[str, str]] = {

    "GenerateNeedsListRequest": {
        "loan_id": "Unique identifier of the loan in the loans table.",
        "loan_program": "Loan program type. One of: CONVENTIONAL, FHA, VA, USDA.",
        "occupancy_type": "Property occupancy type. One of: PRIMARY, SECOND_HOME, INVESTMENT.",
        "income_type": "Primary income type. One of: W2, SELF_EMPLOYED, RETIREMENT.",
        "borrower_id": "Unique identifier of the primary borrower in borrower_profiles.",
        "co_borrower_id": "Optional co-borrower ID. When provided, generates co-borrower-specific requests.",
        "has_gift_funds": "Whether the borrower is using gift funds. Adds gift letter requirement.",
        "is_self_employed": "Whether the borrower is self-employed. Adds P&L, business tax returns.",
        "has_bankruptcy": "Whether the borrower has prior bankruptcy. Adds discharge papers requirement.",
        "property_type": "Optional property type for property-specific requirements.",
    },

    "SmartDocument": {
        "id": "Auto-increment primary key.",
        "request_id": "FK to smart_document_requests. Links upload to the requirement it fulfills.",
        "loan_id": "FK to loans table. Used for tenant isolation and organization scoping.",
        "borrower_id": "FK to borrower_profiles. Identifies the document owner.",
        "file_name": "Sanitized file name stored in S3.",
        "original_filename": "Original file name as uploaded by the user.",
        "mime_type": "MIME type (e.g., application/pdf, image/jpeg).",
        "file_size": "File size in bytes.",
        "storage_key": "S3 object key. Format: org_{id}/loan_{id}/borrower_{id}/{doc_id}_{filename}.",
        "page_count": "Number of pages (PDF only).",
        "doc_type": "Document type enum (PAYSTUB, W2, BANK_STATEMENT, etc.).",
        "detected_doc_type": "AI-detected document type string.",
        "detected_is_screenshot": "True if the document was detected as a screenshot.",
        "screenshot_confidence": "Screenshot detection confidence (0.0 to 1.0).",
        "screenshot_reasons": "JSON array of detection layer results explaining the screenshot decision.",
        "extracted_dates": "JSON object with extracted date fields: payDate, periodEnd, statementEnd.",
        "extracted_names": "JSON array of names found in the document.",
        "extracted_employer": "Employer name extracted from paystubs/W-2s.",
        "extracted_account_number": "Last 4 digits of account number (bank statements).",
        "extracted_amount": "Primary monetary amount extracted (e.g., gross pay, account balance).",
        "extraction_confidence": "Overall extraction confidence (0.0 to 1.0).",
        "ocr_text": "Full OCR text extracted from the document.",
        "doc_date": "Primary date on the document (pay date, statement date).",
        "doc_expires_at": "When the document's freshness expires based on doc_date + freshness_days.",
        "is_expired": "True if the document date exceeds the freshness window.",
        "days_until_expiration": "Days remaining until freshness expiration. Negative if expired.",
        "status": (
            "Document lifecycle status. One of: UPLOADED, SCANNING, PROCESSING, "
            "APPROVED, REJECTED, EXPIRED, DELETED, SUPERSEDED."
        ),
        "decision": "Automated review decision enum: ACCEPT, REJECT, NEEDS_REVIEW.",
        "decision_reasons": "JSON array of reasons for the automated decision.",
        "rejection_reason": "Human-readable rejection reason.",
        "rejection_category": "Rejection category enum: SCREENSHOT, EXPIRED, POOR_QUALITY, INCOMPLETE, WRONG_TYPE, OTHER.",
        "fix_instructions": "Instructions for the borrower to fix and re-upload.",
        "reviewed_at": "Timestamp of the most recent review action.",
        "reviewed_by": "User ID of reviewer, or 'SYSTEM' for automated reviews.",
        "upload_source": "Where the document was uploaded from: WEB, MOBILE, EMAIL.",
        "display_name": "User-editable display name for the document.",
        "assigned_owner": "Which party the document belongs to: BORROWER or CO_BORROWER.",
    },

    "DocumentRequest": {
        "id": "Auto-increment primary key.",
        "loan_id": "FK to loans. Required. Indexed.",
        "borrower_id": "FK to borrower_profiles. Optional.",
        "doc_type": "Required document type enum.",
        "title": "Human-readable title displayed in the needs list.",
        "description": "Detailed description of what is needed.",
        "instructions": "Specific instructions for the borrower on how to provide the document.",
        "required_count": "Number of documents required (e.g., 2 for '2 months of bank statements').",
        "applies_to": "Who must provide the document: BORROWER, CO_BORROWER, or BOTH.",
        "priority": "Request priority: CRITICAL, HIGH, NORMAL, LOW.",
        "freshness_days": "Maximum age in days. 30 for paystubs, 60 for bank statements, 365 for W-2s.",
        "auto_renew": "If True, a new request is auto-created when the document expires.",
        "next_expected_available_at": "Predicted date when a new version will be available (based on pay frequency).",
        "payroll_frequency": "Borrower's payroll frequency: WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY.",
        "status": "Request lifecycle status: OPEN, PENDING_REVIEW, ACCEPTED, REJECTED, WAIVED.",
        "due_date": "Deadline for the borrower to provide the document.",
        "completed_at": "Timestamp when the request was fulfilled (status changed to ACCEPTED).",
        "sla_due_at": "SLA deadline for the processor to review (typically 3 business days).",
        "is_active": "False if superseded by a newer request (e.g., after auto-renewal).",
        "superseded_by": "ID of the replacement request that superseded this one.",
    },

    "AddCustomRequestBody": {
        "title": "Title for the custom document request.",
        "description": "Optional detailed description.",
        "instructions": "Optional instructions for the borrower.",
        "priority": "Priority level: CRITICAL, HIGH, NORMAL, LOW. Default: NORMAL.",
        "due_date": "Optional deadline as ISO 8601 datetime.",
        "send_notification": "If True, sends an email notification to the borrower.",
        "borrower_email": "Required if send_notification is True.",
        "borrower_name": "Borrower's name for the notification email.",
    },

    "RejectDocumentBody": {
        "reviewer": "User ID of the person rejecting the document.",
        "reason": "Human-readable reason for rejection. Shown to the borrower.",
        "rejection_category": (
            "Optional category: SCREENSHOT, EXPIRED, POOR_QUALITY, INCOMPLETE, "
            "WRONG_TYPE, OTHER. Helps with analytics and auto-messaging."
        ),
    },

    "ApproveDocumentBody": {
        "reviewer": "User ID of the person approving the document.",
        "assigned_owner": "Optional. Set to BORROWER or CO_BORROWER to assign ownership.",
        "apply_fields": "Optional. If provided, applies extracted field values to a Lead or Loan profile.",
        "notes": "Optional approval notes.",
    },

    "WaiveRequestBody": {
        "reason": "Documented reason for waiving the requirement. Required for audit trail.",
        "waived_by": "User ID of the person waiving the requirement.",
    },

    "SourceDepositBody": {
        "explanation": "Explanation of the deposit source (e.g., 'Tax refund', 'Gift from parent').",
        "supporting_document_id": "Optional document ID of supporting evidence (e.g., gift letter).",
        "sourced_by": "User ID of the person sourcing the deposit.",
    },

    "CompareIncomeBody": {
        "stated_monthly_income": "Borrower's stated monthly income in dollars. Must be greater than 0.",
    },

    "RuleUpdateRequest": {
        "value": "New rule value. Type depends on the specific rule (int, float, string, bool).",
        "effective_date": "Date when the new value takes effect (YYYY-MM-DD). Defaults to today.",
        "expiration_date": "Optional date when the rule expires (YYYY-MM-DD). Null = no expiration.",
        "source": "Regulatory or policy source reference (e.g., 'irs_2026', 'fannie_mae', 'internal').",
        "description": "Human-readable description of the rule or reason for the change.",
    },
}


# =============================================================================
# FRESHNESS RULES REFERENCE
# =============================================================================

FRESHNESS_RULES: Dict[str, Dict[str, Any]] = {
    "PAYSTUB": {
        "freshness_days": 30,
        "auto_renew": True,
        "description": "Paystubs must be dated within the last 30 calendar days.",
        "regulatory_basis": "Fannie Mae B1-1-03; Freddie Mac 5102.2",
    },
    "BANK_STATEMENT": {
        "freshness_days": 60,
        "auto_renew": True,
        "description": "Bank statements must cover the most recent 60 calendar days (typically 2 monthly statements).",
        "regulatory_basis": "Fannie Mae B3-4.2-01",
    },
    "INVESTMENT_STATEMENT": {
        "freshness_days": 90,
        "auto_renew": True,
        "description": "Investment account statements must be dated within the last 90 days (1 quarterly statement).",
        "regulatory_basis": "Fannie Mae B3-4.3-01",
    },
    "W2": {
        "freshness_days": 365,
        "auto_renew": False,
        "description": "W-2 forms from the most recent year. Replaced annually in January/February.",
        "regulatory_basis": "Fannie Mae B1-1-03",
    },
    "TAX_RETURN": {
        "freshness_days": 365,
        "auto_renew": False,
        "description": "Tax returns from the most recent filing year.",
        "regulatory_basis": "Fannie Mae B3-3.1-01",
    },
    "BUSINESS_TAX_RETURN": {
        "freshness_days": 365,
        "auto_renew": False,
        "description": "Business tax returns required for self-employed borrowers.",
        "regulatory_basis": "Fannie Mae B3-3.2-01",
    },
}


# =============================================================================
# ENDPOINT CATALOG
# =============================================================================

ENDPOINT_CATALOG: List[Dict[str, str]] = [
    # Document Management (CRUD)
    {"method": "POST", "path": "/api/v1/smart-docs/needs-list/generate", "tag": "Smart Documents", "summary": "Generate needs list from loan application data."},
    {"method": "GET", "path": "/api/v1/smart-docs/needs-list/{loan_id}", "tag": "Smart Documents", "summary": "Get the current needs list for a loan."},
    {"method": "POST", "path": "/api/v1/smart-docs/upload/{loan_id}", "tag": "Smart Documents", "summary": "Upload a document for a loan."},
    {"method": "GET", "path": "/api/v1/smart-docs/download/{document_id}", "tag": "Smart Documents", "summary": "Download a document via presigned S3 URL."},
    {"method": "POST", "path": "/api/v1/smart-docs/merge", "tag": "Smart Documents", "summary": "Merge multiple documents into a single PDF."},
    {"method": "GET", "path": "/api/v1/smart-docs/loan/{loan_id}/documents", "tag": "Smart Documents", "summary": "List all documents for a loan."},
    {"method": "POST", "path": "/api/v1/smart-docs/sync-application-documents", "tag": "Smart Documents", "summary": "Sync document requirements from application."},
    {"method": "GET", "path": "/api/v1/smart-docs/templates", "tag": "Smart Documents", "summary": "List available needs list templates."},
    {"method": "GET", "path": "/api/v1/smart-docs/events/{loan_id}", "tag": "Smart Documents", "summary": "Get document policy events for a loan."},
    {"method": "GET", "path": "/api/v1/smart-docs/expiring", "tag": "Smart Documents", "summary": "Get documents expiring within a given number of days."},
    {"method": "PATCH", "path": "/api/v1/smart-docs/document/{document_id}/type", "tag": "Smart Documents", "summary": "Update a document's type classification."},
    {"method": "PATCH", "path": "/api/v1/smart-docs/document/{document_id}/name", "tag": "Smart Documents", "summary": "Update document display name."},

    # Document Approval
    {"method": "POST", "path": "/api/v1/smart-docs/document/{document_id}/approve", "tag": "Smart Documents", "summary": "Approve a document."},
    {"method": "POST", "path": "/api/v1/smart-docs/document/{document_id}/reject", "tag": "Smart Documents", "summary": "Reject a document with reason."},
    {"method": "DELETE", "path": "/api/v1/smart-docs/document/{document_id}", "tag": "Smart Documents", "summary": "Soft-delete a document."},
    {"method": "POST", "path": "/api/v1/smart-docs/document/{document_id}/manual-review", "tag": "Smart Documents", "summary": "Submit manual review decision."},
    {"method": "POST", "path": "/api/v1/smart-docs/document/{document_id}/reprocess", "tag": "Smart Documents", "summary": "Reprocess through validation pipeline."},
    {"method": "POST", "path": "/api/v1/smart-docs/document/{document_id}/review-approve", "tag": "Smart Documents", "summary": "Approve with field extraction and application."},
    {"method": "POST", "path": "/api/v1/smart-docs/document/{document_id}/extract", "tag": "Smart Documents", "summary": "Trigger AI data extraction."},
    {"method": "GET", "path": "/api/v1/smart-docs/document/{document_id}/extraction", "tag": "Smart Documents", "summary": "Get extraction results."},
    {"method": "GET", "path": "/api/v1/smart-docs/document/{document_id}/comparison", "tag": "Smart Documents", "summary": "Compare extracted data vs profile."},
    {"method": "POST", "path": "/api/v1/smart-docs/document/{document_id}/apply-fields", "tag": "Smart Documents", "summary": "Apply extracted fields to Lead/Loan."},

    # Document Requests
    {"method": "POST", "path": "/api/v1/smart-docs/needs-list/{loan_id}/custom-request", "tag": "Smart Documents", "summary": "Add a custom document request."},
    {"method": "POST", "path": "/api/v1/smart-docs/needs-list/request/{request_id}/waive", "tag": "Smart Documents", "summary": "Waive a document requirement."},
    {"method": "POST", "path": "/api/v1/smart-docs/request/{request_id}/re-request", "tag": "Smart Documents", "summary": "Re-request a rejected document."},

    # Income Calculation
    {"method": "POST", "path": "/api/smart-docs/income/calculate", "tag": "Income Calculation", "summary": "Calculate income from uploaded documents."},
    {"method": "GET", "path": "/api/smart-docs/income/calculation/{calculation_id}", "tag": "Income Calculation", "summary": "Get income calculation details."},
    {"method": "GET", "path": "/api/smart-docs/income/history/{loan_id}", "tag": "Income Calculation", "summary": "Get calculation history for a loan."},
    {"method": "POST", "path": "/api/smart-docs/income/calculation/{calculation_id}/approve", "tag": "Income Calculation", "summary": "Approve income calculation (maker-checker)."},
    {"method": "POST", "path": "/api/smart-docs/income/calculation/{calculation_id}/reject", "tag": "Income Calculation", "summary": "Reject income calculation."},
    {"method": "GET", "path": "/api/smart-docs/income/dti/{loan_id}", "tag": "Income Calculation", "summary": "Get DTI analysis for a loan."},

    # E-Signature
    {"method": "POST", "path": "/api/v1/esign/envelopes", "tag": "E-Signature", "summary": "Create a new e-signature envelope."},
    {"method": "POST", "path": "/api/v1/esign/envelopes/{envelope_id}/send", "tag": "E-Signature", "summary": "Send envelope to all recipients."},
    {"method": "GET", "path": "/api/v1/esign/envelopes/{envelope_id}", "tag": "E-Signature", "summary": "Get envelope status and details."},
    {"method": "POST", "path": "/api/v1/esign/envelopes/{envelope_id}/void", "tag": "E-Signature", "summary": "Void an envelope."},
    {"method": "GET", "path": "/api/v1/esign/envelopes/{envelope_id}/audit-trail", "tag": "E-Signature", "summary": "Get cryptographic audit trail."},
    {"method": "GET", "path": "/api/v1/esign/sign", "tag": "E-Signature", "summary": "Start a signing session (token-based)."},
    {"method": "POST", "path": "/api/v1/esign/sign/submit", "tag": "E-Signature", "summary": "Submit signed fields."},
    {"method": "GET", "path": "/api/v1/esign/stats", "tag": "E-Signature", "summary": "Get e-signature statistics."},

    # Bank Statement Analysis
    {"method": "POST", "path": "/api/smart-docs/bank-analysis/analyze/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Analyze bank statements for a loan."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/results/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Get cached analysis results."},
    {"method": "POST", "path": "/api/smart-docs/bank-analysis/reanalyze/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Re-analyze with latest statements."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/large-deposits/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Get large deposits requiring sourcing."},
    {"method": "POST", "path": "/api/smart-docs/bank-analysis/large-deposits/{deposit_index}/source", "tag": "Bank Statement Analysis", "summary": "Mark deposit as sourced."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/nsf-events/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Get NSF/overdraft events."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/irs-payments/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Get IRS payment analysis."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/income-verification/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Get deposit-based income verification."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/undisclosed-debts/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Get undisclosed obligation detection."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/risk-summary/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Get overall risk summary."},
    {"method": "POST", "path": "/api/smart-docs/bank-analysis/compare-income/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Compare stated vs deposit income."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/tasks/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Get analysis-generated tasks."},
    {"method": "POST", "path": "/api/smart-docs/bank-analysis/generate-report/{loan_id}", "tag": "Bank Statement Analysis", "summary": "Generate bank analysis PDF report."},
    {"method": "GET", "path": "/api/smart-docs/bank-analysis/stats", "tag": "Bank Statement Analysis", "summary": "Get org-wide analysis statistics."},

    # Document Intelligence
    {"method": "POST", "path": "/api/smart-docs/doc-intel/classify", "tag": "Document Intelligence", "summary": "Classify an uploaded document."},
    {"method": "POST", "path": "/api/smart-docs/doc-intel/classify/{document_id}", "tag": "Document Intelligence", "summary": "Classify an existing document."},
    {"method": "GET", "path": "/api/smart-docs/doc-intel/classification/{document_id}", "tag": "Document Intelligence", "summary": "Get classification results."},
    {"method": "POST", "path": "/api/smart-docs/doc-intel/classification/{id}/feedback", "tag": "Document Intelligence", "summary": "Submit classification feedback."},
    {"method": "POST", "path": "/api/smart-docs/doc-intel/analyze-application/{loan_id}", "tag": "Document Intelligence", "summary": "Analyze POS for required documents."},
    {"method": "POST", "path": "/api/smart-docs/doc-intel/analyze-call", "tag": "Document Intelligence", "summary": "Analyze call transcript for document needs."},
    {"method": "GET", "path": "/api/smart-docs/doc-intel/requirement-rules", "tag": "Document Intelligence", "summary": "List configurable requirement rules."},
    {"method": "POST", "path": "/api/smart-docs/doc-intel/batch-classify/{loan_id}", "tag": "Document Intelligence", "summary": "Batch classify unclassified documents."},
    {"method": "GET", "path": "/api/smart-docs/doc-intel/stats", "tag": "Document Intelligence", "summary": "Get intelligence statistics."},

    # Document Security
    {"method": "POST", "path": "/api/smart-docs/doc-security/access/log", "tag": "Document Security", "summary": "Log a document access event."},
    {"method": "GET", "path": "/api/smart-docs/doc-security/access/log/{document_id}", "tag": "Document Security", "summary": "Get access log for a document."},
    {"method": "POST", "path": "/api/smart-docs/doc-security/integrity/verify/{document_id}", "tag": "Document Security", "summary": "Verify document integrity (SHA-256)."},
    {"method": "POST", "path": "/api/smart-docs/doc-security/fraud/check/{document_id}", "tag": "Document Security", "summary": "Run fraud analysis on a document."},
    {"method": "GET", "path": "/api/smart-docs/doc-security/retention/policies", "tag": "Document Security", "summary": "Get retention policies."},
    {"method": "POST", "path": "/api/smart-docs/doc-security/watermark/{document_id}", "tag": "Document Security", "summary": "Apply forensic watermark."},
    {"method": "GET", "path": "/api/smart-docs/doc-security/encryption/status/{document_id}", "tag": "Document Security", "summary": "Get encryption status."},
    {"method": "GET", "path": "/api/smart-docs/doc-security/suspicious-activity", "tag": "Document Security", "summary": "Get suspicious activity report."},

    # Document Analytics
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/dashboard", "tag": "Document Analytics", "summary": "Main analytics dashboard."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/pipeline-completeness", "tag": "Document Analytics", "summary": "Per-loan document completeness."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/sla-compliance", "tag": "Document Analytics", "summary": "Document SLA compliance metrics."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/ai-performance", "tag": "Document Analytics", "summary": "AI classification performance."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/followup-effectiveness", "tag": "Document Analytics", "summary": "Follow-up campaign effectiveness."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/income-summary", "tag": "Document Analytics", "summary": "Income calculation summary."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/bank-analysis-summary", "tag": "Document Analytics", "summary": "Bank analysis summary."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/esign-metrics", "tag": "Document Analytics", "summary": "E-signature metrics."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/processor-productivity", "tag": "Document Analytics", "summary": "Per-processor review productivity."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/loan/{loan_id}/timeline", "tag": "Document Analytics", "summary": "Document timeline for a loan."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/trends", "tag": "Document Analytics", "summary": "Document volume and processing trends."},
    {"method": "GET", "path": "/api/smart-docs/doc-analytics/bottlenecks", "tag": "Document Analytics", "summary": "Identify document bottlenecks."},

    # Follow-up & Scheduling
    {"method": "POST", "path": "/api/smart-docs/followup/campaigns", "tag": "Document Follow-up", "summary": "Create a follow-up campaign."},
    {"method": "GET", "path": "/api/smart-docs/followup/campaigns", "tag": "Document Follow-up", "summary": "List campaigns."},
    {"method": "GET", "path": "/api/smart-docs/followup/campaigns/{campaign_id}", "tag": "Document Follow-up", "summary": "Get campaign details."},
    {"method": "POST", "path": "/api/smart-docs/followup/campaigns/{campaign_id}/pause", "tag": "Document Follow-up", "summary": "Pause a campaign."},
    {"method": "POST", "path": "/api/smart-docs/followup/campaigns/{campaign_id}/resume", "tag": "Document Follow-up", "summary": "Resume a paused campaign."},
    {"method": "POST", "path": "/api/smart-docs/followup/campaigns/{campaign_id}/cancel", "tag": "Document Follow-up", "summary": "Cancel a campaign."},
    {"method": "POST", "path": "/api/smart-docs/followup/appointments", "tag": "Document Follow-up", "summary": "Create a document appointment."},
    {"method": "GET", "path": "/api/smart-docs/followup/appointments", "tag": "Document Follow-up", "summary": "List appointments."},
    {"method": "POST", "path": "/api/smart-docs/followup/appointments/{id}/confirm", "tag": "Document Follow-up", "summary": "Confirm an appointment."},
    {"method": "POST", "path": "/api/smart-docs/followup/appointments/{id}/cancel", "tag": "Document Follow-up", "summary": "Cancel an appointment."},
    {"method": "GET", "path": "/api/smart-docs/followup/templates", "tag": "Document Follow-up", "summary": "List message templates."},
    {"method": "POST", "path": "/api/smart-docs/followup/templates", "tag": "Document Follow-up", "summary": "Create a message template."},

    # Borrower Portal
    {"method": "GET", "path": "/api/smart-docs/portal/docs/{workspace_slug}/checklist", "tag": "Document Portal", "summary": "Get borrower document checklist."},
    {"method": "POST", "path": "/api/smart-docs/portal/docs/{workspace_slug}/upload", "tag": "Document Portal", "summary": "Upload a document via portal."},
    {"method": "POST", "path": "/api/smart-docs/portal/docs/{workspace_slug}/reupload/{request_id}", "tag": "Document Portal", "summary": "Re-upload a rejected document."},
    {"method": "GET", "path": "/api/smart-docs/portal/docs/{workspace_slug}/preview/{document_id}", "tag": "Document Portal", "summary": "Get presigned preview URL."},
    {"method": "GET", "path": "/api/smart-docs/portal/docs/{workspace_slug}/status/{document_id}", "tag": "Document Portal", "summary": "Check document review status."},
    {"method": "POST", "path": "/api/smart-docs/portal/docs/{workspace_slug}/loe", "tag": "Document Portal", "summary": "Submit a Letter of Explanation."},
    {"method": "GET", "path": "/api/smart-docs/portal/docs/{workspace_slug}/progress", "tag": "Document Portal", "summary": "Get overall progress summary."},

    # Document Review
    {"method": "POST", "path": "/api/smart-docs/doc-review/review/{document_id}", "tag": "Document Review", "summary": "AI review a single document."},
    {"method": "POST", "path": "/api/smart-docs/doc-review/batch-review/{loan_id}", "tag": "Document Review", "summary": "AI review all pending documents for a loan."},
    {"method": "GET", "path": "/api/smart-docs/doc-review/queue", "tag": "Document Review", "summary": "Get review queue."},
    {"method": "POST", "path": "/api/smart-docs/doc-review/queue/{document_id}/claim", "tag": "Document Review", "summary": "Claim a document for review."},
    {"method": "POST", "path": "/api/smart-docs/doc-review/queue/{document_id}/release", "tag": "Document Review", "summary": "Release a claimed document."},
    {"method": "POST", "path": "/api/smart-docs/doc-review/validate-file", "tag": "Document Review", "summary": "Pre-upload file validation."},
    {"method": "GET", "path": "/api/smart-docs/doc-review/history/{document_id}", "tag": "Document Review", "summary": "Get review history."},
    {"method": "GET", "path": "/api/smart-docs/doc-review/stats", "tag": "Document Review", "summary": "Get review statistics."},
    {"method": "GET", "path": "/api/smart-docs/doc-review/completeness/{loan_id}", "tag": "Document Review", "summary": "Get loan document completeness."},

    # Enterprise Config
    {"method": "GET", "path": "/api/smart-docs/config/rules", "tag": "business-rules", "summary": "List all business rules."},
    {"method": "GET", "path": "/api/smart-docs/config/rules/{category}", "tag": "business-rules", "summary": "List rules by category."},
    {"method": "PUT", "path": "/api/smart-docs/config/rules/{rule_key}", "tag": "business-rules", "summary": "Update a business rule (admin only)."},
    {"method": "GET", "path": "/api/smart-docs/config/rules/{rule_key}/history", "tag": "business-rules", "summary": "Get rule change history."},
    {"method": "POST", "path": "/api/smart-docs/config/rules/seed-defaults", "tag": "business-rules", "summary": "Seed default rules for organization."},
]


# =============================================================================
# MAIN CONFIG FUNCTION
# =============================================================================

def get_api_docs_config() -> Dict[str, Any]:
    """
    Return the complete Smart Docs V2 API documentation configuration.

    This dictionary can be used to:
    - Enhance FastAPI's auto-generated OpenAPI spec
    - Populate Swagger UI with rich examples
    - Generate client SDK documentation
    - Feed API reference sites

    Returns:
        Dictionary containing all documentation sections.
    """
    return {
        "title": API_TITLE,
        "version": API_VERSION,
        "description": API_DESCRIPTION,
        "tags_metadata": TAGS_METADATA,

        # Schema documentation
        "enum_descriptions": {
            "DocType": DOC_TYPE_DESCRIPTIONS,
            "RequestStatus": REQUEST_STATUS_DESCRIPTIONS,
            "DocumentStatus": DOCUMENT_STATUS_DESCRIPTIONS,
            "RejectionCategory": REJECTION_CATEGORY_DESCRIPTIONS,
            "EnvelopeStatus": ENVELOPE_STATUS_DESCRIPTIONS,
            "CampaignStatus": CAMPAIGN_STATUS_DESCRIPTIONS,
        },
        "schema_field_descriptions": SCHEMA_FIELD_DESCRIPTIONS,
        "freshness_rules": FRESHNESS_RULES,

        # Authentication
        "auth_schemes": AUTH_SCHEMES,
        "endpoint_auth_requirements": ENDPOINT_AUTH_REQUIREMENTS,

        # Rate limiting
        "rate_limits": RATE_LIMITS,

        # Error codes
        "error_codes": ERROR_CODES,

        # Webhooks
        "webhook_events": WEBHOOK_EVENTS,
        "webhook_security": WEBHOOK_SECURITY,

        # Examples
        "response_examples": RESPONSE_EXAMPLES,
        "request_examples": REQUEST_EXAMPLES,

        # Endpoint catalog
        "endpoint_catalog": ENDPOINT_CATALOG,
        "total_endpoints": len(ENDPOINT_CATALOG),
    }


def get_openapi_tags() -> List[Dict[str, str]]:
    """Return tag metadata list for FastAPI's openapi_tags parameter."""
    return TAGS_METADATA


def get_responses_for(endpoint_key: str) -> Dict[int, Dict[str, Any]]:
    """
    Get response examples for a specific endpoint key.

    Args:
        endpoint_key: Key from RESPONSE_EXAMPLES (e.g., "document_upload",
                      "income_calculate", "esign_create_envelope").

    Returns:
        Dictionary mapping HTTP status codes to response descriptions,
        or empty dict if key not found.
    """
    return RESPONSE_EXAMPLES.get(endpoint_key, {})


def get_request_example(example_key: str) -> Dict[str, Any]:
    """
    Get a request body example for a specific key.

    Args:
        example_key: Key from REQUEST_EXAMPLES (e.g., "generate_needs_list",
                     "create_esign_envelope", "source_large_deposit").

    Returns:
        Dictionary with "summary" and "value" keys, or empty dict if not found.
    """
    return REQUEST_EXAMPLES.get(example_key, {})


def get_error_details(error_code: str) -> Dict[str, str]:
    """
    Get error code details including troubleshooting guidance.

    Args:
        error_code: Error code from ERROR_CODES (e.g., "LOAN_NOT_FOUND",
                    "MAKER_CHECKER_VIOLATION", "RATE_LIMITED").

    Returns:
        Dictionary with "status", "description", and "troubleshooting" keys.
    """
    return ERROR_CODES.get(error_code, {})


def get_webhook_payload(event_type: str) -> Dict[str, Any]:
    """
    Get the example webhook payload for an event type.

    Args:
        event_type: Event type string (e.g., "document.uploaded",
                    "esign.envelope_completed").

    Returns:
        Dictionary with "description" and "payload_example" keys.
    """
    return WEBHOOK_EVENTS.get(event_type, {})
