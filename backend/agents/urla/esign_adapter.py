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


class StubESignatureAdapter:
    """
    No-op adapter for development and testing. Logs calls, returns
    stub responses. Replace with a real vendor adapter in production.
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
    When a real vendor adapter is wired up, this function selects it
    based on env config (e.g. ESIGN_PROVIDER=docusign).
    """
    import os
    provider = os.getenv("ESIGN_PROVIDER", "stub")
    if provider == "stub":
        return StubESignatureAdapter()
    raise ValueError(f"Unknown ESIGN_PROVIDER: {provider}")
