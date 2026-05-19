"""
Outbound (CRM → Salesforce) push handlers.

Provides `OutboundSyncMixin` consumed by `SalesforceSyncService`.
These methods push CRM records (loans, leads, emails, calendar events) to
Salesforce. NOTE: outbound sync is currently disabled in production (the
canonical data flow is Salesforce → CRM only), but the code path is retained
for explicit invocations.

Self-attribute contract (provided by SalesforceSyncService):
  - self._map_crm_stage_to_salesforce(stage) -> str
  - self._map_crm_lead_stage_to_salesforce(stage) -> str
  - self._find_salesforce_record_by_email (defined here)
  - self.push_loan_to_salesforce / push_lead_to_salesforce /
    push_email_to_salesforce / push_calendar_event_to_salesforce
    (defined here, referenced by sync_outbound)
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from salesforce_integration_models import IntegrationProfile
from .oauth_service import salesforce_oauth
from .http_client import get_sf_client
from ._queries import SF_API_VERSION, _sanitize_soql_email

import logging

logger = logging.getLogger(__name__)


class OutboundSyncMixin:
    """Outbound (CRM → Salesforce) push methods for SalesforceSyncService."""

    async def push_loan_to_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        loan_id: int
    ) -> Dict[str, Any]:
        """
        Push a CRM loan to Salesforce as an Opportunity.

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            loan_id: CRM loan ID to push

        Returns:
            Result dict with salesforce_id and success status
        """
        from sqlalchemy import text

        # Get access token
        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, integration_profile_id
        )

        # Get loan data
        loan = db.execute(text("""
            SELECT l.*, u.email as lo_email, COALESCE(es.full_name, u.email) as lo_name
            FROM loans l
            LEFT JOIN users u ON u.id = l.loan_officer_id
            LEFT JOIN email_signatures es ON es.user_id = u.id
            WHERE l.id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        # Map CRM loan fields to Salesforce Opportunity fields
        opportunity_data = {
            "Name": loan.borrower_name or f"Loan {loan.loan_number}",
            "Amount": float(loan.amount or 0),
            "StageName": self._map_crm_stage_to_salesforce(loan.stage),
            "CloseDate": str(loan.closing_date or loan.expected_close_date or datetime.now(timezone.utc).date()),
            "Description": f"Loan #{loan.loan_number}\nProperty: {loan.property_address or 'N/A'}",
        }

        # Add custom fields if they exist in Salesforce
        custom_fields = {
            "Loan_Number__c": loan.loan_number,
            "Property_Address__c": loan.property_address,
            "Loan_Type__c": loan.loan_type,
            "Loan_Program__c": loan.program,
            "Borrower_Email__c": loan.borrower_email,
            "Borrower_Phone__c": loan.borrower_phone,
            "Interest_Rate__c": float(loan.interest_rate) if loan.interest_rate else None,
            "LTV__c": float(loan.ltv) if hasattr(loan, 'ltv') and loan.ltv else None,
        }

        # Only include custom fields that have values
        for field, value in custom_fields.items():
            if value is not None:
                opportunity_data[field] = value

        # Check if loan already has a Salesforce ID (update) or needs to be created
        salesforce_id = loan.salesforce_id

        async with get_sf_client() as client:
            if salesforce_id:
                # UPDATE existing Opportunity
                response = await client.patch(
                    f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/Opportunity/{salesforce_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=opportunity_data,
                    timeout=30.0
                )

                if response.status_code == 204:
                    logger.info(f"Updated Salesforce Opportunity {salesforce_id} for loan {loan_id}")

                    # Update loan's sync timestamp
                    db.execute(text("""
                        UPDATE loans SET updated_at = CURRENT_TIMESTAMP
                        WHERE id = :loan_id
                    """), {"loan_id": loan_id})
                    db.commit()

                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "updated",
                        "loan_id": loan_id
                    }
                else:
                    error = response.text
                    logger.error(f"Failed to update Salesforce Opportunity: {error}")
                    return {
                        "success": False,
                        "error": error,
                        "loan_id": loan_id
                    }
            else:
                # CREATE new Opportunity
                response = await client.post(
                    f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/Opportunity",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=opportunity_data,
                    timeout=30.0
                )

                if response.status_code == 201:
                    result = response.json()
                    salesforce_id = result.get('id')

                    logger.info(f"Created Salesforce Opportunity {salesforce_id} for loan {loan_id}")

                    # Update loan with Salesforce ID
                    db.execute(text("""
                        UPDATE loans SET
                            salesforce_id = :sf_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :loan_id
                    """), {"sf_id": salesforce_id, "loan_id": loan_id})
                    db.commit()

                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "created",
                        "loan_id": loan_id
                    }
                else:
                    error = response.text
                    logger.error(f"Failed to create Salesforce Opportunity: {error}")
                    return {
                        "success": False,
                        "error": error,
                        "loan_id": loan_id
                    }

    async def _find_salesforce_record_by_email(
        self,
        access_token: str,
        instance_url: str,
        email: str
    ) -> Dict[str, Any]:
        """
        Search Salesforce for an existing Lead or Contact by email.

        Args:
            access_token: Salesforce OAuth token
            instance_url: Salesforce instance URL
            email: Email address to search for

        Returns:
            Dict with 'found', 'type' (Lead/Contact), and 'id' if found
        """
        if not email:
            return {"found": False}

        async with get_sf_client() as client:
            # First, search for Lead by email
            lead_query = f"SELECT Id, FirstName, LastName, Email, Phone FROM Lead WHERE Email = '{_sanitize_soql_email(email)}' LIMIT 1"
            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": lead_query},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('totalSize', 0) > 0:
                    record = data['records'][0]
                    logger.info(f"Found existing Salesforce Lead {record['Id']} for CRM record lookup")
                    return {
                        "found": True,
                        "type": "Lead",
                        "id": record['Id'],
                        "record": record
                    }

            # If no Lead found, search for Contact
            contact_query = f"SELECT Id, FirstName, LastName, Email, Phone, AccountId FROM Contact WHERE Email = '{_sanitize_soql_email(email)}' LIMIT 1"
            response = await client.get(
                f"{instance_url}/services/data/{SF_API_VERSION}/query",
                params={"q": contact_query},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('totalSize', 0) > 0:
                    record = data['records'][0]
                    logger.info(f"Found existing Salesforce Contact {record['Id']} for CRM record lookup")
                    return {
                        "found": True,
                        "type": "Contact",
                        "id": record['Id'],
                        "record": record
                    }

        return {"found": False}

    async def push_lead_to_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        lead_id: int
    ) -> Dict[str, Any]:
        """
        Push a CRM lead to Salesforce as a Lead.

        Features:
        - Matches existing Salesforce Lead/Contact by email before creating new
        - Pushes comprehensive field mapping (all available CRM fields)

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            lead_id: CRM lead ID to push

        Returns:
            Result dict with salesforce_id and success status
        """
        from sqlalchemy import text

        # Get access token
        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, integration_profile_id
        )

        # Get lead data with all fields
        lead = db.execute(text("""
            SELECT * FROM leads WHERE id = :lead_id
        """), {"lead_id": lead_id}).fetchone()

        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Check if lead already has a Salesforce ID
        salesforce_id = lead.salesforce_id if hasattr(lead, 'salesforce_id') and lead.salesforce_id else None
        sf_object_type = "Lead"  # Default to Lead

        # If no salesforce_id, try to find existing record by email
        if not salesforce_id and lead.email:
            match_result = await self._find_salesforce_record_by_email(
                access_token, instance_url, lead.email
            )
            if match_result.get('found'):
                salesforce_id = match_result['id']
                sf_object_type = match_result['type']
                logger.info(f"Matched CRM lead {lead_id} to existing Salesforce {sf_object_type} {salesforce_id} by email")

                # Save the matched salesforce_id
                db.execute(text("""
                    UPDATE leads SET
                        salesforce_id = :sf_id,
                        meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                            jsonb_build_object('salesforce_type', :sf_type)
                    WHERE id = :lead_id
                """), {"sf_id": salesforce_id, "sf_type": sf_object_type, "lead_id": lead_id})
                db.commit()

        # Build comprehensive field mapping for Salesforce Lead
        # Standard Salesforce Lead fields
        lead_data = {}

        # Basic contact info
        if lead.first_name:
            lead_data["FirstName"] = lead.first_name
        if lead.last_name:
            lead_data["LastName"] = lead.last_name or "Unknown"
        else:
            # Parse name if only full name available
            if lead.name:
                name_parts = lead.name.split(' ', 1)
                lead_data["FirstName"] = name_parts[0] if len(name_parts) > 0 else ""
                lead_data["LastName"] = name_parts[1] if len(name_parts) > 1 else name_parts[0]
            else:
                lead_data["LastName"] = "Unknown"

        if lead.email:
            lead_data["Email"] = lead.email
        if lead.phone:
            lead_data["Phone"] = lead.phone

        # Company/employer info
        if hasattr(lead, 'employer_name') and lead.employer_name:
            lead_data["Company"] = lead.employer_name
        elif hasattr(lead, 'company') and lead.company:
            lead_data["Company"] = lead.company
        else:
            lead_data["Company"] = "Individual"

        # Lead source and status
        if lead.source:
            lead_data["LeadSource"] = lead.source
        if lead.stage:
            lead_data["Status"] = self._map_crm_lead_stage_to_salesforce(lead.stage)

        # Address fields
        if hasattr(lead, 'address') and lead.address:
            lead_data["Street"] = lead.address
        if hasattr(lead, 'city') and lead.city:
            lead_data["City"] = lead.city
        if hasattr(lead, 'state') and lead.state:
            lead_data["State"] = lead.state
        if hasattr(lead, 'zip_code') and lead.zip_code:
            lead_data["PostalCode"] = lead.zip_code

        # Industry
        if hasattr(lead, 'industry') and lead.industry:
            lead_data["Industry"] = lead.industry

        # Description with comprehensive loan details
        description_parts = [f"CRM Lead ID: {lead.id}"]

        # Add loan details to description
        if hasattr(lead, 'loan_amount') and lead.loan_amount:
            description_parts.append(f"Loan Amount: ${lead.loan_amount:,.2f}")
        if hasattr(lead, 'loan_type') and lead.loan_type:
            description_parts.append(f"Loan Type: {lead.loan_type}")
        if hasattr(lead, 'loan_purpose') and lead.loan_purpose:
            description_parts.append(f"Purpose: {lead.loan_purpose}")
        if hasattr(lead, 'property_type') and lead.property_type:
            description_parts.append(f"Property Type: {lead.property_type}")
        if hasattr(lead, 'property_value') and lead.property_value:
            description_parts.append(f"Property Value: ${lead.property_value:,.2f}")
        if hasattr(lead, 'credit_score') and lead.credit_score:
            description_parts.append(f"Credit Score: {lead.credit_score}")
        if hasattr(lead, 'dti') and lead.dti:
            description_parts.append(f"DTI: {lead.dti:.1f}%")
        if hasattr(lead, 'ltv') and lead.ltv:
            description_parts.append(f"LTV: {lead.ltv:.1f}%")
        if hasattr(lead, 'annual_income') and lead.annual_income:
            description_parts.append(f"Annual Income: ${lead.annual_income:,.2f}")
        if hasattr(lead, 'interest_rate') and lead.interest_rate:
            description_parts.append(f"Rate: {lead.interest_rate:.3f}%")

        lead_data["Description"] = "\n".join(description_parts)

        # Custom fields (if they exist in Salesforce org)
        # These may fail if custom fields don't exist - that's OK
        custom_fields = {}

        # CRM tracking
        custom_fields["CRM_Lead_ID__c"] = str(lead.id)

        # Financial fields
        if hasattr(lead, 'loan_amount') and lead.loan_amount:
            custom_fields["Loan_Amount__c"] = float(lead.loan_amount)
        if hasattr(lead, 'property_value') and lead.property_value:
            custom_fields["Property_Value__c"] = float(lead.property_value)
        if hasattr(lead, 'down_payment') and lead.down_payment:
            custom_fields["Down_Payment__c"] = float(lead.down_payment)
        if hasattr(lead, 'credit_score') and lead.credit_score:
            custom_fields["Credit_Score__c"] = int(lead.credit_score)
        if hasattr(lead, 'annual_income') and lead.annual_income:
            custom_fields["Annual_Income__c"] = float(lead.annual_income)
        if hasattr(lead, 'dti') and lead.dti:
            custom_fields["DTI__c"] = float(lead.dti)
        if hasattr(lead, 'ltv') and lead.ltv:
            custom_fields["LTV__c"] = float(lead.ltv)
        if hasattr(lead, 'interest_rate') and lead.interest_rate:
            custom_fields["Interest_Rate__c"] = float(lead.interest_rate)
        if hasattr(lead, 'monthly_payment') and lead.monthly_payment:
            custom_fields["Monthly_Payment__c"] = float(lead.monthly_payment)

        # Loan details
        if hasattr(lead, 'loan_type') and lead.loan_type:
            custom_fields["Loan_Type__c"] = lead.loan_type
        if hasattr(lead, 'loan_purpose') and lead.loan_purpose:
            custom_fields["Loan_Purpose__c"] = lead.loan_purpose
        if hasattr(lead, 'loan_term') and lead.loan_term:
            custom_fields["Loan_Term__c"] = int(lead.loan_term)
        if hasattr(lead, 'program') and lead.program:
            custom_fields["Loan_Program__c"] = lead.program
        if hasattr(lead, 'rate_type') and lead.rate_type:
            custom_fields["Rate_Type__c"] = lead.rate_type

        # Property details
        if hasattr(lead, 'property_type') and lead.property_type:
            custom_fields["Property_Type__c"] = lead.property_type
        if hasattr(lead, 'occupancy_type') and lead.occupancy_type:
            custom_fields["Occupancy_Type__c"] = lead.occupancy_type
        if hasattr(lead, 'property_address') and lead.property_address:
            custom_fields["Property_Address__c"] = lead.property_address

        # Preapproval info
        if hasattr(lead, 'preapproval_amount') and lead.preapproval_amount:
            custom_fields["Preapproval_Amount__c"] = float(lead.preapproval_amount)

        # Co-applicant info
        if hasattr(lead, 'co_applicant_name') and lead.co_applicant_name:
            custom_fields["Co_Applicant_Name__c"] = lead.co_applicant_name
        if hasattr(lead, 'co_applicant_email') and lead.co_applicant_email:
            custom_fields["Co_Applicant_Email__c"] = lead.co_applicant_email
        if hasattr(lead, 'co_applicant_phone') and lead.co_applicant_phone:
            custom_fields["Co_Applicant_Phone__c"] = lead.co_applicant_phone

        async with get_sf_client() as client:
            if salesforce_id:
                # UPDATE existing Lead or Contact
                # First try to update with all fields including custom
                all_fields = {**lead_data, **custom_fields}

                response = await client.patch(
                    f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/{sf_object_type}/{salesforce_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=all_fields,
                    timeout=30.0
                )

                if response.status_code == 204:
                    logger.info(f"Updated Salesforce {sf_object_type} {salesforce_id} for CRM lead {lead_id} with all fields")
                    action = "updated"
                elif response.status_code == 400 and "INVALID_FIELD" in response.text:
                    # Custom fields don't exist - retry with standard fields only
                    logger.warning(f"Custom fields failed, retrying with standard fields only")
                    response = await client.patch(
                        f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/{sf_object_type}/{salesforce_id}",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json=lead_data,
                        timeout=30.0
                    )
                    if response.status_code == 204:
                        logger.info(f"Updated Salesforce {sf_object_type} {salesforce_id} with standard fields only")
                        action = "updated_standard_only"
                    else:
                        error = response.text
                        logger.error(f"Failed to update Salesforce {sf_object_type}: {error}")
                        return {"success": False, "error": error, "lead_id": lead_id}
                else:
                    error = response.text
                    logger.error(f"Failed to update Salesforce {sf_object_type}: {error}")
                    return {"success": False, "error": error, "lead_id": lead_id}

                # Update sync timestamp
                db.execute(text("""
                    UPDATE leads SET
                        updated_at = CURRENT_TIMESTAMP,
                        meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                            jsonb_build_object('salesforce_synced_at', :synced_at, 'salesforce_type', :sf_type)
                    WHERE id = :lead_id
                """), {"lead_id": lead_id, "synced_at": datetime.now(timezone.utc).isoformat(), "sf_type": sf_object_type})
                db.commit()

                return {
                    "success": True,
                    "salesforce_id": salesforce_id,
                    "salesforce_type": sf_object_type,
                    "action": action,
                    "lead_id": lead_id,
                    "fields_pushed": list(lead_data.keys()) + list(custom_fields.keys())
                }
            else:
                # CREATE new Lead - try with all fields first
                all_fields = {**lead_data, **custom_fields}

                response = await client.post(
                    f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/Lead",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=all_fields,
                    timeout=30.0
                )

                if response.status_code == 201:
                    result = response.json()
                    salesforce_id = result.get('id')
                    logger.info(f"Created Salesforce Lead {salesforce_id} for CRM lead {lead_id} with all fields")
                elif response.status_code == 400 and "INVALID_FIELD" in response.text:
                    # Custom fields don't exist - retry with standard fields only
                    logger.warning(f"Custom fields failed on create, retrying with standard fields")
                    response = await client.post(
                        f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/Lead",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json=lead_data,
                        timeout=30.0
                    )
                    if response.status_code == 201:
                        result = response.json()
                        salesforce_id = result.get('id')
                        logger.info(f"Created Salesforce Lead {salesforce_id} with standard fields only")
                    else:
                        error = response.text
                        logger.error(f"Failed to create Salesforce Lead: {error}")
                        return {"success": False, "error": error, "lead_id": lead_id}
                else:
                    error = response.text
                    logger.error(f"Failed to create Salesforce Lead: {error}")
                    return {"success": False, "error": error, "lead_id": lead_id}

                # Save salesforce_id
                db.execute(text("""
                    UPDATE leads SET
                        salesforce_id = :sf_id,
                        updated_at = CURRENT_TIMESTAMP,
                        meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                            jsonb_build_object('salesforce_synced_at', :synced_at, 'salesforce_type', 'Lead')
                    WHERE id = :lead_id
                """), {"sf_id": salesforce_id, "lead_id": lead_id, "synced_at": datetime.now(timezone.utc).isoformat()})
                db.commit()

                return {
                    "success": True,
                    "salesforce_id": salesforce_id,
                    "salesforce_type": "Lead",
                    "action": "created",
                    "lead_id": lead_id,
                    "fields_pushed": list(lead_data.keys()) + list(custom_fields.keys())
                }

    async def push_email_to_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        email_id: int
    ) -> Dict[str, Any]:
        """
        Push a CRM email to Salesforce as a Task (Email type).

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            email_id: CRM email ID to push

        Returns:
            Result dict with salesforce_id and success status
        """
        from sqlalchemy import text

        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, integration_profile_id
        )

        # Get email data with related lead/loan Salesforce IDs
        email = db.execute(text("""
            SELECT em.*,
                   l.salesforce_id as lead_sf_id,
                   lo.salesforce_id as loan_sf_id
            FROM email_messages em
            LEFT JOIN leads l ON l.id = em.lead_id
            LEFT JOIN loans lo ON lo.id = em.loan_id
            WHERE em.id = :email_id
        """), {"email_id": email_id}).fetchone()

        if not email:
            raise ValueError(f"Email {email_id} not found")

        # Build Task data
        task_data = {
            "Subject": email.subject or "Email Activity",
            "Description": (email.body or "")[:32000],
            "TaskSubtype": "Email",
            "Status": "Completed",
            "Priority": "Normal",
            "ActivityDate": email.created_at.strftime("%Y-%m-%d") if email.created_at else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }

        # Link to Lead or Opportunity
        if email.lead_sf_id:
            task_data["WhoId"] = email.lead_sf_id
        if email.loan_sf_id:
            task_data["WhatId"] = email.loan_sf_id

        async with get_sf_client() as client:
            response = await client.post(
                f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/Task",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=task_data,
                timeout=30.0
            )

            if response.status_code == 201:
                result = response.json()
                salesforce_id = result.get('id')

                logger.info(f"Created Salesforce Task {salesforce_id} for email {email_id}")

                # Update email with Salesforce Task ID
                db.execute(text("""
                    UPDATE email_messages SET
                        meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                            jsonb_build_object(
                                'salesforce_task_id', :sf_id,
                                'salesforce_pushed_at', :pushed_at
                            )
                    WHERE id = :email_id
                """), {
                    "sf_id": salesforce_id,
                    "pushed_at": datetime.now(timezone.utc).isoformat(),
                    "email_id": email_id
                })
                db.commit()

                return {
                    "success": True,
                    "salesforce_id": salesforce_id,
                    "action": "created",
                    "email_id": email_id
                }
            else:
                error = response.text
                logger.error(f"Failed to create Salesforce Task: {error}")
                return {"success": False, "error": error, "email_id": email_id}

    async def push_calendar_event_to_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        event_id: int
    ) -> Dict[str, Any]:
        """
        Push a CRM calendar event to Salesforce as an Event.

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            event_id: CRM calendar event ID to push

        Returns:
            Result dict with salesforce_id and success status
        """
        from sqlalchemy import text

        access_token, instance_url = await salesforce_oauth.get_access_token(
            db, integration_profile_id
        )

        # Get event data
        event = db.execute(text("""
            SELECT ce.*,
                   l.salesforce_id as lead_sf_id,
                   lo.salesforce_id as loan_sf_id
            FROM calendar_events ce
            LEFT JOIN leads l ON l.id = ce.lead_id
            LEFT JOIN loans lo ON lo.id = ce.loan_id
            WHERE ce.id = :event_id
        """), {"event_id": event_id}).fetchone()

        if not event:
            raise ValueError(f"Calendar event {event_id} not found")

        # Build Salesforce Event data
        event_data = {
            "Subject": event.title or "CRM Event",
            "Description": event.description or "",
            "StartDateTime": event.start_time.isoformat() if event.start_time else datetime.now(timezone.utc).isoformat(),
            "EndDateTime": event.end_time.isoformat() if event.end_time else (event.start_time + timedelta(hours=1)).isoformat() if event.start_time else datetime.now(timezone.utc).isoformat(),
            "Location": event.location if hasattr(event, 'location') and event.location else None,
            "IsAllDayEvent": event.all_day if hasattr(event, 'all_day') else False,
        }

        # Remove None values
        event_data = {k: v for k, v in event_data.items() if v is not None}

        # Link to Lead or Opportunity
        if hasattr(event, 'lead_sf_id') and event.lead_sf_id:
            event_data["WhoId"] = event.lead_sf_id
        if hasattr(event, 'loan_sf_id') and event.loan_sf_id:
            event_data["WhatId"] = event.loan_sf_id

        # Check for existing Salesforce ID
        salesforce_id = None
        if hasattr(event, 'meta_data') and event.meta_data:
            salesforce_id = event.meta_data.get('salesforce_event_id')

        async with get_sf_client() as client:
            if salesforce_id:
                # UPDATE existing Event
                response = await client.patch(
                    f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/Event/{salesforce_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=event_data,
                    timeout=30.0
                )

                if response.status_code == 204:
                    logger.info(f"Updated Salesforce Event {salesforce_id}")
                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "updated",
                        "event_id": event_id
                    }
                else:
                    error = response.text
                    return {"success": False, "error": error, "event_id": event_id}
            else:
                # CREATE new Event
                response = await client.post(
                    f"{instance_url}/services/data/{SF_API_VERSION}/sobjects/Event",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=event_data,
                    timeout=30.0
                )

                if response.status_code == 201:
                    result = response.json()
                    salesforce_id = result.get('id')

                    logger.info(f"Created Salesforce Event {salesforce_id}")

                    # Update CRM event with Salesforce ID
                    db.execute(text("""
                        UPDATE calendar_events SET
                            meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                                jsonb_build_object(
                                    'salesforce_event_id', :sf_id,
                                    'salesforce_pushed_at', :pushed_at
                                )
                        WHERE id = :event_id
                    """), {
                        "sf_id": salesforce_id,
                        "pushed_at": datetime.now(timezone.utc).isoformat(),
                        "event_id": event_id
                    })
                    db.commit()

                    return {
                        "success": True,
                        "salesforce_id": salesforce_id,
                        "action": "created",
                        "event_id": event_id
                    }
                else:
                    error = response.text
                    return {"success": False, "error": error, "event_id": event_id}

    async def sync_outbound(
        self,
        db: Session,
        integration_profile_id: int,
        sync_loans: bool = True,
        sync_leads: bool = True,
        sync_emails: bool = True,
        sync_calendar: bool = True,
        since_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Push all recent CRM changes to Salesforce.

        Args:
            db: Database session
            integration_profile_id: User's Salesforce integration profile
            sync_loans: Push loan changes
            sync_leads: Push lead changes
            sync_emails: Push email activities
            sync_calendar: Push calendar events
            since_hours: Only sync records modified in the last N hours

        Returns:
            Summary of sync results
        """
        from sqlalchemy import text

        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.id == integration_profile_id
        ).first()

        if not profile:
            raise ValueError("Integration profile not found")

        user_id = profile.user_id
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        results = {
            "success": True,
            "loans": {"pushed": 0, "failed": 0, "errors": []},
            "leads": {"pushed": 0, "failed": 0, "errors": []},
            "emails": {"pushed": 0, "failed": 0, "errors": []},
            "calendar": {"pushed": 0, "failed": 0, "errors": []},
        }

        # Sync Loans
        if sync_loans:
            loans = db.execute(text("""
                SELECT id FROM loans
                WHERE loan_officer_id = :user_id
                  AND updated_at >= :since
                ORDER BY updated_at DESC
                LIMIT 100
            """), {"user_id": user_id, "since": since}).fetchall()

            for loan in loans:
                try:
                    result = await self.push_loan_to_salesforce(db, integration_profile_id, loan.id)
                    if result['success']:
                        results['loans']['pushed'] += 1
                    else:
                        results['loans']['failed'] += 1
                        results['loans']['errors'].append(result.get('error', 'Unknown error')[:100])
                except Exception as e:
                    results['loans']['failed'] += 1
                    results['loans']['errors'].append(str(e)[:100])
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after outbound loan push error: {e2}")

        # Sync Leads
        if sync_leads:
            leads = db.execute(text("""
                SELECT id FROM leads
                WHERE owner_id = :user_id
                  AND updated_at >= :since
                  AND (salesforce_id IS NULL
                       OR (meta_data->>'salesforce_synced_at')::timestamp < updated_at)
                ORDER BY updated_at DESC
                LIMIT 100
            """), {"user_id": user_id, "since": since}).fetchall()

            for lead in leads:
                try:
                    result = await self.push_lead_to_salesforce(db, integration_profile_id, lead.id)
                    if result['success']:
                        results['leads']['pushed'] += 1
                    else:
                        results['leads']['failed'] += 1
                        results['leads']['errors'].append(result.get('error', 'Unknown error')[:100])
                except Exception as e:
                    results['leads']['failed'] += 1
                    results['leads']['errors'].append(str(e)[:100])
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after outbound lead push error: {e2}")

        # Sync Emails
        if sync_emails:
            emails = db.execute(text("""
                SELECT id FROM email_messages
                WHERE user_id = :user_id
                  AND created_at >= :since
                  AND direction = 'outbound'
                  AND (meta_data IS NULL OR meta_data->>'salesforce_task_id' IS NULL)
                ORDER BY created_at DESC
                LIMIT 100
            """), {"user_id": user_id, "since": since}).fetchall()

            for email in emails:
                try:
                    result = await self.push_email_to_salesforce(db, integration_profile_id, email.id)
                    if result['success']:
                        results['emails']['pushed'] += 1
                    else:
                        results['emails']['failed'] += 1
                        results['emails']['errors'].append(result.get('error', 'Unknown error')[:100])
                except Exception as e:
                    results['emails']['failed'] += 1
                    results['emails']['errors'].append(str(e)[:100])
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after outbound email push error: {e2}")

        # Sync Calendar Events
        if sync_calendar:
            events = db.execute(text("""
                SELECT id FROM calendar_events
                WHERE user_id = :user_id
                  AND updated_at >= :since
                  AND (meta_data IS NULL OR meta_data->>'salesforce_event_id' IS NULL)
                ORDER BY updated_at DESC
                LIMIT 100
            """), {"user_id": user_id, "since": since}).fetchall()

            for event in events:
                try:
                    result = await self.push_calendar_event_to_salesforce(db, integration_profile_id, event.id)
                    if result['success']:
                        results['calendar']['pushed'] += 1
                    else:
                        results['calendar']['failed'] += 1
                        results['calendar']['errors'].append(result.get('error', 'Unknown error')[:100])
                except Exception as e:
                    results['calendar']['failed'] += 1
                    results['calendar']['errors'].append(str(e)[:100])
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.exception(f"Failed to rollback after outbound calendar push error: {e2}")

        # Check overall success
        total_failed = sum([
            results['loans']['failed'],
            results['leads']['failed'],
            results['emails']['failed'],
            results['calendar']['failed']
        ])
        results['success'] = total_failed == 0

        logger.info(
            f"Outbound sync complete: "
            f"loans={results['loans']['pushed']}, "
            f"leads={results['leads']['pushed']}, "
            f"emails={results['emails']['pushed']}, "
            f"calendar={results['calendar']['pushed']}"
        )

        return results
