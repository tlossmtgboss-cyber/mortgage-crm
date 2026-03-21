"""
DRE Entity Matcher — Match extracted email fields to CRM entities.

Functions:
    match_entity   — Multi-strategy entity matching (loan number, name, email, phone)
    get_entity_name — Look up display name for a matched entity
"""
import logging
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, text

from services.dre._base import _ensure_models

logger = logging.getLogger(__name__)


def match_entity(fields: Dict[str, Any], db: Session, user_id: int, organization_id: int = None) -> Dict[str, Any]:
    """Match extracted fields to existing CRM entities

    Enhanced matching includes:
    - Loan number exact and partial matching
    - Borrower name matching (primary and co-borrower)
    - Last name matching for spouse/family identification
    - Email and phone matching for leads
    - Combined first_name + last_name support

    Args:
        organization_id: Tenant filter. When provided, lead queries are scoped
                         to this organization to prevent cross-tenant data leakage.
    """
    _ensure_models()
    from services.dre._base import (
        Loan, Lead, MUMClient, ReferralPartner, LoanStage,
    )

    match_results = {
        "entity_type": None,
        "entity_id": None,
        "confidence": 0.0,
        "candidates": []
    }

    def get_last_name(full_name: str) -> str:
        """Extract last name from full name"""
        if not full_name:
            return ""
        parts = full_name.strip().split()
        return parts[-1].lower() if parts else ""

    def names_match(name1: str, name2: str) -> tuple:
        """Check if names match - returns (is_match, confidence)"""
        if not name1 or not name2:
            return False, 0.0
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        # Exact match
        if n1 == n2:
            return True, 0.95

        # One contains the other (partial name match)
        if n1 in n2 or n2 in n1:
            return True, 0.80

        def normalize_name(name: str) -> set:
            """Extract name parts, handling 'Last, First' and 'First Last' formats"""
            name = name.lower().strip()
            if ',' in name:
                parts = [p.strip() for p in name.split(',')]
                parts = list(reversed(parts))
            else:
                parts = name.split()
            return set(p for p in parts if len(p) > 1)

        parts1 = normalize_name(n1)
        parts2 = normalize_name(n2)

        common_parts = parts1 & parts2
        if len(common_parts) >= 2:
            return True, 0.90

        if len(common_parts) == 1:
            ln1 = get_last_name(name1)
            ln2 = get_last_name(name2)
            if ln1 and ln2 and ln1 == ln2:
                return True, 0.75

        ln1, ln2 = get_last_name(name1), get_last_name(name2)
        if ln1 and ln2 and ln1 == ln2:
            return True, 0.75

        return False, 0.0

    def normalize_phone(phone: str) -> str:
        """Normalize phone number for comparison"""
        if not phone:
            return ""
        return ''.join(c for c in phone if c.isdigit())[-10:]

    def normalize_email(email: str) -> str:
        """Normalize email for comparison"""
        if not email:
            return ""
        return email.lower().strip()

    # Build combined borrower name from first_name + last_name if not already present
    borrower_name = None
    if "borrower_name" in fields and fields["borrower_name"].get("value"):
        borrower_name = fields["borrower_name"]["value"]
    elif "first_name" in fields or "last_name" in fields:
        first = fields.get("first_name", {}).get("value", "") or ""
        last = fields.get("last_name", {}).get("value", "") or ""
        if first or last:
            borrower_name = f"{first} {last}".strip()
            logger.info(f"Built borrower_name from first_name + last_name: '{borrower_name}'")

    # Extract email and phone from fields
    extracted_email = None
    extracted_phone = None
    if "borrower_email" in fields and fields["borrower_email"].get("value"):
        extracted_email = normalize_email(fields["borrower_email"]["value"])
    if "borrower_phone" in fields and fields["borrower_phone"].get("value"):
        extracted_phone = normalize_phone(fields["borrower_phone"]["value"])

    logger.info(f"=" * 60)
    logger.info(f"MATCH_ENTITY DEBUG - Starting match process")
    logger.info(f"=" * 60)
    logger.info(f"Input fields: {list(fields.keys()) if fields else 'None'}")
    logger.info(f"Extracted borrower_name: '{borrower_name}'")
    logger.info(f"Extracted email: '{extracted_email}'")
    logger.info(f"Extracted phone: '{extracted_phone}'")

    # Collect all potential loan numbers from various fields
    loan_numbers_to_try = []
    if "loan_number" in fields and fields["loan_number"].get("value"):
        loan_numbers_to_try.append(str(fields["loan_number"]["value"]).strip())
    if "file_number" in fields and fields["file_number"].get("value"):
        loan_numbers_to_try.append(str(fields["file_number"]["value"]).strip())
    if "cmg_file_number" in fields and fields["cmg_file_number"].get("value"):
        loan_numbers_to_try.append(str(fields["cmg_file_number"]["value"]).strip())
    if "lender_loan_number" in fields and fields["lender_loan_number"].get("value"):
        loan_numbers_to_try.append(str(fields["lender_loan_number"]["value"]).strip())
    if "investor_loan_number" in fields and fields["investor_loan_number"].get("value"):
        loan_numbers_to_try.append(str(fields["investor_loan_number"]["value"]).strip())

    # Remove duplicates while preserving order
    loan_numbers_to_try = list(dict.fromkeys(loan_numbers_to_try))
    logger.info(f"Loan numbers to try: {loan_numbers_to_try}")
    logger.info(f"Total loan numbers to match: {len(loan_numbers_to_try)}")

    # Try to match by loan number first (highest confidence)
    for loan_num in loan_numbers_to_try:
        loan_num_upper = loan_num.upper()
        logger.info(f"Attempting to match loan number: '{loan_num}'")

        def get_loan_entity_type(loan_obj):
            """Return 'portfolio' for funded loans, 'loan' for active loans"""
            if loan_obj and loan_obj.stage == LoanStage.FUNDED:
                return "portfolio"
            return "loan"

        # ========== CHECK MUM CLIENTS FIRST (Portfolio) ==========
        logger.info(f"[MUM] Searching MUM clients for loan_number='{loan_num}'")
        try:
            total_mum = db.query(MUMClient).count()
            logger.info(f"[MUM] Total MUM clients in database: {total_mum}")

            mum_client = db.query(MUMClient).filter(
                func.upper(MUMClient.loan_number) == loan_num_upper
            ).first()

            if mum_client:
                logger.info(f"[MUM] EXACT MATCH: {mum_client.name} (id={mum_client.id}, loan#={mum_client.loan_number})")
                match_results["candidates"].append({
                    "type": "portfolio",
                    "id": mum_client.id,
                    "name": mum_client.name,
                    "loan_number": mum_client.loan_number,
                    "confidence": 0.98,
                    "match_type": "mum_loan_number_exact"
                })
            else:
                logger.info(f"[MUM] No exact match for loan_number='{loan_num}'")
                mum_clients = db.query(MUMClient).filter(
                    MUMClient.loan_number.ilike(f"%{loan_num}%")
                ).all()
                logger.info(f"[MUM] Partial match search found {len(mum_clients)} clients")
                for client in mum_clients:
                    logger.info(f"[MUM] PARTIAL MATCH: {client.name} (loan#={client.loan_number})")
                    match_results["candidates"].append({
                        "type": "portfolio",
                        "id": client.id,
                        "name": client.name,
                        "loan_number": client.loan_number,
                        "confidence": 0.92,
                        "match_type": "mum_loan_number_partial"
                    })
        except Exception as e:
            logger.warning(f"MUM client loan number matching error: {e}")

        # ========== ACTIVE LOAN PROFILE MATCHING ==========
        try:
            from models.active_loan_profile import ActiveLoanProfile

            active_loan = db.query(ActiveLoanProfile).filter(
                func.upper(ActiveLoanProfile.loan_number) == loan_num_upper,
                ActiveLoanProfile.is_deleted == False
            ).first()

            if active_loan:
                logger.info(f"Found match in ActiveLoanProfile: {active_loan.id}")
                match_results["candidates"].append({
                    "type": "active_loan",
                    "id": str(active_loan.id),
                    "name": f"Active Loan {active_loan.loan_number}",
                    "loan_number": active_loan.loan_number,
                    "confidence": 0.99,
                    "match_type": "active_loan_exact"
                })
            else:
                active_loans = db.query(ActiveLoanProfile).filter(
                    ActiveLoanProfile.loan_number.ilike(f"%{loan_num}%"),
                    ActiveLoanProfile.is_deleted == False
                ).all()

                for al in active_loans:
                    logger.info(f"Found partial match in ActiveLoanProfile: {al.id}")
                    match_results["candidates"].append({
                        "type": "active_loan",
                        "id": str(al.id),
                        "name": f"Active Loan {al.loan_number}",
                        "loan_number": al.loan_number,
                        "confidence": 0.90,
                        "match_type": "active_loan_partial"
                    })

        except Exception as e:
            logger.debug(f"ActiveLoanProfile check skipped: {e}")

        # ========== REGULAR LOAN TABLE MATCHING ==========
        try:
            loan = db.query(Loan).filter(
                func.upper(Loan.loan_number) == loan_num_upper,
                Loan.loan_officer_id == user_id
            ).first()

            if loan:
                entity_type = get_loan_entity_type(loan)
                logger.info(f"Found exact match with user's loan: {loan.id} (type: {entity_type})")
                match_results["candidates"].append({
                    "type": entity_type,
                    "id": loan.id,
                    "name": loan.borrower_name,
                    "loan_number": loan.loan_number,
                    "confidence": 0.98,
                    "match_type": "loan_user_owned_exact"
                })
            else:
                loan = db.query(Loan).filter(
                    func.upper(Loan.loan_number) == loan_num_upper
                ).first()
                if loan:
                    entity_type = get_loan_entity_type(loan)
                    logger.info(f"Found exact match (any user): {loan.id} (type: {entity_type})")
                    match_results["candidates"].append({
                        "type": entity_type,
                        "id": loan.id,
                        "name": loan.borrower_name,
                        "loan_number": loan.loan_number,
                        "confidence": 0.95,
                        "match_type": "loan_exact"
                    })
                else:
                    logger.info(f"Trying partial match for: {loan_num}")
                    loans = db.query(Loan).filter(
                        Loan.loan_number.ilike(f"%{loan_num}%")
                    ).all()
                    logger.info(f"Found {len(loans)} partial matches")
                    for l in loans:
                        entity_type = get_loan_entity_type(l)
                        conf = 0.90 if l.loan_officer_id == user_id else 0.85
                        match_results["candidates"].append({
                            "type": entity_type,
                            "id": l.id,
                            "name": l.borrower_name,
                            "loan_number": l.loan_number,
                            "confidence": conf,
                            "match_type": "loan_partial"
                        })
        except Exception as e:
            logger.warning(f"Loan table matching error: {e}")

        # If we have loan number candidates, pick the best one and return early
        if match_results["candidates"]:
            best = max(match_results["candidates"], key=lambda x: x["confidence"])
            logger.info(f"Best loan number match: {best['type']} id={best['id']} conf={best['confidence']:.2f}")
            match_results["entity_type"] = best["type"]
            match_results["entity_id"] = best["id"]
            match_results["confidence"] = best["confidence"]
            return match_results

    # ========== LEAD MATCHING (Email, Phone, Name) ==========
    if extracted_email:
        logger.info(f"Trying email match: '{extracted_email}'")
        email_leads = db.query(Lead).filter(
            Lead.email.ilike(extracted_email)
        ).all()
        for lead in email_leads:
            conf = 0.98 if lead.owner_id == user_id else 0.92
            match_results["candidates"].append({
                "type": "lead",
                "id": lead.id,
                "name": lead.name,
                "confidence": conf,
                "match_type": "email_exact"
            })
            logger.info(f"Email match found: Lead {lead.id} - {lead.name}")

    # Try phone matching (high confidence)
    if extracted_phone and len(extracted_phone) >= 10:
        logger.info(f"Trying phone match: '{extracted_phone}'")
        # TENANT-002: Scope lead query to organization to prevent cross-tenant leakage
        lead_query = db.query(Lead)
        if organization_id:
            lead_query = lead_query.filter(Lead.organization_id == organization_id)
        all_leads = lead_query.all()
        for lead in all_leads:
            if lead.phone:
                lead_phone = normalize_phone(lead.phone)
                if lead_phone and lead_phone == extracted_phone:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "lead" and c["id"] == lead.id), None)
                    if not existing:
                        conf = 0.95 if lead.owner_id == user_id else 0.88
                        match_results["candidates"].append({
                            "type": "lead",
                            "id": lead.id,
                            "name": lead.name,
                            "confidence": conf,
                            "match_type": "phone_exact"
                        })
                        logger.info(f"Phone match found: Lead {lead.id} - {lead.name}")

    # Try to match by borrower name
    borrower_last_name = get_last_name(borrower_name) if borrower_name else ""
    if borrower_name:
        logger.info(f"Attempting to match borrower name: '{borrower_name}' (last name: '{borrower_last_name}')")

        # TENANT-002: Scope lead query to organization to prevent cross-tenant leakage
        lead_name_query = db.query(Lead)
        if organization_id:
            lead_name_query = lead_name_query.filter(Lead.organization_id == organization_id)
        all_leads = lead_name_query.all()
        for lead in all_leads:
            if lead.name:
                is_match, conf = names_match(borrower_name, lead.name)
                if is_match:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "lead" and c["id"] == lead.id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.1)
                        existing["match_type"] += "+name"
                    else:
                        final_conf = conf if lead.owner_id == user_id else conf * 0.90
                        match_results["candidates"].append({
                            "type": "lead",
                            "id": lead.id,
                            "name": lead.name,
                            "confidence": final_conf,
                            "match_type": "lead_name"
                        })
                        logger.info(f"Name match found: Lead {lead.id} - {lead.name} (conf: {final_conf:.2f})")

    # ========== LOAN MATCHING (Name, Email, Phone) ==========
    if borrower_name or extracted_email or extracted_phone:
        try:
            loan_results = db.execute(
                text("""
                    SELECT id, borrower_name, coborrower_name, loan_officer_id,
                           borrower_email, borrower_phone, co_borrower_email, loan_number
                    FROM loans
                    WHERE loan_officer_id = :user_id
                """),
                {"user_id": user_id}
            ).fetchall()
            logger.info(f"Found {len(loan_results)} loans for user {user_id}")
        except Exception as e:
            logger.error(f"Error querying user loans: {e}")
            loan_results = []

        for loan_row in loan_results:
            loan_id, loan_borrower_name, loan_coborrower_name, loan_officer_id, loan_borrower_email, loan_borrower_phone, loan_coborrower_email, loan_loan_number = loan_row

            # ===== EMAIL MATCHING =====
            if extracted_email and loan_borrower_email:
                if normalize_email(extracted_email) == normalize_email(loan_borrower_email):
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.15)
                        existing["match_type"] += "+email"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.96,
                            "match_type": "borrower_email"
                        })
                        logger.info(f"Loan email match: {loan_id} - {loan_borrower_name} (email: {loan_borrower_email})")

            if extracted_email and loan_coborrower_email:
                if normalize_email(extracted_email) == normalize_email(loan_coborrower_email):
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.12)
                        existing["match_type"] += "+coborrower_email"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": f"{loan_borrower_name} (co-borrower email match)",
                            "loan_number": loan_loan_number,
                            "confidence": 0.92,
                            "match_type": "coborrower_email"
                        })

            # ===== PHONE MATCHING =====
            if extracted_phone and loan_borrower_phone:
                if normalize_phone(extracted_phone) == normalize_phone(loan_borrower_phone):
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.12)
                        existing["match_type"] += "+phone"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.93,
                            "match_type": "borrower_phone"
                        })
                        logger.info(f"Loan phone match: {loan_id} - {loan_borrower_name}")

            # ===== NAME MATCHING =====
            if borrower_name and loan_borrower_name:
                is_match, conf = names_match(borrower_name, loan_borrower_name)
                if is_match:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.10)
                        existing["match_type"] += "+name"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": conf,
                            "match_type": "borrower_name"
                        })
                        logger.info(f"Loan borrower match: {loan_id} - {loan_borrower_name} (conf: {conf:.2f})")

            if borrower_name and loan_coborrower_name:
                is_match, conf = names_match(borrower_name, loan_coborrower_name)
                if is_match:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.08)
                        existing["match_type"] += "+coborrower_name"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": f"{loan_borrower_name} (co-borrower: {loan_coborrower_name})",
                            "loan_number": loan_loan_number,
                            "confidence": conf * 0.95,
                            "match_type": "coborrower_name"
                        })

            # Last name match
            if borrower_last_name:
                borrower_ln = get_last_name(loan_borrower_name) if loan_borrower_name else ""
                coborrower_ln = get_last_name(loan_coborrower_name) if loan_coborrower_name else ""

                if borrower_last_name == borrower_ln or borrower_last_name == coborrower_ln:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if not existing:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.75,
                            "match_type": "last_name_family"
                        })

        # If no matches found with user filter, try broader search for loans
        if not any(c["type"] == "loan" for c in match_results["candidates"]):
            logger.info("No loan matches with user filter, trying all loans...")
            try:
                all_loan_results = db.execute(
                    text("""
                        SELECT id, borrower_name, coborrower_name, loan_officer_id,
                               borrower_email, borrower_phone, co_borrower_email, loan_number
                        FROM loans
                    """)
                ).fetchall()
                logger.info(f"Found {len(all_loan_results)} total loans in database")
            except Exception as e:
                logger.error(f"Error querying all loans: {e}")
                all_loan_results = []

            for loan_row in all_loan_results:
                loan_id, loan_borrower_name, loan_coborrower_name, loan_officer_id, loan_borrower_email, loan_borrower_phone, loan_coborrower_email, loan_loan_number = loan_row

                if extracted_email and loan_borrower_email:
                    if normalize_email(extracted_email) == normalize_email(loan_borrower_email):
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.94,
                            "match_type": "borrower_email_global"
                        })
                        logger.info(f"Global loan email match: {loan_id} - {loan_borrower_name}")
                        continue

                if extracted_phone and loan_borrower_phone:
                    if normalize_phone(extracted_phone) == normalize_phone(loan_borrower_phone):
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.90,
                            "match_type": "borrower_phone_global"
                        })
                        logger.info(f"Global loan phone match: {loan_id} - {loan_borrower_name}")
                        continue

                if loan_borrower_name:
                    is_match, conf = names_match(borrower_name, loan_borrower_name)
                    if is_match:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": conf * 0.85,
                            "match_type": "borrower_name_global"
                        })
                        logger.info(f"Global loan borrower match: {loan_id} - {loan_borrower_name}")

                if loan_coborrower_name:
                    is_match, conf = names_match(borrower_name, loan_coborrower_name)
                    if is_match:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": f"{loan_borrower_name} (co-borrower: {loan_coborrower_name})",
                            "loan_number": loan_loan_number,
                            "confidence": conf * 0.80,
                            "match_type": "coborrower_name_global"
                        })

    # ========== PARTNER MATCHING (Referral Partners) ==========
    partner_name = fields.get("partner_name", {}).get("value") or fields.get("agent_name", {}).get("value") or fields.get("realtor_name", {}).get("value")
    partner_email = fields.get("partner_email", {}).get("value") or fields.get("agent_email", {}).get("value") or fields.get("realtor_email", {}).get("value")
    partner_phone = fields.get("partner_phone", {}).get("value") or fields.get("agent_phone", {}).get("value") or fields.get("realtor_phone", {}).get("value")
    partner_company = fields.get("partner_company", {}).get("value") or fields.get("brokerage", {}).get("value") or fields.get("company", {}).get("value")

    if partner_name or partner_email or partner_phone:
        logger.info(f"Trying partner match: name='{partner_name}', email='{partner_email}', phone='{partner_phone}'")
        all_partners = db.query(ReferralPartner).filter(ReferralPartner.status == "active").all()

        for partner in all_partners:
            partner_conf = 0.0
            match_reasons = []

            if partner_email and partner.email:
                if normalize_email(partner_email) == normalize_email(partner.email):
                    partner_conf = max(partner_conf, 0.95)
                    match_reasons.append("email")

            if partner_phone and partner.phone:
                if normalize_phone(partner_phone) == normalize_phone(partner.phone):
                    partner_conf = max(partner_conf, 0.90)
                    match_reasons.append("phone")

            if partner_name and partner.name:
                is_match, conf = names_match(partner_name, partner.name)
                if is_match:
                    partner_conf = max(partner_conf, conf * 0.90)
                    match_reasons.append("name")

            if partner_company and partner.company:
                if partner_company.lower().strip() in partner.company.lower() or partner.company.lower() in partner_company.lower().strip():
                    partner_conf = min(0.98, partner_conf + 0.10)
                    match_reasons.append("company")

            if partner_conf > 0.5:
                match_results["candidates"].append({
                    "type": "partner",
                    "id": partner.id,
                    "name": partner.name,
                    "confidence": partner_conf,
                    "match_type": "+".join(match_reasons)
                })
                logger.info(f"Partner match found: {partner.name} ({partner_conf:.2f}) via {'+'.join(match_reasons)}")

    # ========== PORTFOLIO/MUM CLIENT MATCHING (by name, email, phone) ==========
    if borrower_name or extracted_email or extracted_phone:
        logger.info(f"[MUM-NAME] Starting name/email/phone matching for borrower='{borrower_name}'")
        try:
            all_mum_clients = db.query(MUMClient).all()
            logger.info(f"[MUM-NAME] Checking {len(all_mum_clients)} MUM clients for name match")

            sample_names = [c.name for c in all_mum_clients[:5]]
            logger.info(f"[MUM-NAME] Sample MUM client names: {sample_names}")

            for client in all_mum_clients:
                existing = next((c for c in match_results["candidates"]
                               if c["type"] == "portfolio" and c["id"] == client.id), None)
                if existing:
                    continue

                client_conf = 0.0
                match_reasons = []

                if extracted_email and client.email:
                    if normalize_email(extracted_email) == normalize_email(client.email):
                        client_conf = max(client_conf, 0.95)
                        match_reasons.append("email")

                if extracted_phone and client.phone:
                    if normalize_phone(extracted_phone) == normalize_phone(client.phone):
                        client_conf = max(client_conf, 0.90)
                        match_reasons.append("phone")

                if borrower_name and client.name:
                    is_match, conf = names_match(borrower_name, client.name)
                    if is_match:
                        client_conf = max(client_conf, conf * 0.88)
                        match_reasons.append("name")

                if client_conf > 0.5:
                    match_results["candidates"].append({
                        "type": "portfolio",
                        "id": client.id,
                        "name": client.name,
                        "loan_number": client.loan_number,
                        "confidence": client_conf,
                        "match_type": "+".join(match_reasons)
                    })
                    logger.info(f"Portfolio match found: {client.name} ({client_conf:.2f}) via {'+'.join(match_reasons)}")
        except Exception as e:
            logger.warning(f"Portfolio matching failed (table may not exist): {e}")

    # Return best candidate if found
    logger.info(f"=" * 60)
    logger.info(f"MATCH_ENTITY DEBUG - Final Results")
    logger.info(f"=" * 60)
    logger.info(f"Total candidates found: {len(match_results['candidates'])}")

    if match_results["candidates"]:
        for i, cand in enumerate(match_results["candidates"]):
            logger.info(f"  Candidate {i+1}: {cand['type']} - {cand.get('name', 'N/A')} (id={cand['id']}, conf={cand['confidence']:.2f}, via={cand.get('match_type', 'unknown')})")

        best = max(match_results["candidates"], key=lambda x: x["confidence"])
        logger.info(f"BEST MATCH: {best['type']} - {best.get('name', 'N/A')} (id={best['id']}, conf={best['confidence']:.2f})")
        match_results["entity_type"] = best["type"]
        match_results["entity_id"] = best["id"]
        match_results["confidence"] = best["confidence"]
    else:
        logger.info("NO MATCH FOUND - All matching strategies failed")
        logger.info(f"  Searched with: name='{borrower_name}', email='{extracted_email}', phone='{extracted_phone}'")
        logger.info(f"  Loan numbers tried: {loan_numbers_to_try}")

    logger.info(f"=" * 60)
    return match_results


