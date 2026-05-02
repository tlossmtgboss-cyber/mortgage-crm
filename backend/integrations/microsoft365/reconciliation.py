"""Reconciliation engine.

Given an inbound email or Teams message, find the CRM records (leads, loans,
partners) it belongs to, with a confidence score.

Strategy ladder:
  1. exact_email_match           — sender or recipient <-> lead.email
  2. loan_number_in_subject      — regex match on subject/body
  3. partner_domain_rule         — sender domain <-> referral_partner company domain
  4. conversation_thread         — same conversation_id as a previously linked email
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    MSEmailReconciliation,
    ReconciliationLinkType,
    ReconciliationStatus,
)

from database.models.lead_loan import Lead, Loan
from database.models.referral import ReferralPartner


@dataclass
class CandidateMatch:
    link_type: ReconciliationLinkType
    link_id: int
    label: str
    confidence: float
    strategy: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_suggested_link(self) -> dict[str, Any]:
        return {
            "link_type": self.link_type.value,
            "link_id": self.link_id,
            "label": self.label,
            "confidence": self.confidence,
            "strategy": self.strategy,
            "metadata": self.metadata,
        }


@dataclass
class ReconciliationResult:
    status: ReconciliationStatus
    best_match: CandidateMatch | None
    suggestions: list[CandidateMatch]


def _strategy_exact_email(
    db: Session,
    *,
    organization_id: int,
    emails: Sequence[str],
) -> list[CandidateMatch]:
    if not emails:
        return []
    norm = {e.lower().strip() for e in emails if e}
    if not norm:
        return []

    leads = db.query(Lead).filter(
        Lead.organization_id == organization_id,
        Lead.email.in_(norm),
    ).limit(10).all()

    out: list[CandidateMatch] = []
    for lead in leads:
        name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Unknown"
        out.append(
            CandidateMatch(
                link_type=ReconciliationLinkType.LEAD,
                link_id=lead.id,
                label=f"{name} <{lead.email}>",
                confidence=0.97,
                strategy="exact_email_match",
                metadata={"matched_email": lead.email},
            )
        )
    return out


def _strategy_loan_number(
    db: Session, *, organization_id: int, text: str
) -> list[CandidateMatch]:
    if not text:
        return []
    s = get_settings()
    candidates: list[tuple[str, float]] = []
    for pattern in s.loan_number_patterns:
        for m in re.finditer(pattern, text):
            number = m.group(0)
            conf = 0.95 if "RCA" in number.upper() else 0.72
            candidates.append((_normalize_loan_number(number), conf))

    if not candidates:
        return []

    out: list[CandidateMatch] = []
    seen: set[int] = set()
    for number, conf in candidates:
        loans = db.query(Loan).filter(
            Loan.organization_id == organization_id,
            Loan.loan_number == number,
        ).limit(2).all()
        for loan in loans:
            if loan.id in seen:
                continue
            seen.add(loan.id)
            out.append(
                CandidateMatch(
                    link_type=ReconciliationLinkType.LOAN,
                    link_id=loan.id,
                    label=f"Loan {loan.loan_number} — {loan.borrower_name or 'unknown'}",
                    confidence=conf,
                    strategy="loan_number_in_subject",
                    metadata={"matched_token": number},
                )
            )
    return out


def _strategy_partner_domain(
    db: Session, *, organization_id: int, sender_email: str
) -> list[CandidateMatch]:
    if not sender_email or "@" not in sender_email:
        return []
    domain = sender_email.split("@", 1)[1].lower().strip()
    if not domain or domain in _COMMON_DOMAINS:
        return []

    partners = db.query(ReferralPartner).filter(
        ReferralPartner.organization_id == organization_id,
        ReferralPartner.email.ilike(f"%@{domain}"),
    ).limit(5).all()

    return [
        CandidateMatch(
            link_type=ReconciliationLinkType.PARTNER,
            link_id=p.id,
            label=f"{p.name} ({domain})",
            confidence=0.78,
            strategy="partner_domain_rule",
            metadata={"matched_domain": domain},
        )
        for p in partners
    ]


def _strategy_conversation_thread(
    db: Session,
    *,
    organization_id: int,
    conversation_id: str | None,
) -> list[CandidateMatch]:
    if not conversation_id:
        return []
    prior = db.query(MSEmailReconciliation).filter(
        MSEmailReconciliation.organization_id == organization_id,
        MSEmailReconciliation.conversation_id == conversation_id,
        MSEmailReconciliation.matched_link_id.isnot(None),
    ).order_by(MSEmailReconciliation.received_at.desc()).first()

    if not prior or prior.matched_link_type is None or prior.matched_link_id is None:
        return []
    return [
        CandidateMatch(
            link_type=ReconciliationLinkType(prior.matched_link_type),
            link_id=prior.matched_link_id,
            label="Same thread as previously linked email",
            confidence=0.93,
            strategy="conversation_thread",
            metadata={"prior_email_id": prior.id},
        )
    ]


def reconcile_email(
    db: Session,
    *,
    organization_id: int,
    sender_email: str,
    recipient_emails: Sequence[str],
    subject: str,
    body_preview: str | None,
    conversation_id: str | None,
) -> ReconciliationResult:
    all_emails = [sender_email, *recipient_emails]
    haystack = f"{subject}\n{body_preview or ''}"

    candidates: list[CandidateMatch] = []
    candidates.extend(_strategy_conversation_thread(
        db, organization_id=organization_id, conversation_id=conversation_id
    ))
    candidates.extend(_strategy_exact_email(
        db, organization_id=organization_id, emails=all_emails
    ))
    candidates.extend(_strategy_loan_number(
        db, organization_id=organization_id, text=haystack
    ))
    candidates.extend(_strategy_partner_domain(
        db, organization_id=organization_id, sender_email=sender_email
    ))

    return _resolve(candidates)


def reconcile_teams_message(
    db: Session,
    *,
    organization_id: int,
    sender_email: str,
    body_text: str | None,
) -> ReconciliationResult:
    candidates: list[CandidateMatch] = []
    candidates.extend(_strategy_exact_email(
        db, organization_id=organization_id, emails=[sender_email]
    ))
    if body_text:
        candidates.extend(_strategy_loan_number(
            db, organization_id=organization_id, text=body_text
        ))
    candidates.extend(_strategy_partner_domain(
        db, organization_id=organization_id, sender_email=sender_email
    ))
    return _resolve(candidates)


def _resolve(candidates: list[CandidateMatch]) -> ReconciliationResult:
    s = get_settings()
    if not candidates:
        return ReconciliationResult(
            status=ReconciliationStatus.UNMATCHED,
            best_match=None,
            suggestions=[],
        )

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    best = candidates[0]

    if best.confidence >= s.auto_link_threshold:
        status = ReconciliationStatus.AUTO_LINKED
    elif best.confidence >= s.suggest_threshold:
        status = ReconciliationStatus.SUGGESTED
    else:
        status = ReconciliationStatus.UNMATCHED

    seen: set[tuple[str, int]] = set()
    deduped: list[CandidateMatch] = []
    for c in candidates:
        key = (c.link_type.value, c.link_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    return ReconciliationResult(
        status=status,
        best_match=best if status != ReconciliationStatus.UNMATCHED else None,
        suggestions=deduped[:10],
    )


_COMMON_DOMAINS = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "outlook.com",
        "hotmail.com",
        "icloud.com",
        "aol.com",
        "live.com",
        "me.com",
        "msn.com",
        "mac.com",
        "comcast.net",
        "verizon.net",
        "att.net",
    }
)


def _normalize_loan_number(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", raw).upper()
