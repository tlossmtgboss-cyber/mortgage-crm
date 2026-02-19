"""
Encompass (ICE Mortgage Technology) API Client

Implements the BaseLOSClient interface for Encompass v3 API.
Supports OAuth2 client credentials flow, loan CRUD, pipeline search,
and document listing.

Enterprise Readiness: Check 7.1 (LOS Integration Framework)

Encompass API Reference:
    Base URL: https://api.elliemae.com/encompass/v3/
    Auth: https://api.elliemae.com/oauth2/v1/token (client_credentials)
    Key endpoints:
        POST   /loans             - Create loan
        GET    /loans/{id}        - Get loan
        PATCH  /loans/{id}        - Update loan
        GET    /loans/{id}/documents - List documents
        POST   /loanPipeline      - Pipeline search

Usage:
    client = EncompassClient(
        instance_id="BE11200822",
        client_id="xxx",
        client_secret="yyy",
    )
    await client.authenticate()
    loan = await client.pull_loan("some-guid-here")
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    logger.warning("httpx not installed; EncompassClient will use requests (sync fallback)")

try:
    import requests as sync_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from .base import (
    BaseLOSClient,
    LOSConfig,
    LOSLoanData,
    LOSSyncResult,
    LOSSyncStatus,
    LOSSyncDirection,
)
from .error_handler import LOSError, LOSRetryableError, LOSErrorHandler


# =============================================================================
# Encompass Field Mapping
# =============================================================================

# Maps CRM Loan model fields -> Encompass API field paths
# Encompass uses a flat "fields" dict with canonical field IDs
ENCOMPASS_FIELD_MAP = {
    # Borrower info
    "borrower_name": "Fields/4000",           # Borrower Full Name
    "borrower_email": "Fields/1240",          # Borrower Email
    "borrower_phone": "Fields/66",            # Borrower Home Phone
    "coborrower_name": "Fields/4004",         # Co-Borrower Full Name
    "co_borrower_email": "Fields/1268",       # Co-Borrower Email

    # Loan details
    "loan_number": "Fields/364",              # Loan Number
    "amount": "Fields/1109",                  # Total Loan Amount
    "purchase_price": "Fields/136",           # Purchase Price
    "rate": "Fields/3",                       # Note Rate
    "term": "Fields/4",                       # Loan Term (months)
    "loan_type": "Fields/1172",               # Loan Type
    "loan_purpose": "Fields/19",              # Loan Purpose

    # Property
    "property_address": "Fields/11",          # Subject Property Address
    "property_city": "Fields/12",             # Subject Property City
    "property_state": "Fields/14",            # Subject Property State
    "property_zip": "Fields/15",              # Subject Property Zip
    "property_type": "Fields/1041",           # Property Type
    "property_county": "Fields/13",           # Subject Property County

    # Dates
    "application_date": "Fields/745",         # Application Date
    "closing_date": "Fields/748",             # Closing Date / Settlement Date
    "lock_date": "Fields/761",               # Lock Date
    "lock_expiration_date": "Fields/762",     # Lock Expiration Date
    "funded_date": "Fields/2370",             # Disbursement Date / Funding Date

    # Disclosures
    "loan_estimate_sent_date": "Fields/3152", # LE Sent Date
    "cd_sent_to_borrower_date": "Fields/CD1.X1",  # CD Sent Date

    # Financials
    "ltv": "Fields/353",                      # LTV
    "cltv": "Fields/976",                     # CLTV
    "down_payment": "Fields/1771",            # Down Payment Amount

    # Team
    "loan_officer_name": "Fields/317",        # Loan Officer Name
    "loan_officer_email": "Fields/VEND.X263",  # Loan Officer Email
    "processor": "Fields/362",               # Processor Name
    "underwriter": "Fields/VEND.X23",         # Underwriter Name
}

# Reverse map: Encompass field ID -> CRM field
ENCOMPASS_REVERSE_MAP = {v: k for k, v in ENCOMPASS_FIELD_MAP.items()}

# Stage mapping: Encompass milestone -> CRM stage
ENCOMPASS_STAGE_MAP = {
    "Started": "DISCLOSED",
    "Processed": "PROCESSING",
    "Submitted": "SUBMITTED",
    "Conditionally Approved": "CONDITIONAL",
    "Approved": "APPROVED",
    "Docs Signing": "DOCS_OUT",
    "Docs Signed": "DOCS_BACK",
    "Funded": "FUNDED",
    "Purchased": "FUNDED",
    "Completed": "FUNDED",
    "Denied": "DENIED",
    "Withdrawn": "WITHDRAWN",
    "Suspended": "SUSPENDED",
    "Cancelled": "CANCELLED",
}

# Reverse: CRM stage -> Encompass milestone
CRM_TO_ENCOMPASS_STAGE = {v: k for k, v in ENCOMPASS_STAGE_MAP.items()}


class EncompassClient(BaseLOSClient):
    """Encompass (ICE Mortgage Technology) API client.

    Implements OAuth2 client credentials authentication and provides
    methods for loan CRUD, pipeline search, and document listing.
    """

    TOKEN_URL = "https://api.elliemae.com/oauth2/v1/token"
    BASE_URL = "https://api.elliemae.com/encompass/v3"

    def __init__(
        self,
        instance_id: str,
        client_id: str,
        client_secret: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: int = 30,
    ):
        config = LOSConfig(
            provider="encompass",
            instance_id=instance_id,
            client_id=client_id,
            client_secret=client_secret,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        super().__init__(config)
        self.base_url = base_url or self.BASE_URL
        self.error_handler = LOSErrorHandler(max_retries=config.max_retries)
        self._http_client: Optional[Any] = None

    # =========================================================================
    # HTTP helpers
    # =========================================================================

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests."""
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["X-Encompass-Api-Key"] = self.config.api_key
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make an authenticated API request with error handling.

        Handles token refresh, retries, and error classification.
        """
        await self.ensure_authenticated()

        url = f"{self.base_url}{path}"
        headers = self._get_headers()

        async def _do_request():
            if HAS_HTTPX:
                async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=json_data,
                        params=params,
                    )
                    return response.status_code, response.text, response.json() if response.text else {}
            elif HAS_REQUESTS:
                # Synchronous fallback
                response = sync_requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params,
                    timeout=self.config.timeout_seconds,
                )
                return response.status_code, response.text, response.json() if response.text else {}
            else:
                raise LOSError(
                    "No HTTP client available. Install httpx or requests.",
                    code="NO_HTTP_CLIENT",
                )

        status_code, response_text, response_data = await self.error_handler.execute_with_retry(
            _do_request
        )

        # Handle HTTP errors
        if status_code == 401:
            # Token expired - re-authenticate and retry once
            self._authenticated = False
            await self.ensure_authenticated()
            headers = self._get_headers()
            status_code, response_text, response_data = await _do_request()

        if status_code >= 400:
            error_msg = response_data.get("summary", response_data.get("message", response_text[:200]))
            if status_code == 404:
                raise LOSError(f"Resource not found: {error_msg}", code="NOT_FOUND")
            elif status_code == 409:
                raise LOSError(f"Conflict: {error_msg}", code="CONFLICT")
            elif status_code == 429:
                raise LOSRetryableError(f"Rate limited: {error_msg}", code="RATE_LIMITED")
            elif status_code >= 500:
                raise LOSRetryableError(f"Server error ({status_code}): {error_msg}", code="SERVER_ERROR")
            else:
                raise LOSError(f"API error ({status_code}): {error_msg}", code="API_ERROR")

        return response_data

    # =========================================================================
    # Authentication
    # =========================================================================

    async def authenticate(self) -> bool:
        """Authenticate with Encompass OAuth2 (client credentials grant).

        Encompass OAuth requires:
            - grant_type: client_credentials
            - client_id / client_secret
            - scope: lp (Loan Pipeline)
            - instance_id in the request body

        Returns:
            True if authentication succeeded
        """
        try:
            auth_data = {
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": "lp",
            }

            # Encompass requires instance_id
            if self.config.instance_id:
                auth_data["instance_id"] = self.config.instance_id

            if HAS_HTTPX:
                async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                    response = await client.post(
                        self.TOKEN_URL,
                        data=auth_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    response_data = response.json()
                    status_code = response.status_code
            elif HAS_REQUESTS:
                response = sync_requests.post(
                    self.TOKEN_URL,
                    data=auth_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self.config.timeout_seconds,
                )
                response_data = response.json()
                status_code = response.status_code
            else:
                raise LOSError("No HTTP client available", code="NO_HTTP_CLIENT")

            if status_code != 200:
                error_msg = response_data.get("error_description", response_data.get("error", "Unknown"))
                logger.error(f"Encompass auth failed ({status_code}): {error_msg}")
                self._authenticated = False
                return False

            self._token = response_data["access_token"]
            expires_in = response_data.get("expires_in", 3600)
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
            self._authenticated = True

            logger.info(f"Encompass authenticated (instance={self.config.instance_id}, expires_in={expires_in}s)")
            return True

        except Exception as e:
            logger.error(f"Encompass authentication error: {e}")
            self._authenticated = False
            return False

    # =========================================================================
    # Loan Operations
    # =========================================================================

    async def push_loan(self, loan_data: Dict[str, Any]) -> LOSSyncResult:
        """Push loan data to Encompass.

        If los_loan_id is present in loan_data, updates the existing loan.
        Otherwise, creates a new loan.

        Args:
            loan_data: Dict with CRM field names and values.
                       Must include 'loan_id' (CRM ID).
                       Optionally include 'los_loan_id' for updates.

        Returns:
            LOSSyncResult
        """
        result = LOSSyncResult(
            status=LOSSyncStatus.IN_PROGRESS,
            direction=LOSSyncDirection.PUSH,
            loan_id=loan_data.get("loan_id", 0),
            los_loan_id=loan_data.get("los_loan_id"),
        )

        try:
            # Map CRM fields to Encompass field format
            encompass_fields = {}
            for crm_field, value in loan_data.items():
                if crm_field in ("loan_id", "los_loan_id"):
                    continue
                los_field = ENCOMPASS_FIELD_MAP.get(crm_field)
                if los_field and value is not None:
                    # Convert datetime objects to ISO strings
                    if isinstance(value, datetime):
                        value = value.strftime("%Y-%m-%dT%H:%M:%SZ")
                    encompass_fields[los_field] = str(value)
                    result.fields_synced += 1
                else:
                    result.fields_skipped += 1

            if not encompass_fields:
                result.status = LOSSyncStatus.SKIPPED
                result.errors.append("No mappable fields found")
                return result

            payload = {"fields": encompass_fields}

            if result.los_loan_id:
                # Update existing loan
                response = await self._request(
                    "PATCH",
                    f"/loans/{result.los_loan_id}",
                    json_data=payload,
                )
                logger.info(f"Updated Encompass loan {result.los_loan_id}")
            else:
                # Create new loan
                response = await self._request(
                    "POST",
                    "/loans",
                    json_data=payload,
                )
                # Encompass returns the loan GUID in response
                result.los_loan_id = response.get("encompassId") or response.get("id")
                logger.info(f"Created Encompass loan {result.los_loan_id}")

            result.status = LOSSyncStatus.SUCCESS
            result.completed_at = datetime.now(timezone.utc)
            result.details["encompass_fields_pushed"] = list(encompass_fields.keys())

        except LOSError as e:
            result.status = LOSSyncStatus.FAILED
            result.errors.append(str(e))
            result.completed_at = datetime.now(timezone.utc)
            logger.error(f"Push to Encompass failed for loan {result.loan_id}: {e}")

        return result

    async def pull_loan(self, los_loan_id: str) -> LOSLoanData:
        """Pull loan data from Encompass.

        Fetches the full loan object and extracts fields we care about.

        Args:
            los_loan_id: Encompass loan GUID

        Returns:
            LOSLoanData with normalized fields
        """
        response = await self._request("GET", f"/loans/{los_loan_id}")

        # Extract fields from Encompass response
        fields = response.get("fields", response)

        def get_field(field_id: str) -> Optional[str]:
            """Get a field value by Encompass canonical ID."""
            return fields.get(field_id) or fields.get(field_id.replace("Fields/", ""))

        # Map Encompass milestone to CRM stage
        milestone = response.get("currentMilestone") or response.get("Fields/2015")
        crm_stage = ENCOMPASS_STAGE_MAP.get(milestone, "PROCESSING")

        loan_data = LOSLoanData(
            los_loan_id=los_loan_id,
            loan_number=get_field("Fields/364"),
            borrower_name=get_field("Fields/4000"),
            borrower_email=get_field("Fields/1240"),
            loan_amount=_safe_float(get_field("Fields/1109")),
            loan_type=get_field("Fields/1172"),
            property_address=get_field("Fields/11"),
            property_city=get_field("Fields/12"),
            property_state=get_field("Fields/14"),
            property_zip=get_field("Fields/15"),
            rate=_safe_float(get_field("Fields/3")),
            stage=crm_stage,
            closing_date=get_field("Fields/748"),
            raw_data=response,
        )

        logger.info(f"Pulled Encompass loan {los_loan_id}: {loan_data.loan_number}")
        return loan_data

    async def get_loan_status(self, los_loan_id: str) -> Dict[str, Any]:
        """Get loan status and milestone from Encompass.

        Args:
            los_loan_id: Encompass loan GUID

        Returns:
            Dict with milestone, last_modified, and CRM stage mapping
        """
        # Fetch only key fields for efficiency
        response = await self._request(
            "GET",
            f"/loans/{los_loan_id}",
            params={"entities": "milestone"},
        )

        milestone = response.get("currentMilestone", "Unknown")
        last_modified = response.get("lastModified")

        return {
            "los_loan_id": los_loan_id,
            "milestone": milestone,
            "crm_stage": ENCOMPASS_STAGE_MAP.get(milestone, "PROCESSING"),
            "last_modified": last_modified,
            "loan_folder": response.get("loanFolder"),
        }

    async def search_loans(
        self,
        filters: Dict[str, Any],
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search the Encompass pipeline.

        Uses the POST /loanPipeline endpoint with filter criteria.

        Args:
            filters: Dict with search criteria. Supported keys:
                - loan_number: Loan number to search
                - borrower_name: Borrower last name
                - loan_officer: LO name
                - date_from: Start date (YYYY-MM-DD)
                - date_to: End date (YYYY-MM-DD)
            limit: Max results

        Returns:
            List of loan summary dicts
        """
        # Build Encompass pipeline query
        terms = []

        if filters.get("loan_number"):
            terms.append({
                "canonicalName": "Fields.364",
                "value": filters["loan_number"],
                "matchType": "exact",
            })

        if filters.get("borrower_name"):
            terms.append({
                "canonicalName": "Fields.4002",  # Borrower Last Name
                "value": filters["borrower_name"],
                "matchType": "contains",
            })

        if filters.get("loan_officer"):
            terms.append({
                "canonicalName": "Fields.317",
                "value": filters["loan_officer"],
                "matchType": "contains",
            })

        pipeline_request = {
            "filter": {
                "operator": "and",
                "terms": terms,
            } if terms else {},
            "fields": [
                "Fields.364",   # Loan Number
                "Fields.4000",  # Borrower Name
                "Fields.1109",  # Loan Amount
                "Fields.14",    # Property State
                "Fields.2015",  # Current Milestone
                "Fields.317",   # LO Name
                "Fields.748",   # Closing Date
            ],
            "sortOrder": [
                {"canonicalName": "Fields.748", "order": "desc"},
            ],
            "start": 0,
            "limit": limit,
        }

        response = await self._request("POST", "/loanPipeline", json_data=pipeline_request)

        # Normalize results
        results = []
        for item in response if isinstance(response, list) else response.get("items", []):
            fields = item.get("fields", {})
            results.append({
                "los_loan_id": item.get("loanGuid") or item.get("id"),
                "loan_number": fields.get("Fields.364"),
                "borrower_name": fields.get("Fields.4000"),
                "loan_amount": _safe_float(fields.get("Fields.1109")),
                "property_state": fields.get("Fields.14"),
                "milestone": fields.get("Fields.2015"),
                "loan_officer": fields.get("Fields.317"),
                "closing_date": fields.get("Fields.748"),
            })

        logger.info(f"Encompass pipeline search returned {len(results)} results")
        return results

    async def get_loan_documents(self, los_loan_id: str) -> List[Dict[str, Any]]:
        """Get documents attached to an Encompass loan.

        Args:
            los_loan_id: Encompass loan GUID

        Returns:
            List of document metadata dicts
        """
        response = await self._request("GET", f"/loans/{los_loan_id}/documents")

        documents = []
        items = response if isinstance(response, list) else response.get("items", [])
        for doc in items:
            documents.append({
                "document_id": doc.get("documentId") or doc.get("id"),
                "title": doc.get("title"),
                "description": doc.get("description"),
                "date_created": doc.get("dateCreated"),
                "date_received": doc.get("dateReceived"),
                "status": doc.get("status", {}).get("name") if isinstance(doc.get("status"), dict) else doc.get("status"),
                "category": doc.get("category", {}).get("name") if isinstance(doc.get("category"), dict) else None,
            })

        return documents


# =============================================================================
# Helpers
# =============================================================================

def _safe_float(value: Any) -> Optional[float]:
    """Convert a value to float safely."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