def get_entity_name(entity_type: str, entity_id, db: Session) -> str:
    """Get the name of the matched entity"""
    _ensure_models()
    from services.dre._base import Loan, Lead, MUMClient, ReferralPartner

    try:
        if entity_type == "loan":
            loan = db.query(Loan).filter(Loan.id == entity_id).first()
            return loan.borrower_name if loan and loan.borrower_name else f"Loan #{entity_id}"
        elif entity_type == "lead":
            lead = db.query(Lead).filter(Lead.id == entity_id).first()
            return lead.name if lead and lead.name else f"Lead #{entity_id}"
        elif entity_type == "active_loan":
            try:
                from models.active_loan_profile import ActiveLoanProfile
                from models.lead_profile import LeadProfile
                import uuid as uuid_mod

                if isinstance(entity_id, str):
                    try:
                        loan_uuid = uuid_mod.UUID(entity_id)
                    except ValueError:
                        loan_uuid = entity_id
                else:
                    loan_uuid = entity_id

                active_loan = db.query(ActiveLoanProfile).filter(
                    ActiveLoanProfile.id == loan_uuid
                ).first()

                if active_loan:
                    if active_loan.lead_profile_id:
                        lead_profile = db.query(LeadProfile).filter(
                            LeadProfile.id == active_loan.lead_profile_id
                        ).first()
                        if lead_profile:
                            name_parts = []
                            if lead_profile.first_name:
                                name_parts.append(lead_profile.first_name)
                            if lead_profile.last_name:
                                name_parts.append(lead_profile.last_name)
                            if name_parts:
                                return " ".join(name_parts)
                    return f"Portfolio Loan {active_loan.loan_number}"
            except Exception as e:
                logger.error(f"Error getting ActiveLoanProfile: {e}")
            return f"Portfolio Loan #{entity_id}"
        elif entity_type == "client":
            client = db.query(Lead).filter(Lead.id == entity_id).first()
            return client.name if client and client.name else f"Client #{entity_id}"
        elif entity_type == "portfolio":
            try:
                loan = db.query(Loan).filter(Loan.id == entity_id).first()
                if loan:
                    return loan.borrower_name if loan.borrower_name else f"Portfolio Loan #{entity_id}"
            except Exception as e:
                logger.exception(f"Failed to look up portfolio Loan for entity_id {entity_id}: {e}")
            mum_client = db.query(MUMClient).filter(MUMClient.id == entity_id).first()
            return mum_client.name if mum_client and mum_client.name else f"Portfolio Client #{entity_id}"
        elif entity_type == "partner":
            partner = db.query(ReferralPartner).filter(ReferralPartner.id == entity_id).first()
            return partner.name if partner and partner.name else f"Partner #{entity_id}"
    except Exception as e:
        logger.error(f"Error getting entity name: {e}")

    return f"{entity_type} #{entity_id}"
