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

import json
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
    "loan_estimate_sent_date": "Fields/3152",          # LE Sent Date
    "initial_disclosures_sent_date": "Fields/3152",    # Initial Disclosures Sent (same as LE)
    "initial_disclosures_signed_date": "Fields/3153",  # Initial Disclosures Signed
    "cd_sent_to_borrower_date": "Fields/CD1.X1",       # CD Sent Date
    "cd_acknowledged_date": "Fields/CD1.X3",            # CD Acknowledged/Received Date

    # Appraisal dates
    "appraisal_ordered_date": "Fields/APPRAISAL.X1",    # Appraisal Ordered Date
    "appraisal_scheduled_date": "Fields/APPRAISAL.X2",  # Appraisal Scheduled Date
    "appraisal_completed_date": "Fields/APPRAISAL.X3",  # Appraisal Completed Date
    "appraisal_received_date": "Fields/APPRAISAL.X4",   # Appraisal Received Date
    "appraisal_value": "Fields/356",                    # Appraised Value

    # Title dates
    "title_ordered_date": "Fields/VEND.X39",       # Title Ordered Date
    "title_received_date": "Fields/VEND.X40",      # Title Received Date

    # Insurance dates
    "insurance_ordered_date": "Fields/VEND.X41",   # Insurance Ordered Date
    "insurance_received_date": "Fields/VEND.X42",  # Insurance Received Date

    # Milestone dates
    "uw_received_date": "Fields/2015",              # UW Received / Submitted to UW Date
    "loan_approved_date": "Fields/2301",            # Loan Approved Date
    "conditional_approval_date": "Fields/2302",     # Conditional Approval Date
    "clear_to_close_date": "Fields/CTC.X1",         # Clear to Close Date
    "docs_ordered_date": "Fields/DOCS.X1",           # Docs Ordered Date
    "docs_out_date": "Fields/DOCS.X2",               # Docs Out / Sent Date
    "scheduled_closing_date": "Fields/763",          # Scheduled Closing Date
    "first_payment_date": "Fields/682",              # First Payment Date

    # Financials
    "ltv": "Fields/353",                      # LTV
    "cltv": "Fields/976",                     # CLTV
    "down_payment": "Fields/1771",            # Down Payment Amount
    "monthly_payment": "Fields/5",            # Monthly P&I Payment

    # Team
    "loan_officer_name": "Fields/317",        # Loan Officer Name
    "loan_officer_email": "Fields/VEND.X263",  # Loan Officer Email
    "processor": "Fields/362",               # Processor Name
    "processor_email": "Fields/VEND.X264",    # Processor Email
    "underwriter": "Fields/VEND.X23",         # Underwriter Name
    "closer": "Fields/VEND.X24",              # Closer Name
    "title_company": "Fields/VEND.X5",        # Title Company Name
}

# Reverse map: Encompass field ID -> CRM field
ENCOMPASS_REVERSE_MAP = {v: k for k, v in ENCOMPASS_FIELD_MAP.items()}

# Stage mapping: Encompass milestone -> CRM LoanStage (UPPERCASE strings)
# Covers all standard Encompass milestones mapped to all LoanStage enum values
ENCOMPASS_STAGE_MAP = {
    # Application phase
    "Started": "APPLICATION",
    "File Started": "APPLICATION",
    "Disclosed": "DISCLOSED",
    "LE Sent": "DISCLOSED",

    # Processing phase
    "Processed": "PROCESSING",
    "Processing": "PROCESSING",
    "Submitted": "SUBMITTED",
    "Submitted to UW": "SUBMITTED",

    # Underwriting phase
    "In Underwriting": "UNDERWRITING",
    "Underwriting": "UNDERWRITING",
    "UW Review": "UW_RECEIVED",
    "Received": "UW_RECEIVED",

    # Approval phase
    "Conditionally Approved": "CONDITIONAL_APPROVAL",
    "Cond. Approved": "CONDITIONAL_APPROVAL",
    "Approved": "APPROVED",
    "Approved with Conditions": "CONDITIONAL_APPROVAL",

    # Suspended
    "Suspended": "SUSPENDED",

    # Clear to Close & Docs
    "Clear to Close": "CLEAR_TO_CLOSE",
    "CTC": "CTC",
    "Closing": "CLOSING",
    "Docs Drawing": "DOCS",
    "Doc Preparation": "DOCS",
    "Docs Signing": "DOCS_OUT",
    "Docs Out": "DOCS_OUT",
    "Docs Signed": "DOCS_OUT",

    # Funded / Terminal
    "Funded": "FUNDED",
    "Purchased": "FUNDED",
    "Completed": "FUNDED",

    # Terminal / Negative
    "Denied": "DENIED",
    "Withdrawn": "WITHDRAWN",
    "Cancelled": "CANCELLED",
    "Dead": "DEAD",
    "Inactive": "DEAD",
}

