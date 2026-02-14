"""
Salesforce Email Sync Service
Syncs EmailMessage and Email Activity records from Salesforce to CRM client profiles
"""
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import httpx

from sqlalchemy.orm import Session
from sqlalchemy import text

from salesforce_integration_models import (
    IntegrationProfile,
    IntegrationEvent
)
from .oauth_service import salesforce_oauth
from .http_client import get_sf_client, SF_TIMEOUT

logger = logging.getLogger(__name__)


class SalesforceEmailSyncService:
    """Syncs email history from Salesforce to CRM client profiles"""

    async def sync_emails(
        self,
        db: Session,
        integration_profile_id: int,
        days_back: int = 90,
        limit: int = 500
    ) -> Dict[str, Any]:
        """
        Sync emails from Salesforce to CRM.

        Pulls EmailMessage records and Task records (Type='Email') from Salesforce
        and creates corresponding EmailMessage records in the CRM.
        """
        result = {
            'success': False,
            'emails_synced': 0,
            'emails_skipped': 0,
            'errors': []
        }

        try:
            # Get access token
            access_token, instance_url = await salesforce_oauth.get_access_token(
                db, integration_profile_id
            )

            if not access_token:
                result['errors'].append("Failed to get Salesforce access token")
                return result

            # Get the integration profile for user_id
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.id == integration_profile_id
            ).first()

            if not profile:
                result['errors'].append("Integration profile not found")
                return result

            user_id = profile.user_id

            # Calculate date filter
            since_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%SZ')

            # Query EmailMessage objects from Salesforce
            email_messages = await self._query_email_messages(
                access_token, instance_url, since_date, limit
            )

            # Query Task records with Type='Email'
            email_tasks = await self._query_email_tasks(
                access_token, instance_url, since_date, limit
            )

            # Process EmailMessage records
            for sf_email in email_messages:
                try:
                    synced = await self._process_email_message(db, user_id, sf_email, instance_url)
                    if synced:
                        result['emails_synced'] += 1
                    else:
                        result['emails_skipped'] += 1
                except Exception as e:
                    logger.error(f"Error processing EmailMessage {sf_email.get('Id')}: {e}")
                    result['errors'].append(f"EmailMessage {sf_email.get('Id')}: {str(e)[:100]}")
                    # Rollback to recover from any transaction errors (e.g., constraint violations)
                    try:
                        db.rollback()
                    except Exception:
                        pass

            # Process Email Tasks
            for sf_task in email_tasks:
                try:
                    synced = await self._process_email_task(db, user_id, sf_task, instance_url)
                    if synced:
                        result['emails_synced'] += 1
                    else:
                        result['emails_skipped'] += 1
                except Exception as e:
                    logger.error(f"Error processing Email Task {sf_task.get('Id')}: {e}")
                    result['errors'].append(f"Task {sf_task.get('Id')}: {str(e)[:100]}")
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception:
                        pass

            # Log sync event
            self._log_sync_event(db, integration_profile_id, result)

            result['success'] = True
            db.commit()

        except Exception as e:
            logger.error(f"Email sync failed: {e}")
            result['errors'].append(str(e))
            db.rollback()

        return result

    async def _query_email_messages(
        self,
        access_token: str,
        instance_url: str,
        since_date: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Query EmailMessage objects from Salesforce"""
        soql = f"""
            SELECT Id, ParentId, ActivityId, MessageDate, FromAddress, ToAddress,
                   CcAddress, BccAddress, Subject, TextBody, HtmlBody, HasAttachment,
                   Incoming, Status, RelatedToId
            FROM EmailMessage
            WHERE MessageDate >= {since_date}
            ORDER BY MessageDate DESC
            LIMIT {limit}
        """

        try:
            async with get_sf_client() as client:
                response = await client.get(
                    f"{instance_url}/services/data/v59.0/query",
                    params={"q": soql},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('records', [])
                else:
                    logger.warning(f"EmailMessage query failed: {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            logger.error(f"Error querying EmailMessage: {e}")
            return []

    async def _query_email_tasks(
        self,
        access_token: str,
        instance_url: str,
        since_date: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Query Task records with Type='Email' from Salesforce"""
        soql = f"""
            SELECT Id, WhoId, WhatId, Subject, Description, ActivityDate,
                   Status, Priority, OwnerId, CreatedDate
            FROM Task
            WHERE TaskSubtype = 'Email' AND CreatedDate >= {since_date}
            ORDER BY CreatedDate DESC
            LIMIT {limit}
        """

        try:
            async with get_sf_client() as client:
                response = await client.get(
                    f"{instance_url}/services/data/v59.0/query",
                    params={"q": soql},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('records', [])
                else:
                    logger.warning(f"Email Task query failed: {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            logger.error(f"Error querying Email Tasks: {e}")
            return []

    async def _process_email_message(
        self,
        db: Session,
        user_id: int,
        sf_email: Dict[str, Any],
        instance_url: str
    ) -> bool:
        """Process a Salesforce EmailMessage and create CRM record"""
        sf_id = sf_email.get('Id')

        # Check if already synced
        existing = db.execute(text("""
            SELECT id FROM email_messages
            WHERE meta_data->>'salesforce_id' = :sf_id
        """), {"sf_id": sf_id}).fetchone()

        if existing:
            return False  # Already synced

        # Find matching lead/loan by email address
        from_email = sf_email.get('FromAddress', '')
        to_email = sf_email.get('ToAddress', '')

        # Determine direction
        is_incoming = sf_email.get('Incoming', False)
        direction = 'inbound' if is_incoming else 'outbound'
        client_email = from_email if is_incoming else to_email

        # Find lead by email
        lead_id, loan_id = await self._find_client_by_email(db, client_email, user_id)

        if not lead_id and not loan_id:
            # Try RelatedToId to find loan
            related_to_id = sf_email.get('RelatedToId')
            if related_to_id:
                loan_id = await self._find_loan_by_salesforce_id(db, related_to_id)

        # Create EmailMessage record
        message_date = sf_email.get('MessageDate')
        if message_date:
            try:
                received_at = datetime.fromisoformat(message_date.replace('Z', '+00:00'))
            except Exception:
                received_at = datetime.now(timezone.utc)
        else:
            received_at = datetime.now(timezone.utc)

        db.execute(text("""
            INSERT INTO email_messages (
                user_id, lead_id, loan_id, to_email, from_email, subject,
                body, html_body, direction, status, has_attachments,
                meta_data, created_at, received_at
            ) VALUES (
                :user_id, :lead_id, :loan_id, :to_email, :from_email, :subject,
                :body, :html_body, :direction, :status, :has_attachments,
                CAST(:meta_data AS jsonb), :created_at, :received_at
            )
        """), {
            "user_id": user_id,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "to_email": to_email or '',
            "from_email": from_email or '',
            "subject": sf_email.get('Subject', ''),
            "body": sf_email.get('TextBody', ''),
            "html_body": sf_email.get('HtmlBody', ''),
            "direction": direction,
            "status": 'synced_from_salesforce',
            "has_attachments": sf_email.get('HasAttachment', False),
            "meta_data": json.dumps({
                "salesforce_id": sf_id,
                "salesforce_parent_id": sf_email.get('ParentId'),
                "salesforce_activity_id": sf_email.get('ActivityId'),
                "cc_address": sf_email.get('CcAddress'),
                "bcc_address": sf_email.get('BccAddress'),
                "source": "salesforce_sync"
            }),
            "created_at": datetime.now(timezone.utc),
            "received_at": received_at
        })

        return True

    async def _process_email_task(
        self,
        db: Session,
        user_id: int,
        sf_task: Dict[str, Any],
        instance_url: str
    ) -> bool:
        """Process a Salesforce Email Task and create CRM record"""
        sf_id = sf_task.get('Id')

        # Check if already synced
        existing = db.execute(text("""
            SELECT id FROM email_messages
            WHERE meta_data->>'salesforce_task_id' = :sf_id
        """), {"sf_id": sf_id}).fetchone()

        if existing:
            return False  # Already synced

        # Find lead/loan by WhoId or WhatId
        lead_id = None
        loan_id = None

        who_id = sf_task.get('WhoId')
        what_id = sf_task.get('WhatId')

        if who_id:
            # WhoId is usually a Contact or Lead
            lead_id = await self._find_lead_by_salesforce_id(db, who_id)

        if what_id:
            # WhatId is usually an Opportunity (loan)
            loan_id = await self._find_loan_by_salesforce_id(db, what_id)

        # Create EmailMessage record from Task
        created_date = sf_task.get('CreatedDate')
        if created_date:
            try:
                received_at = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
            except Exception:
                received_at = datetime.now(timezone.utc)
        else:
            received_at = datetime.now(timezone.utc)

        db.execute(text("""
            INSERT INTO email_messages (
                user_id, lead_id, loan_id, to_email, from_email, subject,
                body, direction, status, meta_data, created_at, received_at
            ) VALUES (
                :user_id, :lead_id, :loan_id, :to_email, :from_email, :subject,
                :body, :direction, :status, CAST(:meta_data AS jsonb), :created_at, :received_at
            )
        """), {
            "user_id": user_id,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "to_email": "",  # Task doesn't have email addresses
            "from_email": "",
            "subject": sf_task.get('Subject', 'Email Activity'),
            "body": sf_task.get('Description', ''),
            "direction": "outbound",  # Tasks are usually logged outbound emails
            "status": 'synced_from_salesforce',
            "meta_data": json.dumps({
                "salesforce_task_id": sf_id,
                "salesforce_who_id": who_id,
                "salesforce_what_id": what_id,
                "activity_date": sf_task.get('ActivityDate'),
                "source": "salesforce_task_sync"
            }),
            "created_at": datetime.now(timezone.utc),
            "received_at": received_at
        })

        return True

    async def _find_client_by_email(
        self,
        db: Session,
        email: str,
        user_id: int
    ) -> tuple:
        """Find lead_id and loan_id by email address"""
        if not email:
            return None, None

        email = email.lower().strip()

        # Check leads
        lead = db.execute(text("""
            SELECT id FROM leads
            WHERE LOWER(email) = :email AND owner_id = :user_id
            LIMIT 1
        """), {"email": email, "user_id": user_id}).fetchone()

        lead_id = lead[0] if lead else None

        # Check loans (by borrower email)
        loan = db.execute(text("""
            SELECT id FROM loans
            WHERE LOWER(borrower_email) = :email AND loan_officer_id = :user_id
            LIMIT 1
        """), {"email": email, "user_id": user_id}).fetchone()

        loan_id = loan[0] if loan else None

        return lead_id, loan_id

    async def _find_lead_by_salesforce_id(self, db: Session, sf_id: str) -> Optional[int]:
        """Find CRM lead by Salesforce ID"""
        result = db.execute(text("""
            SELECT id FROM leads
            WHERE salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id
            LIMIT 1
        """), {"sf_id": sf_id}).fetchone()
        return result[0] if result else None

    async def _find_loan_by_salesforce_id(self, db: Session, sf_id: str) -> Optional[int]:
        """Find CRM loan by Salesforce ID"""
        result = db.execute(text("""
            SELECT id FROM loans
            WHERE salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id
            LIMIT 1
        """), {"sf_id": sf_id}).fetchone()
        return result[0] if result else None

    def _log_sync_event(
        self,
        db: Session,
        integration_profile_id: int,
        result: Dict[str, Any]
    ):
        """Log the sync event"""
        try:
            event = IntegrationEvent(
                integration_profile_id=integration_profile_id,
                event_type='email_sync_completed' if result['success'] else 'email_sync_failed',
                status='success' if result['success'] else 'error',
                direction='inbound',
                records_processed=result['emails_synced'] + result['emails_skipped'],
                records_succeeded=result['emails_synced'],
                records_failed=len(result.get('errors', [])),
                event_data={
                    'emails_synced': result['emails_synced'],
                    'emails_skipped': result['emails_skipped'],
                    'errors': result['errors'][:10]  # Limit errors in log
                }
            )
            db.add(event)
        except Exception as e:
            logger.error(f"Failed to log sync event: {e}")


    async def find_contact_by_email(
        self,
        access_token: str,
        instance_url: str,
        email: str
    ) -> Optional[Dict[str, Any]]:
        """
        Look up a Salesforce Contact or Lead by email address.
        Returns dict with 'id' and 'type' ('Contact' or 'Lead'), or None.
        """
        if not email:
            return None

        # Strict email validation to prevent SOQL injection
        # Only allow standard email characters — reject anything suspicious
        email = email.strip().lower()
        if not re.match(r'^[\w.+-]+@[\w.-]+\.\w{2,}$', email):
            logger.warning(f"Invalid email format rejected for SOQL lookup: {email[:50]}")
            return None

        # Try Contact first (preferred for Activity linking)
        for sobject in ["Contact", "Lead"]:
            soql = f"SELECT Id, Name FROM {sobject} WHERE Email = '{email}' LIMIT 1"
            try:
                async with get_sf_client() as client:
                    response = await client.get(
                        f"{instance_url}/services/data/v59.0/query",
                        params={"q": soql},
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=15.0
                    )
                    if response.status_code == 200:
                        data = response.json()
                        records = data.get("records", [])
                        if records:
                            return {
                                "id": records[0]["Id"],
                                "name": records[0].get("Name", ""),
                                "type": sobject
                            }
            except Exception as e:
                logger.warning(f"SOQL lookup failed for {sobject} email={email[:30]}...: {e}")

        return None

    async def send_email_via_salesforce(
        self,
        db: Session,
        integration_profile_id: int,
        to_email: str,
        subject: str,
        html_body: str
    ) -> Dict[str, Any]:
        """
        Send an email through Salesforce's emailSimple action.
        The email is sent FROM the Salesforce user's address and
        an Activity record is automatically created on the contact.

        Returns dict with keys: success, message, sf_contact_id, send_method
        """
        result = {
            "success": False,
            "message": "",
            "sf_contact_id": None,
            "sf_contact_type": None,
            "send_method": "salesforce"
        }

        try:
            access_token, instance_url = await salesforce_oauth.get_access_token(
                db, integration_profile_id
            )
        except Exception as e:
            result["message"] = f"Failed to get Salesforce access token: {e}"
            logger.warning(result["message"])
            return result

        if not access_token:
            result["message"] = "No Salesforce access token available"
            return result

        # Look up the recipient in Salesforce
        sf_record = await self.find_contact_by_email(access_token, instance_url, to_email)
        if sf_record:
            result["sf_contact_id"] = sf_record["id"]
            result["sf_contact_type"] = sf_record["type"]

        # Build emailSimple payload
        email_input = {
            "emailSubject": subject,
            "emailBody": html_body,
            "emailAddresses": to_email,
            "senderType": "CurrentUser"
        }
        if sf_record:
            email_input["relatedToId"] = sf_record["id"]

        payload = {
            "inputs": [email_input]
        }

        # Send via Salesforce emailSimple action
        send_url = f"{instance_url}/services/data/v59.0/actions/standard/emailSimple"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            async with get_sf_client() as client:
                response = await client.post(
                    send_url, json=payload, headers=headers, timeout=30.0
                )

                # Handle 401 — token expired, refresh and retry once
                if response.status_code == 401:
                    logger.info("Salesforce token expired during email send, refreshing...")
                    try:
                        access_token = await salesforce_oauth.refresh_access_token(
                            db, integration_profile_id
                        )
                        profile = db.query(IntegrationProfile).filter(
                            IntegrationProfile.id == integration_profile_id
                        ).first()
                        instance_url = profile.instance_url if profile else instance_url
                    except Exception as refresh_err:
                        result["message"] = f"Token refresh failed: {refresh_err}"
                        return result

                    headers["Authorization"] = f"Bearer {access_token}"
                    send_url = f"{instance_url}/services/data/v59.0/actions/standard/emailSimple"
                    response = await client.post(
                        send_url, json=payload, headers=headers, timeout=30.0
                    )

                if response.status_code in (200, 201):
                    resp_data = response.json()
                    # emailSimple returns a list of results
                    if isinstance(resp_data, list) and resp_data:
                        first = resp_data[0]
                        if first.get("isSuccess", False):
                            result["success"] = True
                            result["message"] = "Email sent via Salesforce"
                            logger.info(f"Email sent via Salesforce to {to_email}")
                        else:
                            errors = first.get("errors", [])
                            err_msg = errors[0].get("message", "Unknown error") if errors else "Unknown error"
                            result["message"] = f"Salesforce email action failed: {err_msg}"
                            logger.warning(result["message"])
                    else:
                        result["success"] = True
                        result["message"] = "Email sent via Salesforce"
                else:
                    error_text = response.text[:500]
                    result["message"] = f"Salesforce API error {response.status_code}: {error_text}"
                    logger.warning(result["message"])

        except Exception as e:
            result["message"] = f"Salesforce email send error: {e}"
            logger.error(result["message"], exc_info=True)

        return result


# Singleton instance
salesforce_email_sync = SalesforceEmailSyncService()
