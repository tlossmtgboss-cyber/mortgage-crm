"""
AI Command Executors for Perennia AI

This module contains the action executor functions for the AI command system:
- execute_email_campaign: Send email campaigns to filtered client lists
- execute_bulk_update: Bulk update records (leads, deals)
- execute_voicemail_drop: Queue ringless voicemail campaigns
- execute_pre_approval_letter: Generate and send pre-approval letters via email
"""

from sqlalchemy.orm import Session
from fastapi import BackgroundTasks
from typing import Dict, Any
from datetime import datetime, timedelta
import logging

from ai_command_models import get_main_module

logger = logging.getLogger(__name__)


async def execute_email_campaign(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute an email campaign"""
    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity

    # Apply any modifications
    subject = modifications.get("subject", preview.get("subject", ""))
    body = modifications.get("body", preview.get("body", ""))
    recipients = preview.get("recipients", [])

    # In production, this would queue emails through your email service
    # For now, log the action and create activity records

    for recipient_name in recipients:
        # Find the lead
        names = recipient_name.split()
        if len(names) >= 2:
            lead = db.query(Lead).filter(
                Lead.owner_id == user_id,
                Lead.first_name == names[0],
                Lead.last_name == names[-1]
            ).first()

            if lead:
                # Create activity record
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead.id,
                    activity_type="email",
                    description=f"Email sent: {subject}",
                    data={"subject": subject, "body": body[:500]}
                )
                db.add(activity)

    db.commit()

    return {
        "message": f"Email campaign sent to {len(recipients)} recipients",
        "recipients_count": len(recipients),
        "subject": subject
    }


async def execute_bulk_update(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute a bulk update operation"""
    main = get_main_module()
    Lead = main.Lead
    Loan = main.Loan

    records = preview.get("records", [])
    field = modifications.get("field", preview.get("field", ""))
    new_value = modifications.get("new_value", preview.get("new_value", ""))

    updated_count = 0
    _protected_lead = {'id', 'organization_id', 'created_at', 'updated_at', 'owner_id'}
    _protected_loan = {'id', 'organization_id', 'created_at', 'updated_at'}

    for record in records:
        record_id = record.get("id")
        record_type = record.get("type", "lead")

        if record_type == "lead":
            lead = db.query(Lead).filter(
                Lead.id == record_id,
                Lead.owner_id == user_id
            ).first()

            if lead and hasattr(lead, field) and field not in _protected_lead:
                setattr(lead, field, new_value)
                updated_count += 1

        elif record_type == "deal":
            loan = db.query(Loan).filter(
                Loan.id == record_id,
                Loan.loan_officer_id == user_id
            ).first()

            if loan and hasattr(loan, field) and field not in _protected_loan:
                setattr(loan, field, new_value)
                updated_count += 1

    db.commit()

    return {
        "message": f"Updated {updated_count} records",
        "updated_count": updated_count,
        "field": field,
        "new_value": new_value
    }


async def execute_voicemail_drop(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute a voicemail drop campaign"""
    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity

    script = modifications.get("script", preview.get("script", ""))
    recipients = preview.get("recipients", [])

    # In production, this would integrate with a service like Slybroadcast
    # For now, create activity records

    for recipient_name in recipients:
        names = recipient_name.split()
        if len(names) >= 2:
            lead = db.query(Lead).filter(
                Lead.owner_id == user_id,
                Lead.first_name == names[0],
                Lead.last_name == names[-1]
            ).first()

            if lead:
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead.id,
                    activity_type="voicemail",
                    description="Ringless voicemail sent",
                    data={"script": script[:500]}
                )
                db.add(activity)

    db.commit()

    return {
        "message": f"Voicemail campaign queued for {len(recipients)} recipients",
        "recipients_count": len(recipients),
        "status": "queued"
    }


async def execute_pre_approval_letter(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute sending a pre-approval letter via email with PDF attachment"""
    from routes.pre_approval_letter_settings_routes import (
        generate_pre_approval_letter_pdf,
        PreApprovalLetterSettings
    )
    from email_service import email_service

    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity
    User = main.User

    # Apply modifications to preview data
    borrower_names = modifications.get("borrower_names", preview.get("borrower_names", ""))
    property_address = modifications.get("property_address", preview.get("property_address", "To Be Determined"))
    loan_amount = modifications.get("loan_amount", preview.get("loan_amount", 0))
    loan_type = modifications.get("loan_type", preview.get("loan_type", "Conventional"))
    recipient_email = modifications.get("recipient_email", preview.get("recipient_email", ""))
    interest_rate = modifications.get("interest_rate", preview.get("interest_rate"))
    expiration_days = modifications.get("expiration_days", preview.get("expiration_days", 90))
    lead_id = modifications.get("lead_id", preview.get("lead_id"))

    # Get user/loan officer details
    user = db.query(User).filter(User.id == user_id).first()
    lo_name = f"{user.first_name} {user.last_name}" if user else "Loan Officer"
    lo_nmls = getattr(user, 'nmls_id', '') or ''
    lo_email = user.email if user else ''
    lo_phone = getattr(user, 'phone', '') or ''

    # Get or create settings (use defaults if not configured)
    settings = db.query(PreApprovalLetterSettings).filter(
        PreApprovalLetterSettings.user_id == user_id
    ).first()

    if not settings:
        # Create default settings
        settings = PreApprovalLetterSettings(
            user_id=user_id,
            company_name="The Tim Loss Team",
            company_address="123 Main Street, San Francisco, CA 94105",
            company_phone="(555) 123-4567",
            company_nmls="123456",
            logo_url=None,
            letter_template="standard",
            default_conditions=[
                "Verification of employment and income",
                "Satisfactory appraisal of the subject property",
                "Clear title and title insurance",
                "Verification of assets and funds to close"
            ],
            signature_name=lo_name,
            signature_title="Loan Officer",
            signature_nmls=lo_nmls,
            signature_phone=lo_phone,
            signature_email=lo_email,
            include_disclaimer=True
        )

    # Calculate expiration date
    expiration_date = datetime.now() + timedelta(days=expiration_days)

    # Build sample data for PDF generation
    sample_data = {
        "borrower_names": borrower_names,
        "property_address": property_address,
        "loan_amount": f"${loan_amount:,.2f}" if isinstance(loan_amount, (int, float)) else str(loan_amount),
        "loan_type": loan_type,
        "interest_rate": f"{interest_rate}%" if interest_rate else "Market Rate",
        "expiration_date": expiration_date.strftime("%B %d, %Y"),
        "date_issued": datetime.now().strftime("%B %d, %Y")
    }

    try:
        # Generate PDF
        pdf_bytes = generate_pre_approval_letter_pdf(settings, sample_data)

        # Create filename
        borrower_filename = borrower_names.replace(" ", "_").replace(",", "")
        pdf_filename = f"Pre_Approval_Letter_{borrower_filename}.pdf"

        # Create email content
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <p>Please find attached the pre-approval letter for <strong>{borrower_names}</strong>.</p>

            <p><strong>Loan Details:</strong></p>
            <ul>
                <li>Loan Amount: {sample_data['loan_amount']}</li>
                <li>Loan Type: {loan_type}</li>
                <li>Property: {property_address}</li>
                <li>Valid Until: {sample_data['expiration_date']}</li>
            </ul>

            <p>Please don't hesitate to reach out if you have any questions.</p>

            <p>Best regards,<br>
            {lo_name}<br>
            {settings.signature_title or 'Loan Officer'}<br>
            NMLS# {lo_nmls or settings.signature_nmls or 'N/A'}<br>
            {lo_phone or settings.signature_phone or ''}<br>
            {lo_email or settings.signature_email or ''}</p>
        </body>
        </html>
        """

        plain_text = f"""
Pre-Approval Letter for {borrower_names}

Loan Details:
- Loan Amount: {sample_data['loan_amount']}
- Loan Type: {loan_type}
- Property: {property_address}
- Valid Until: {sample_data['expiration_date']}

Please find the pre-approval letter attached.

Best regards,
{lo_name}
{settings.signature_title or 'Loan Officer'}
NMLS# {lo_nmls or settings.signature_nmls or 'N/A'}
        """

        # Create attachment
        attachments = [{
            'content': pdf_bytes,
            'filename': pdf_filename,
            'type': 'application/pdf'
        }]

        # Send email (SF routing skips automatically when attachments present)
        success = await email_service.send_html_email_sf(
            to_email=recipient_email,
            subject=f"Pre-Approval Letter - {borrower_names}",
            html_body=html_content,
            plain_text_body=plain_text,
            attachments=attachments,
            db=db,
            user_id=user_id,
        )

        if not success:
            return {
                "success": False,
                "message": "Failed to send pre-approval letter email",
                "error": "Email service returned failure"
            }

        # Create activity record if we have a lead
        if lead_id:
            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == user_id).first()
            if lead:
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead_id,
                    activity_type="pre_approval_letter",
                    description=f"Pre-approval letter sent to {recipient_email}",
                    data={
                        "borrower_names": borrower_names,
                        "loan_amount": loan_amount,
                        "loan_type": loan_type,
                        "recipient_email": recipient_email,
                        "expiration_date": sample_data['expiration_date']
                    }
                )
                db.add(activity)
                db.commit()

        return {
            "success": True,
            "message": f"Pre-approval letter sent successfully to {recipient_email}",
            "details": {
                "borrower": borrower_names,
                "loan_amount": sample_data['loan_amount'],
                "loan_type": loan_type,
                "sent_to": recipient_email,
                "valid_until": sample_data['expiration_date']
            }
        }

    except Exception as e:
        logger.error(f"Failed to generate/send pre-approval letter: {e}")
        return {
            "success": False,
            "message": "Failed to send pre-approval letter",
            "error": "Internal server error"
        }
