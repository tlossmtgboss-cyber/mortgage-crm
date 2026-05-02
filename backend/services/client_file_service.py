from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.client_file import ClientFile


def ensure_client_file(db: Session, lead) -> ClientFile:
    existing = db.execute(
        select(ClientFile).where(ClientFile.lead_id == lead.id)
    ).scalar_one_or_none()
    if existing:
        return existing
    cf = ClientFile(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        first_name=lead.first_name,
        last_name=lead.last_name,
        primary_email=lead.email,
        primary_phone=getattr(lead, "phone", None),
        lifecycle_stage="new_lead",
        source=getattr(lead, "source", None),
        assigned_loan_officer_id=lead.owner_id,
    )
    db.add(cf)
    db.flush()
    return cf
