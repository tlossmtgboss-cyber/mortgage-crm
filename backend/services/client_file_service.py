from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.client_file import ClientFile


def _split_name(lead) -> tuple:
    first = getattr(lead, "first_name", None)
    last = getattr(lead, "last_name", None)
    if first and last:
        return first, last
    full = getattr(lead, "name", None) or ""
    if full.strip():
        parts = full.strip().split(" ", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""
    return first or "", last or ""


def ensure_client_file(db: Session, lead) -> ClientFile:
    existing = db.execute(
        select(ClientFile).where(ClientFile.lead_id == lead.id)
    ).scalar_one_or_none()
    if existing:
        if not existing.first_name and not existing.last_name:
            first, last = _split_name(lead)
            if first or last:
                existing.first_name = first
                existing.last_name = last
                db.flush()
        return existing
    first, last = _split_name(lead)
    cf = ClientFile(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        first_name=first,
        last_name=last,
        primary_email=lead.email,
        primary_phone=getattr(lead, "phone", None),
        lifecycle_stage="new_lead",
        source=getattr(lead, "source", None),
        assigned_loan_officer_id=lead.owner_id,
    )
    db.add(cf)
    db.flush()
    return cf
