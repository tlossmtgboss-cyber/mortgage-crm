"""
URLA Agent — Structured Logging Context
========================================
Thread-safe context injection for loan_id, tenant_id, and caller_phone
into all log records within a URLA session.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar

_loan_id: ContextVar[str] = ContextVar("urla_loan_id", default="")
_tenant_id: ContextVar[str] = ContextVar("urla_tenant_id", default="")
_caller_phone: ContextVar[str] = ContextVar("urla_caller_phone", default="")


def set_session_context(
    tenant_id: str = "",
    caller_phone: str = "",
    loan_id: str = "",
) -> None:
    if tenant_id:
        _tenant_id.set(tenant_id)
    if caller_phone:
        _caller_phone.set(caller_phone)
    if loan_id:
        _loan_id.set(loan_id)


class URLALogFilter(logging.Filter):
    """Auto-inject session context into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.urla_loan_id = _loan_id.get("")
        record.urla_tenant_id = _tenant_id.get("")
        record.urla_caller_phone = _caller_phone.get("")
        return True


URLA_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[tenant=%(urla_tenant_id)s loan=%(urla_loan_id)s] "
    "%(message)s"
)
