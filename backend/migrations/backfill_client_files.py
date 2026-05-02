import logging
from db import SessionLocal
from database.models import Lead
from database.models.client_file import ClientFile

logger = logging.getLogger(__name__)

STAGE_MAP = {
    'FUNDED': 'closed_active',
    'CANCELLED': 'dead', 'DENIED': 'dead', 'DEAD': 'dead',
    'WITHDRAWN': 'dead', 'DOES_NOT_QUALIFY': 'dead',
    'NURTURE': 'nurture',
    'APPLICATION': 'pre_app', 'DISCLOSED': 'pre_app',
    'PROCESSING': 'in_processing', 'SUBMITTED': 'in_processing',
    'UNDERWRITING': 'in_underwriting', 'UW_RECEIVED': 'in_underwriting',
    'CONDITIONAL_APPROVAL': 'in_underwriting', 'APPROVED': 'in_underwriting',
    'SUSPENDED': 'in_underwriting',
    'CTC': 'clear_to_close', 'CLEAR_TO_CLOSE': 'clear_to_close',
    'CLOSING': 'clear_to_close', 'DOCS': 'clear_to_close',
    'DOCS_OUT': 'clear_to_close',
}

BATCH_SIZE = 500

def backfill():
    db = SessionLocal()
    try:
        total = db.query(Lead).count()
        logger.info(f"Backfilling client_files from {total} leads")
        created = 0
        skipped = 0
        for lead in db.query(Lead).yield_per(BATCH_SIZE):
            existing = db.query(ClientFile).filter(
                ClientFile.lead_id == lead.id
            ).first()
            if existing:
                skipped += 1
                continue
            prop_addr = None
            if lead.city:
                prop_addr = {
                    'city': lead.city, 'state': lead.state,
                    'zip': lead.zip_code, 'street': lead.address,
                }
            cf = ClientFile(
                organization_id=lead.organization_id,
                lead_id=lead.id,
                first_name=lead.first_name,
                last_name=lead.last_name,
                primary_email=lead.email,
                primary_phone=lead.phone,
                lifecycle_stage=STAGE_MAP.get(
                    (lead.stage or '').upper(), 'new_lead'
                ),
                source=lead.source,
                preferred_channel=lead.preferred_communication,
                assigned_loan_officer_id=lead.owner_id,
                property_address=prop_addr,
                active_loan_program=lead.program,
                active_loan_purpose=lead.loan_purpose,
                active_loan_amount=lead.loan_amount,
                active_loan_fico=lead.credit_score,
                active_loan_ltv=lead.ltv,
                active_loan_lock_expires_at=lead.lock_expiration,
                active_loan_projected_close_date=lead.closing_date,
                last_contact_at=lead.last_contact,
            )
            db.add(cf)
            created += 1
            if created % BATCH_SIZE == 0:
                db.commit()
                logger.info(f"  committed batch: {created} created, {skipped} skipped")
        db.commit()
        logger.info(f"Backfill complete: {created} created, {skipped} skipped (of {total} leads)")
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backfill()
