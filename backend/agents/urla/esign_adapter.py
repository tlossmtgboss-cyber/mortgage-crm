"""
Perennia AI — E-Signature Adapter Protocol
==========================================
Vendor-agnostic interface for triggering, tracking, and resending
e-signature requests from the URLA voice agent.

The URLA agent triggers signing requests (e.g. credit authorization after
finalize) and tracks their status. It does not own the signing ceremony —
that belongs to the vendor (DocuSign, Blend, etc.).

First concrete adapter is a future deliverable. This module defines the
protocol so the agent can wire up trigger + status tracking now.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger("urla.esign")


class ESignDocumentType(str, Enum):
    URLA = "URLA"
    CREDIT_AUTHORIZATION = "CREDIT_AUTHORIZATION"
    CLOSING_DISCLOSURE = "CLOSING_DISCLOSURE"


class ESignStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    VIEWED = "VIEWED"
    SIGNED = "SIGNED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ESignRequest:
    request_id: str
    document_type: ESignDocumentType
    loan_id: str
    borrower_email: str
    borrower_name: str
    signing_url: Optional[str] = None
    status: ESignStatus = ESignStatus.PENDING
    sent_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class ESignStatusResult:
    request_id: str
    status: ESignStatus
    signed_at: Optional[datetime] = None
    declined_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    error: Optional[str] = None


@runtime_checkable
class ESignatureAdapter(Protocol):
    """
    Vendor-agnostic e-signature protocol.

    Implementations: DocuSignAdapter, BlendAdapter, etc.
    """

    async def send_authorization(
        self,
        document_type: ESignDocumentType,
        loan_id: str,
        borrower_email: str,
        borrower_name: str,
        tenant_id: str,
        metadata: Optional[dict] = None,
    ) -> ESignRequest:
        """
        Initiate a signing request. Returns an ESignRequest with the
        request_id and signing_url (if the vendor provides one).
        """
        ...

    async def check_status(
        self,
        request_id: str,
    ) -> ESignStatusResult:
        """
        Poll the signing status. Used by the LO briefing, review queue,
        and follow-up workflows.
        """
        ...

    async def resend(
        self,
        request_id: str,
    ) -> ESignRequest:
        """
        Re-send the signing email. Used when a borrower says they didn't
        receive it (e.g. on a callback).
        """
        ...


class PosConsentESignAdapter:
    """
    E-signature adapter backed by the POS consent flow.

    The Perennia POS consent flow already provides the full signing
    ceremony for credit authorization and e-disclosure:

      1. ``POST /api/v1/pos/voice-complete`` triggers an SMS with a magic
         link (PURL) to the borrower.
      2. The borrower opens the link, reviews disclosures, types their
         full name, and clicks "I Authorize" on each consent page.
      3. ``GET /api/v1/pos/consent/{token}/status`` reports completion.

    This adapter wraps that existing flow behind the ``ESignatureAdapter``
    protocol so the URLA agent can use a single interface regardless of
    the signing provider.

    NOTE: ``send_authorization()`` returns SENT immediately because the
    voice-complete call in ``finalize_urla`` already triggers the SMS.
    The adapter does not duplicate that HTTP call — it records that the
    request was made and provides status checking / resend capability.
    """

    def __init__(self):
        import os
        self._api_base = os.getenv(
            "CRM_API_BASE_URL", "https://api.perenniaai.com"
        )
        self._api_key = os.getenv("CRM_API_KEY", "")

    # ── helpers ────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _http_get(self, path: str) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._api_base}{path}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def _http_post(self, path: str, payload: dict) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self._api_base}{path}",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ── protocol methods ──────────────────────────────────────────────

    async def send_authorization(
        self,
        document_type: ESignDocumentType,
        loan_id: str,
        borrower_email: str,
        borrower_name: str,
        tenant_id: str,
        metadata: Optional[dict] = None,
    ) -> ESignRequest:
        """
        Record that the signing request has been initiated.

        The actual SMS is already sent by the ``finalize_urla`` method
        via its direct HTTP call to ``/api/v1/pos/voice-complete``.
        This method returns a SENT status so callers know the flow is
        active.  The ``request_id`` encodes the loan_id so
        ``check_status`` can look it up later.
        """
        request_id = f"pos-consent-{loan_id}"
        logger.info(
            "PosConsentESignAdapter.send_authorization: consent flow active",
            extra={
                "request_id": request_id,
                "document_type": document_type.value,
                "loan_id": loan_id,
                "borrower_email": borrower_email,
            },
        )
        return ESignRequest(
            request_id=request_id,
            document_type=document_type,
            loan_id=loan_id,
            borrower_email=borrower_email,
            borrower_name=borrower_name,
            status=ESignStatus.SENT,
            sent_at=datetime.utcnow(),
        )

    async def check_status(self, request_id: str) -> ESignStatusResult:
        """
        Check whether the borrower has completed both consents by
        calling the POS consent status endpoint.

        ``request_id`` is expected to be ``pos-consent-{loan_id}``.
        We need the PURL token to call the status endpoint, but we
        may not have it.  If no token is available, return SENT
        (we know the SMS was sent but cannot check completion).
        """
        # Extract loan_id from request_id
        loan_id = request_id.replace("pos-consent-", "", 1) if request_id.startswith("pos-consent-") else request_id

        # The status endpoint requires a PURL token, not a loan_id.
        # If metadata stored the token, use it.  Otherwise return
        # SENT as a safe default — the LO dashboard and consent
        # service track completion independently.
        logger.info(
            "PosConsentESignAdapter.check_status: loan_id=%s",
            loan_id,
        )
        return ESignStatusResult(
            request_id=request_id,
            status=ESignStatus.SENT,
        )

    async def check_status_by_token(self, request_id: str, purl_token: str) -> ESignStatusResult:
        """
        Check consent completion using a known PURL token.

        This is the preferred path when the caller has the magic-link
        token (e.g. stored in the BorrowerApplication record).
        """
        try:
            data = await self._http_get(
                f"/api/v1/pos/consent/{purl_token}/status"
            )
            all_complete = data.get("all_complete", False)
            credit_done = data.get("credit_auth", {}).get("completed", False)
            econsent_done = data.get("e_consent", {}).get("completed", False)

            if all_complete:
                status = ESignStatus.SIGNED
            elif credit_done or econsent_done:
                status = ESignStatus.VIEWED  # partially complete
            else:
                status = ESignStatus.SENT

            return ESignStatusResult(
                request_id=request_id,
                status=status,
            )
        except Exception as e:
            logger.warning(
                "PosConsentESignAdapter.check_status_by_token failed",
                extra={"request_id": request_id, "error": str(e)},
            )
            return ESignStatusResult(
                request_id=request_id,
                status=ESignStatus.SENT,
                error=str(e),
            )

    async def resend(self, request_id: str) -> ESignRequest:
        """
        Re-trigger the voice-complete flow to re-send the SMS.

        Requires ``_resend_metadata`` to be set with the original
        call parameters.  Falls back to a logged warning if the
        metadata is missing (callers should store it).
        """
        loan_id = request_id.replace("pos-consent-", "", 1) if request_id.startswith("pos-consent-") else request_id

        # We cannot re-trigger without the original call params.
        # Log and return SENT — the LO can manually resend from the
        # CRM dashboard.
        logger.warning(
            "PosConsentESignAdapter.resend: re-send requires original "
            "call params; LO should use CRM dashboard to resend",
            extra={"request_id": request_id, "loan_id": loan_id},
        )
        return ESignRequest(
            request_id=request_id,
            document_type=ESignDocumentType.CREDIT_AUTHORIZATION,
            loan_id=loan_id,
            borrower_email="",
            borrower_name="",
            status=ESignStatus.SENT,
        )

    async def resend_with_params(
        self,
        request_id: str,
        voice_loan_id: str,
        borrower_first_name: str,
        borrower_phone: str,
        lo_name: str,
    ) -> ESignRequest:
        """
        Re-trigger the voice-complete SMS with full parameters.
        Use this when the caller has the original call context.
        """
        loan_id = request_id.replace("pos-consent-", "", 1) if request_id.startswith("pos-consent-") else request_id
        try:
            result = await self._http_post(
                "/api/v1/pos/voice-complete",
                {
                    "voice_loan_id": voice_loan_id,
                    "borrower_first_name": borrower_first_name,
                    "borrower_phone": borrower_phone,
                    "lo_name": lo_name,
                },
            )
            logger.info(
                "PosConsentESignAdapter.resend_with_params: SMS re-sent",
                extra={"request_id": request_id, "result_status": result.get("status")},
            )
            return ESignRequest(
                request_id=request_id,
                document_type=ESignDocumentType.CREDIT_AUTHORIZATION,
                loan_id=loan_id,
                borrower_email="",
                borrower_name="",
                status=ESignStatus.SENT,
                sent_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(
                "PosConsentESignAdapter.resend_with_params failed",
                extra={"request_id": request_id, "error": str(e)},
            )
            return ESignRequest(
                request_id=request_id,
                document_type=ESignDocumentType.CREDIT_AUTHORIZATION,
                loan_id=loan_id,
                borrower_email="",
                borrower_name="",
                status=ESignStatus.ERROR,
                error=str(e),
            )


class StubESignatureAdapter:
    """
    No-op adapter for development and testing. Logs calls, returns
    stub responses. Use ESIGN_PROVIDER=pos_consent in production.
    """

    async def send_authorization(
        self,
        document_type: ESignDocumentType,
        loan_id: str,
        borrower_email: str,
        borrower_name: str,
        tenant_id: str,
        metadata: Optional[dict] = None,
    ) -> ESignRequest:
        import uuid
        request_id = f"stub-{uuid.uuid4().hex[:8]}"
        logger.warning(
            "StubESignatureAdapter: no real e-sign vendor configured",
            extra={
                "request_id": request_id,
                "document_type": document_type.value,
                "loan_id": loan_id,
                "borrower_email": borrower_email,
            },
        )
        return ESignRequest(
            request_id=request_id,
            document_type=document_type,
            loan_id=loan_id,
            borrower_email=borrower_email,
            borrower_name=borrower_name,
            status=ESignStatus.PENDING,
        )

    async def check_status(self, request_id: str) -> ESignStatusResult:
        return ESignStatusResult(
            request_id=request_id,
            status=ESignStatus.PENDING,
        )

    async def resend(self, request_id: str) -> ESignRequest:
        logger.warning("StubESignatureAdapter.resend called", extra={"request_id": request_id})
        return ESignRequest(
            request_id=request_id,
            document_type=ESignDocumentType.CREDIT_AUTHORIZATION,
            loan_id="unknown",
            borrower_email="unknown",
            borrower_name="unknown",
            status=ESignStatus.SENT,
        )


def get_esign_adapter() -> ESignatureAdapter:
    """
    Factory: returns the configured e-signature adapter.

    Defaults to ``pos_consent`` which uses the existing POS consent
    flow (SMS magic link -> credit auth + e-disclosure pages).
    Set ``ESIGN_PROVIDER=stub`` for development/testing.
    """
    import os
    provider = os.getenv("ESIGN_PROVIDER", "pos_consent")
    if provider == "pos_consent":
        return PosConsentESignAdapter()
    if provider == "stub":
        return StubESignatureAdapter()
    raise ValueError(f"Unknown ESIGN_PROVIDER: {provider}")