# Reverse: CRM stage -> Encompass milestone (one-to-one, using preferred Encompass milestone names)
CRM_TO_ENCOMPASS_STAGE = {
    "APPLICATION": "Started",
    "DISCLOSED": "Disclosed",
    "PROCESSING": "Processing",
    "SUBMITTED": "Submitted",
    "UNDERWRITING": "In Underwriting",
    "UW_RECEIVED": "Received",
    "CONDITIONAL_APPROVAL": "Conditionally Approved",
    "APPROVED": "Approved",
    "SUSPENDED": "Suspended",
    "CTC": "Clear to Close",
    "CLEAR_TO_CLOSE": "Clear to Close",
    "CLOSING": "Closing",
    "DOCS": "Doc Preparation",
    "DOCS_OUT": "Docs Out",
    "FUNDED": "Funded",
    "CANCELLED": "Cancelled",
    "DENIED": "Denied",
    "DEAD": "Dead",
    "NURTURE": "Inactive",
    "WITHDRAWN": "Withdrawn",
    "DOES_NOT_QUALIFY": "Denied",
}


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
        _retry_on_401: bool = True,
    ) -> Dict[str, Any]:
        """Make an authenticated API request with error handling.

        Handles token refresh, retries, and error classification.
        On a 401 response the token is cleared and authentication is retried
        exactly once to handle mid-session expiry.
        """
        await self.ensure_authenticated()

        url = f"{self.base_url}{path}"

        def _parse_response(response_text: str) -> Dict[str, Any]:
            """Parse JSON response body; return empty dict on parse failure."""
            if not response_text:
                return {}
            try:
                return json.loads(response_text)
            except (json.JSONDecodeError, ValueError):
                return {}

        async def _do_request() -> tuple:
            """Execute the HTTP request, wrapping connection/timeout errors as retryable."""
            current_headers = self._get_headers()
            try:
                if HAS_HTTPX:
                    async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                        response = await client.request(
                            method=method,
                            url=url,
                            headers=current_headers,
                            json=json_data,
                            params=params,
                        )
                        return response.status_code, response.text, _parse_response(response.text)
                elif HAS_REQUESTS:
                    # Synchronous fallback — runs in calling thread
                    response = sync_requests.request(
                        method=method,
                        url=url,
                        headers=current_headers,
                        json=json_data,
                        params=params,
                        timeout=self.config.timeout_seconds,
                    )
                    return response.status_code, response.text, _parse_response(response.text)
                else:
                    raise LOSError(
                        "No HTTP client available. Install httpx or requests.",
                        code="NO_HTTP_CLIENT",
                    )
            except LOSError:
                raise
            except Exception as exc:
                # Network/timeout errors are retryable
                raise LOSRetryableError(
                    f"Request to {url} failed: {exc}",
                    code="NETWORK_ERROR",
                ) from exc

        status_code, response_text, response_data = await self.error_handler.execute_with_retry(
            _do_request
        )

        # Token expired mid-session — re-authenticate and retry exactly once
        if status_code == 401 and _retry_on_401:
            logger.warning(
                f"Encompass returned 401 for {method} {path}; "
                "re-authenticating and retrying once"
            )
            self._authenticated = False
            self._token = None
            await self.ensure_authenticated()
            # Recursive call with retry disabled to prevent infinite loops
            return await self._request(
                method, path, json_data=json_data, params=params, _retry_on_401=False
            )

        if status_code >= 400:
            error_msg = response_data.get(
                "summary",
                response_data.get("message", (response_text or "")[:200]),
            )
            if status_code == 404:
                raise LOSError(f"Resource not found: {error_msg}", code="NOT_FOUND")
            elif status_code == 409:
                raise LOSError(f"Conflict: {error_msg}", code="CONFLICT")
            elif status_code == 429:
                raise LOSRetryableError(f"Rate limited: {error_msg}", code="RATE_LIMITED")
            elif status_code >= 500:
                raise LOSRetryableError(
                    f"Server error ({status_code}): {error_msg}", code="SERVER_ERROR"
                )
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

        Tokens expire after ~30 minutes and are not refreshable; a new
        client_credentials grant must be obtained each time.

        Returns:
            True if authentication succeeded
        """
        auth_data = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "scope": "lp",
        }

        # Encompass requires instance_id to be included in the token request
        if self.config.instance_id:
            auth_data["instance_id"] = self.config.instance_id

        try:
            if HAS_HTTPX:
                async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                    response = await client.post(
                        self.TOKEN_URL,
                        data=auth_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    try:
                        response_data = response.json()
                    except (json.JSONDecodeError, ValueError):
                        response_data = {}
                    status_code = response.status_code
            elif HAS_REQUESTS:
                response = sync_requests.post(
                    self.TOKEN_URL,
                    data=auth_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self.config.timeout_seconds,
                )
                try:
                    response_data = response.json()
                except (json.JSONDecodeError, ValueError):
                    response_data = {}
                status_code = response.status_code
            else:
                raise LOSError("No HTTP client available. Install httpx or requests.", code="NO_HTTP_CLIENT")

            if status_code != 200:
                error_msg = response_data.get(
                    "error_description",
                    response_data.get("error", f"HTTP {status_code}"),
                )
                logger.error(
                    f"Encompass auth failed (instance={self.config.instance_id}, "
                    f"status={status_code}): {error_msg}"
                )
                self._authenticated = False
                return False

            access_token = response_data.get("access_token")
            if not access_token:
                logger.error(
                    f"Encompass auth response missing 'access_token' field "
                    f"(instance={self.config.instance_id})"
                )
                self._authenticated = False
                return False

            self._token = access_token
            expires_in = int(response_data.get("expires_in", 1800))
            # Subtract 90 seconds from the expiry so we re-auth before the token
            # actually expires (Encompass tokens are typically ~30 min / 1800s)
            buffer_seconds = min(90, expires_in // 4)
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=expires_in - buffer_seconds
            )
            self._authenticated = True

            logger.info(
                f"Encompass authenticated successfully "
                f"(instance={self.config.instance_id}, "
                f"expires_in={expires_in}s, "
                f"valid_until={self._token_expires_at.isoformat()})"
            )
            return True

        except LOSError:
            raise
        except Exception as exc:
            logger.error(
                f"Encompass authentication raised an unexpected error "
                f"(instance={self.config.instance_id}): {exc}",
                exc_info=True,
            )
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
            unmapped_fields = []
            for crm_field, value in loan_data.items():
                if crm_field in ("loan_id", "los_loan_id"):
                    continue
                los_field = ENCOMPASS_FIELD_MAP.get(crm_field)
                if los_field and value is not None:
                    # Convert datetime/date objects to ISO strings
                    if isinstance(value, datetime):
                        value = value.strftime("%Y-%m-%dT%H:%M:%SZ")
                    elif hasattr(value, "isoformat"):
                        # date objects
                        value = value.isoformat()
                    encompass_fields[los_field] = str(value)
                    result.fields_synced += 1
                elif los_field is None:
                    unmapped_fields.append(crm_field)
                    result.fields_skipped += 1
                else:
                    # Field mapped but value is None
                    result.fields_skipped += 1

            if unmapped_fields:
                logger.debug(
                    f"Encompass push for loan {result.loan_id}: "
                    f"{len(unmapped_fields)} unmapped CRM fields skipped: {unmapped_fields}"
                )

            if not encompass_fields:
                logger.warning(
                    f"Encompass push for loan {result.loan_id}: "
                    "no mappable fields with non-null values found; skipping"
                )
                result.status = LOSSyncStatus.SKIPPED
                result.errors.append("No mappable fields with non-null values found")
                result.completed_at = datetime.now(timezone.utc)
                return result

            payload = {"fields": encompass_fields}

            if result.los_loan_id:
                # Update existing loan
                await self._request(
                    "PATCH",
                    f"/loans/{result.los_loan_id}",
                    json_data=payload,
                )
                logger.info(
                    f"Updated Encompass loan {result.los_loan_id} "
                    f"({result.fields_synced} fields pushed)"
                )
            else:
                # Create new loan
                response = await self._request(
                    "POST",
                    "/loans",
                    json_data=payload,
                )
                # Encompass returns the loan GUID in the response body
                result.los_loan_id = response.get("encompassId") or response.get("id")
                if not result.los_loan_id:
                    logger.warning(
                        f"Encompass create response did not include a loan GUID "
                        f"for CRM loan {result.loan_id}; response keys: {list(response.keys())}"
                    )
                logger.info(
                    f"Created Encompass loan {result.los_loan_id} "
                    f"for CRM loan {result.loan_id} "
                    f"({result.fields_synced} fields pushed)"
                )

            result.status = LOSSyncStatus.SUCCESS
            result.completed_at = datetime.now(timezone.utc)
            result.details["encompass_fields_pushed"] = list(encompass_fields.keys())

        except LOSError as e:
            result.status = LOSSyncStatus.FAILED
            result.errors.append(str(e))
            result.completed_at = datetime.now(timezone.utc)
            logger.error(
                f"Push to Encompass failed for CRM loan {result.loan_id} "
                f"(los_loan_id={result.los_loan_id}): [{e.code}] {e}",
                exc_info=True,
            )
        except Exception as exc:
            result.status = LOSSyncStatus.FAILED
            result.errors.append(str(exc))
            result.completed_at = datetime.now(timezone.utc)
            logger.error(
                f"Unexpected error pushing CRM loan {result.loan_id} to Encompass: {exc}",
                exc_info=True,
            )

        return result

    async def pull_loan(self, los_loan_id: str) -> LOSLoanData:
        """Pull loan data from Encompass.

        Fetches the full loan object and extracts fields we care about.
        All field extraction is null-safe; missing fields produce None values
        rather than raising KeyError.

        Args:
            los_loan_id: Encompass loan GUID

        Returns:
            LOSLoanData with normalized fields

        Raises:
            LOSError: If the loan is not found or the API request fails.
        """
        if not los_loan_id:
            raise LOSError("los_loan_id must not be empty", code="INVALID_PARAM")

        logger.debug(f"Pulling Encompass loan {los_loan_id}")
        response = await self._request("GET", f"/loans/{los_loan_id}")

        # Extract fields from Encompass response.
        # The API may nest fields under a "fields" key or return them at the top level.
        raw_fields = response.get("fields") or {}
        # Merge top-level response keys for convenience
        combined = {**response, **raw_fields}

        def get_field(field_id: str) -> Optional[str]:
            """Null-safe field extraction by Encompass canonical ID.

            Tries the full field path (e.g. "Fields/364") and the bare
            numeric ID (e.g. "364") to accommodate both response formats.
            """
            value = combined.get(field_id)
            if value is None:
                bare_id = field_id.replace("Fields/", "")
                value = combined.get(bare_id)
            if value == "" or value == "0" and field_id in ("Fields/1109", "Fields/3"):
                return None
            return value if value is not None else None

        # Map Encompass milestone to CRM stage; fall back to PROCESSING if unknown
        milestone = response.get("currentMilestone") or get_field("Fields/2015")
        crm_stage = ENCOMPASS_STAGE_MAP.get(milestone, "PROCESSING")
        if milestone and crm_stage == "PROCESSING" and milestone != "Processing":
            logger.debug(
                f"Encompass loan {los_loan_id}: unmapped milestone '{milestone}'; "
                "defaulting to PROCESSING"
            )

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

        logger.info(
            f"Pulled Encompass loan {los_loan_id}: "
            f"loan_number={loan_data.loan_number}, "
            f"borrower={loan_data.borrower_name}, "
            f"stage={crm_stage} (milestone='{milestone}')"
        )
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
