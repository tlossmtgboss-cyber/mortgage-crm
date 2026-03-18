"""
DRE Data Applicator — Apply AI-extracted data to CRM entities.

Functions:
    apply_extracted_data — Save extracted fields to loan/lead/partner/portfolio records
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from services.dre._base import _ensure_models
from services.dre.milestone_tasks import create_milestone_tasks, create_lead_milestone_tasks

logger = logging.getLogger(__name__)


def apply_extracted_data(extracted_data, db: Session) -> bool:
    """Apply extracted data to CRM entities - save all extracted fields to the borrower's profile"""
    _ensure_models()
    from services.dre._base import (
        Loan, Lead, MUMClient, ReferralPartner, LoanStage, LeadStage,
    )

    def get_field_value(fields: dict, field_name: str, min_confidence: float = 0.70):
        """Helper to safely get field value if confidence is high enough"""
        if field_name in fields:
            field = fields[field_name]
            if isinstance(field, dict) and field.get("confidence", 0) >= min_confidence:
                return field.get("value")
        return None

    def parse_date(date_str):
        """Parse various date formats to datetime"""
        if not date_str:
            return None
        try:
            if isinstance(date_str, datetime):
                return date_str
            return datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        except (ValueError, TypeError):
            try:
                from dateutil import parser
                return parser.parse(str(date_str))
            except (ValueError, TypeError):
                return None

    try:
        fields = extracted_data.fields or {}
        updated_fields = []

        if extracted_data.match_entity_type == "loan" and extracted_data.match_entity_id:
            loan = db.query(Loan).filter(Loan.id == extracted_data.match_entity_id).first()
            if not loan:
                logger.warning(f"Loan {extracted_data.match_entity_id} not found for data application - approving without applying data")
                return True

            logger.info(f"Applying extracted data to loan {loan.id} ({loan.loan_number})")

            # Capture old stage for SLA tracking
            _dre_old_stage = loan.stage
            if _dre_old_stage and hasattr(_dre_old_stage, 'value'):
                _dre_old_stage = _dre_old_stage.value

            if value := get_field_value(fields, "borrower_name"):
                loan.borrower_name = str(value)
                updated_fields.append("borrower_name")
            elif get_field_value(fields, "first_name") or get_field_value(fields, "last_name"):
                first = get_field_value(fields, "first_name") or ""
                last = get_field_value(fields, "last_name") or ""
                full_name = f"{first} {last}".strip()
                if full_name:
                    loan.borrower_name = full_name
                    updated_fields.append("borrower_name")

            if value := get_field_value(fields, "borrower_email"):
                loan.borrower_email = str(value)
                updated_fields.append("borrower_email")

            if value := get_field_value(fields, "borrower_phone"):
                loan.borrower_phone = str(value)
                updated_fields.append("borrower_phone")

            if value := get_field_value(fields, "coborrower_name"):
                loan.coborrower_name = str(value)
                updated_fields.append("coborrower_name")

            if value := get_field_value(fields, "amount"):
                loan.amount = float(value)
                updated_fields.append("amount")
            elif value := get_field_value(fields, "loan_amount"):
                loan.amount = float(value)
                updated_fields.append("amount")

            if value := get_field_value(fields, "rate"):
                loan.rate = float(value)
                updated_fields.append("rate")

            if value := get_field_value(fields, "program"):
                loan.program = str(value)
                updated_fields.append("program")

            if value := get_field_value(fields, "property_address"):
                loan.property_address = str(value)
                updated_fields.append("property_address")

            if value := get_field_value(fields, "property_city"):
                loan.property_city = str(value)
                updated_fields.append("property_city")

            if value := get_field_value(fields, "property_state"):
                loan.property_state = str(value)
                updated_fields.append("property_state")

            if value := get_field_value(fields, "property_zip"):
                loan.property_zip = str(value)
                updated_fields.append("property_zip")

            if value := get_field_value(fields, "processor"):
                loan.processor = str(value)
                updated_fields.append("processor")

            if value := get_field_value(fields, "underwriter"):
                loan.underwriter = str(value)
                updated_fields.append("underwriter")

            if value := get_field_value(fields, "lender"):
                loan.lender = str(value)
                updated_fields.append("lender")

            if value := get_field_value(fields, "realtor_name"):
                loan.realtor_agent = str(value)
                updated_fields.append("realtor_agent")

            if value := get_field_value(fields, "title_company"):
                loan.title_company = str(value)
                updated_fields.append("title_company")

            if value := get_field_value(fields, "closing_date"):
                if parsed := parse_date(value):
                    loan.closing_date = parsed
                    updated_fields.append("closing_date")
            elif value := get_field_value(fields, "closing_scheduled_date"):
                if parsed := parse_date(value):
                    loan.closing_date = parsed
                    updated_fields.append("closing_date")

            if value := get_field_value(fields, "rate_lock_date"):
                if parsed := parse_date(value):
                    loan.lock_date = parsed
                    updated_fields.append("lock_date")

            if value := get_field_value(fields, "lock_expiration"):
                if parsed := parse_date(value):
                    loan.lock_expiration_date = parsed
                    updated_fields.append("lock_expiration_date")

            if value := get_field_value(fields, "appraisal_ordered_date"):
                if parsed := parse_date(value):
                    loan.appraisal_ordered_date = parsed
                    updated_fields.append("appraisal_ordered_date")

            if value := get_field_value(fields, "appraisal_scheduled_date"):
                if parsed := parse_date(value):
                    loan.appraisal_scheduled_date = parsed
                    updated_fields.append("appraisal_scheduled_date")

            if value := get_field_value(fields, "appraisal_completed_date"):
                if parsed := parse_date(value):
                    loan.appraisal_completed_date = parsed
                    updated_fields.append("appraisal_completed_date")

            if value := get_field_value(fields, "appraisal_value"):
                loan.appraisal_value = float(value)
                updated_fields.append("appraisal_value")

            if value := get_field_value(fields, "initial_disclosures_sent_date"):
                if parsed := parse_date(value):
                    loan.initial_disclosures_sent_date = parsed
                    updated_fields.append("initial_disclosures_sent_date")

            if value := get_field_value(fields, "initial_disclosures_signed_date"):
                if parsed := parse_date(value):
                    loan.initial_disclosures_signed_date = parsed
                    updated_fields.append("initial_disclosures_signed_date")

            if value := get_field_value(fields, "cd_received_signed_date"):
                if parsed := parse_date(value):
                    loan.cd_received_signed_date = parsed
                    updated_fields.append("cd_received_signed_date")

            if value := get_field_value(fields, "final_closing_package_sent_date"):
                if parsed := parse_date(value):
                    loan.final_closing_package_sent_date = parsed
                    updated_fields.append("final_closing_package_sent_date")
                    if loan.stage != LoanStage.FUNDED:
                        loan.stage = LoanStage.CTC
                        updated_fields.append("stage->CTC")

            if value := get_field_value(fields, "borrower_name"):
                if not loan.borrower_name or loan.borrower_name.strip() == "":
                    loan.borrower_name = str(value)
                    updated_fields.append("borrower_name")

            if value := get_field_value(fields, "milestone", min_confidence=0.85):
                milestone = str(value).lower()
                if "clearto" in milestone or "ctc" in milestone:
                    loan.stage = LoanStage.CTC
                    updated_fields.append("stage->CTC")
                elif "approved" in milestone:
                    loan.stage = LoanStage.APPROVED
                    updated_fields.append("stage->APPROVED")
                elif "processing" in milestone:
                    loan.stage = LoanStage.PROCESSING
                    updated_fields.append("stage->PROCESSING")
                elif "u/w" in milestone or "underwriting" in milestone or "received" in milestone:
                    loan.stage = LoanStage.UW_RECEIVED
                    updated_fields.append("stage->UW_RECEIVED")
                elif "submitted" in milestone:
                    loan.stage = LoanStage.SUBMITTED
                    updated_fields.append("stage->SUBMITTED")
                elif "funded" in milestone:
                    loan.stage = LoanStage.FUNDED
                    loan.funded_date = datetime.now(timezone.utc)
                    updated_fields.append("stage->FUNDED")

            loan.updated_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(f"Applied {len(updated_fields)} fields to loan {loan.loan_number}: {', '.join(updated_fields)}")

            # Wire to SLA tracking -- detect stage changes from email parsing
            new_stage = loan.stage
            if new_stage and hasattr(new_stage, 'value'):
                new_stage = new_stage.value
            if new_stage and new_stage != _dre_old_stage:
                try:
                    from services.sla_tracking_service import track_loan_stage_change
                    track_loan_stage_change(
                        db, loan.id, _dre_old_stage, new_stage,
                        loan_number=loan.loan_number,
                        organization_id=getattr(loan, "organization_id", None),
                    )
                except Exception as e_sla:
                    logger.warning(f"SLA tracking hook failed for DRE loan {loan.id}: {e_sla}")

            tasks_created = create_milestone_tasks(loan, updated_fields, db)
            if tasks_created:
                logger.info(f"Created {len(tasks_created)} tasks for loan {loan.loan_number}: {tasks_created}")
            return True

        elif extracted_data.match_entity_type == "lead" and extracted_data.match_entity_id:
            lead = db.query(Lead).filter(Lead.id == extracted_data.match_entity_id).first()
            if not lead:
                logger.warning(f"Lead {extracted_data.match_entity_id} not found for data application - approving without applying data")
                return True

            logger.info(f"Applying extracted data to lead {lead.id} ({lead.name})")

            if value := get_field_value(fields, "borrower_name"):
                lead.name = str(value)
                updated_fields.append("name")
            elif get_field_value(fields, "first_name") or get_field_value(fields, "last_name"):
                first = get_field_value(fields, "first_name") or ""
                last = get_field_value(fields, "last_name") or ""
                full_name = f"{first} {last}".strip()
                if full_name:
                    lead.name = full_name
                    updated_fields.append("name")

            if value := get_field_value(fields, "email"):
                lead.email = str(value)
                updated_fields.append("email")
            elif value := get_field_value(fields, "borrower_email"):
                lead.email = str(value)
                updated_fields.append("email")

            if value := get_field_value(fields, "phone"):
                lead.phone = str(value)
                updated_fields.append("phone")
            elif value := get_field_value(fields, "borrower_phone"):
                lead.phone = str(value)
                updated_fields.append("phone")

            if value := get_field_value(fields, "credit_score"):
                lead.credit_score = int(value)
                updated_fields.append("credit_score")

            if value := get_field_value(fields, "loan_amount"):
                lead.loan_amount = float(value)
                updated_fields.append("loan_amount")
            elif value := get_field_value(fields, "amount"):
                lead.loan_amount = float(value)
                updated_fields.append("loan_amount")

            if value := get_field_value(fields, "property_address"):
                lead.property_address = str(value)
                updated_fields.append("property_address")

            if value := get_field_value(fields, "program"):
                lead.loan_type = str(value)
                updated_fields.append("loan_type")

            if value := get_field_value(fields, "application_started_date"):
                if parsed := parse_date(value):
                    lead.application_started_date = parsed
                    updated_fields.append("application_started_date")

            if value := get_field_value(fields, "application_completed_date"):
                if parsed := parse_date(value):
                    lead.application_completed_date = parsed
                    updated_fields.append("application_completed_date")
                    db.execute(text("UPDATE leads SET stage = :stage WHERE id = :id"),
                               {"stage": LeadStage.APPLICATION.name, "id": lead.id})
                    updated_fields.append("stage->APPLICATION")

            if value := get_field_value(fields, "credit_pulled_date"):
                if parsed := parse_date(value):
                    lead.credit_pulled_date = parsed
                    updated_fields.append("credit_pulled_date")

            if value := get_field_value(fields, "preapproval_issued_date"):
                if parsed := parse_date(value):
                    lead.preapproval_issued_date = parsed
                    updated_fields.append("preapproval_issued_date")
                    db.execute(text("UPDATE leads SET stage = :stage WHERE id = :id"),
                               {"stage": LeadStage.PRE_APPROVED.name, "id": lead.id})
                    updated_fields.append("stage->PRE_APPROVED")

            lead.updated_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(f"Applied {len(updated_fields)} fields to lead {lead.name}: {', '.join(updated_fields)}")

            tasks_created = create_lead_milestone_tasks(lead, updated_fields, db)
            if tasks_created:
                logger.info(f"Created {len(tasks_created)} tasks for lead {lead.name}: {tasks_created}")
            return True

        elif extracted_data.match_entity_type == "partner" and extracted_data.match_entity_id:
            partner = db.query(ReferralPartner).filter(ReferralPartner.id == extracted_data.match_entity_id).first()
            if not partner:
                logger.warning(f"Partner {extracted_data.match_entity_id} not found for data application")
                return True

            logger.info(f"Applying extracted data to partner {partner.id} ({partner.name})")

            if value := get_field_value(fields, "partner_name"):
                partner.name = str(value)
                updated_fields.append("name")
            elif value := get_field_value(fields, "agent_name"):
                partner.name = str(value)
                updated_fields.append("name")
            elif value := get_field_value(fields, "realtor_name"):
                partner.name = str(value)
                updated_fields.append("name")

            if value := get_field_value(fields, "partner_email"):
                partner.email = str(value)
                updated_fields.append("email")
            elif value := get_field_value(fields, "agent_email"):
                partner.email = str(value)
                updated_fields.append("email")

            if value := get_field_value(fields, "partner_phone"):
                partner.phone = str(value)
                updated_fields.append("phone")
            elif value := get_field_value(fields, "agent_phone"):
                partner.phone = str(value)
                updated_fields.append("phone")

            if value := get_field_value(fields, "partner_company"):
                partner.company = str(value)
                updated_fields.append("company")
            elif value := get_field_value(fields, "brokerage"):
                partner.company = str(value)
                updated_fields.append("company")

            partner.last_interaction = datetime.now(timezone.utc)
            updated_fields.append("last_interaction")

            db.commit()
            logger.info(f"Applied {len(updated_fields)} fields to partner {partner.name}: {', '.join(updated_fields)}")
            return True

        elif extracted_data.match_entity_type == "portfolio" and extracted_data.match_entity_id:
            try:
                client = db.query(MUMClient).filter(MUMClient.id == extracted_data.match_entity_id).first()
                if not client:
                    logger.warning(f"Portfolio client {extracted_data.match_entity_id} not found")
                    return True

                logger.info(f"Applying extracted data to portfolio client {client.id} ({client.name})")

                if value := get_field_value(fields, "borrower_name"):
                    client.name = str(value)
                    updated_fields.append("name")

                if value := get_field_value(fields, "borrower_email"):
                    client.email = str(value)
                    updated_fields.append("email")
                elif value := get_field_value(fields, "email"):
                    client.email = str(value)
                    updated_fields.append("email")

                if value := get_field_value(fields, "borrower_phone"):
                    client.phone = str(value)
                    updated_fields.append("phone")
                elif value := get_field_value(fields, "phone"):
                    client.phone = str(value)
                    updated_fields.append("phone")

                db.commit()
                logger.info(f"Applied {len(updated_fields)} fields to portfolio client {client.name}: {', '.join(updated_fields)}")
            except Exception as e:
                logger.warning(f"Portfolio client update failed: {e}")
            return True

        logger.info("No matched entity to apply data to")
        return True

    except Exception as e:
        logger.error(f"Apply extracted data error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
