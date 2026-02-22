"""
Salesforce Calendar/Event Sync Service
Syncs Event and Task records from Salesforce to CRM calendar
"""
import json
import logging
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


class SalesforceCalendarSyncService:
    """Syncs calendar events from Salesforce to CRM"""

    async def sync_calendar(
        self,
        db: Session,
        integration_profile_id: int,
        days_back: int = 30,
        days_forward: int = 90,
        limit: int = 500
    ) -> Dict[str, Any]:
        """
        Sync calendar events from Salesforce to CRM.

        Pulls Event records from Salesforce and creates corresponding
        calendar_events records in the CRM.
        """
        result = {
            'success': False,
            'events_synced': 0,
            'events_skipped': 0,
            'tasks_synced': 0,
            'tasks_skipped': 0,
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

            # Calculate date filters
            start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
            end_date = (datetime.now(timezone.utc) + timedelta(days=days_forward)).strftime('%Y-%m-%dT%H:%M:%SZ')

            # Query Event objects from Salesforce
            events = await self._query_events(
                access_token, instance_url, start_date, end_date, limit
            )

            # Query Task objects (scheduled activities)
            tasks = await self._query_scheduled_tasks(
                access_token, instance_url, start_date, end_date, limit
            )

            # Process Event records
            for sf_event in events:
                try:
                    synced = await self._process_event(db, user_id, sf_event, instance_url)
                    if synced:
                        result['events_synced'] += 1
                    else:
                        result['events_skipped'] += 1
                except Exception as e:
                    logger.error(f"Error processing Event {sf_event.get('Id')}: {e}")
                    result['errors'].append(f"Event {sf_event.get('Id')}: {str(e)[:100]}")
                    # Rollback to recover from any transaction errors (e.g., constraint violations)
                    try:
                        db.rollback()
                    except Exception as e:
                        logger.exception(f"Failed to rollback after Event processing error: {e}")

            # Process Task records
            for sf_task in tasks:
                try:
                    synced = await self._process_task(db, user_id, sf_task, instance_url)
                    if synced:
                        result['tasks_synced'] += 1
                    else:
                        result['tasks_skipped'] += 1
                except Exception as e:
                    logger.error(f"Error processing Task {sf_task.get('Id')}: {e}")
                    result['errors'].append(f"Task {sf_task.get('Id')}: {str(e)[:100]}")
                    # Rollback to recover from any transaction errors
                    try:
                        db.rollback()
                    except Exception as e:
                        logger.exception(f"Failed to rollback after Task processing error: {e}")

            # Log sync event
            self._log_sync_event(db, integration_profile_id, result)

            result['success'] = True
            db.commit()

        except Exception as e:
            logger.error(f"Calendar sync failed: {e}")
            result['errors'].append(str(e))
            db.rollback()

        return result

    async def _query_events(
        self,
        access_token: str,
        instance_url: str,
        start_date: str,
        end_date: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Query Event objects from Salesforce"""
        soql = f"""
            SELECT Id, OwnerId, WhoId, WhatId, Subject, Location,
                   StartDateTime, EndDateTime, ActivityDate, ActivityDateTime,
                   DurationInMinutes, Description, IsAllDayEvent, IsPrivate,
                   ShowAs, RecurrenceActivityId, IsRecurrence,
                   CreatedDate, LastModifiedDate
            FROM Event
            WHERE StartDateTime >= {start_date} AND StartDateTime <= {end_date}
            ORDER BY StartDateTime ASC
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
                    logger.warning(f"Event query failed: {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            logger.error(f"Error querying Events: {e}")
            return []

    async def _query_scheduled_tasks(
        self,
        access_token: str,
        instance_url: str,
        start_date: str,
        end_date: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Query Task records with scheduled dates from Salesforce"""
        soql = f"""
            SELECT Id, OwnerId, WhoId, WhatId, Subject, Description,
                   ActivityDate, Status, Priority, TaskSubtype,
                   ReminderDateTime, IsReminderSet,
                   CreatedDate, LastModifiedDate
            FROM Task
            WHERE ActivityDate >= {start_date[:10]} AND ActivityDate <= {end_date[:10]}
                AND TaskSubtype != 'Email'
            ORDER BY ActivityDate ASC
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
                    logger.warning(f"Task query failed: {response.status_code} - {response.text}")
                    return []
        except Exception as e:
            logger.error(f"Error querying Tasks: {e}")
            return []

    async def _process_event(
        self,
        db: Session,
        user_id: int,
        sf_event: Dict[str, Any],
        instance_url: str
    ) -> bool:
        """Process a Salesforce Event and create CRM calendar record"""
        sf_id = sf_event.get('Id')

        # Check if already synced
        existing = db.execute(text("""
            SELECT id FROM calendar_events
            WHERE meta_data->>'salesforce_id' = :sf_id
        """), {"sf_id": sf_id}).fetchone()

        if existing:
            return False  # Already synced

        # Find related lead/loan
        lead_id, loan_id = await self._find_related_records(
            db, sf_event.get('WhoId'), sf_event.get('WhatId'), user_id
        )

        # Parse dates
        start_time = sf_event.get('StartDateTime')
        end_time = sf_event.get('EndDateTime')

        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except Exception as e:
                logger.exception(f"Failed to parse Event StartDateTime '{start_time}': {e}")
                start_dt = datetime.now(timezone.utc)
        else:
            start_dt = datetime.now(timezone.utc)

        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except Exception as e:
                logger.exception(f"Failed to parse Event EndDateTime '{end_time}': {e}")
                end_dt = start_dt + timedelta(hours=1)
        else:
            end_dt = start_dt + timedelta(hours=1)

        # Determine event type
        sf_type = sf_event.get('Type', '').lower()
        if 'call' in sf_type:
            event_type = 'call'
        elif 'meeting' in sf_type:
            event_type = 'meeting'
        else:
            event_type = 'appointment'

        # Create calendar event
        db.execute(text("""
            INSERT INTO calendar_events (
                user_id, lead_id, loan_id, title, description,
                event_type, location, start_time, end_time,
                all_day, status, meta_data, created_at
            ) VALUES (
                :user_id, :lead_id, :loan_id, :title, :description,
                :event_type, :location, :start_time, :end_time,
                :all_day, :status, CAST(:meta_data AS jsonb), :created_at
            )
        """), {
            "user_id": user_id,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "title": sf_event.get('Subject', 'Salesforce Event'),
            "description": sf_event.get('Description', ''),
            "event_type": event_type,
            "location": sf_event.get('Location', ''),
            "start_time": start_dt,
            "end_time": end_dt,
            "all_day": sf_event.get('IsAllDayEvent', False),
            "status": 'confirmed',
            "meta_data": json.dumps({
                "salesforce_id": sf_id,
                "salesforce_who_id": sf_event.get('WhoId'),
                "salesforce_what_id": sf_event.get('WhatId'),
                "salesforce_type": sf_event.get('Type'),
                "show_as": sf_event.get('ShowAs'),
                "source": "salesforce_sync"
            }),
            "created_at": datetime.now(timezone.utc)
        })

        return True

    async def _process_task(
        self,
        db: Session,
        user_id: int,
        sf_task: Dict[str, Any],
        instance_url: str
    ) -> bool:
        """Process a Salesforce Task and create CRM task record"""
        sf_id = sf_task.get('Id')

        # Check if already synced
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE meta_data->>'salesforce_task_id' = :sf_id
        """), {"sf_id": sf_id}).fetchone()

        if existing:
            return False  # Already synced

        # Find related lead/loan
        lead_id, loan_id = await self._find_related_records(
            db, sf_task.get('WhoId'), sf_task.get('WhatId'), user_id
        )

        # Parse due date
        activity_date = sf_task.get('ActivityDate')
        if activity_date:
            try:
                due_date = datetime.fromisoformat(activity_date)
            except Exception as e:
                logger.exception(f"Failed to parse Task ActivityDate '{activity_date}': {e}")
                due_date = datetime.now(timezone.utc)
        else:
            due_date = datetime.now(timezone.utc)

        # Map status
        sf_status = sf_task.get('Status', '').lower()
        if 'completed' in sf_status:
            status = 'completed'
        elif 'in progress' in sf_status:
            status = 'in_progress'
        else:
            status = 'pending'

        # Map priority
        sf_priority = sf_task.get('Priority', '').lower()
        if 'high' in sf_priority:
            priority = 'high'
        elif 'low' in sf_priority:
            priority = 'low'
        else:
            priority = 'normal'

        # Create task record (tasks table uses owner_id, not user_id)
        db.execute(text("""
            INSERT INTO tasks (
                owner_id, lead_id, loan_id, title, description,
                due_date, status, priority, meta_data, created_at
            ) VALUES (
                :owner_id, :lead_id, :loan_id, :title, :description,
                :due_date, :status, :priority, CAST(:meta_data AS jsonb), :created_at
            )
        """), {
            "owner_id": user_id,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "title": sf_task.get('Subject', 'Salesforce Task'),
            "description": sf_task.get('Description', ''),
            "due_date": due_date,
            "status": status,
            "priority": priority,
            "meta_data": json.dumps({
                "salesforce_task_id": sf_id,
                "salesforce_who_id": sf_task.get('WhoId'),
                "salesforce_what_id": sf_task.get('WhatId'),
                "task_subtype": sf_task.get('TaskSubtype'),
                "source": "salesforce_sync"
            }),
            "created_at": datetime.now(timezone.utc)
        })

        return True

    async def _find_related_records(
        self,
        db: Session,
        who_id: Optional[str],
        what_id: Optional[str],
        user_id: int
    ) -> tuple:
        """Find related lead_id and loan_id from Salesforce IDs"""
        lead_id = None
        loan_id = None

        if who_id:
            # WhoId is usually a Contact or Lead
            result = db.execute(text("""
                SELECT id FROM leads
                WHERE salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id
                LIMIT 1
            """), {"sf_id": who_id}).fetchone()
            lead_id = result[0] if result else None

        if what_id:
            # WhatId is usually an Opportunity (loan)
            result = db.execute(text("""
                SELECT id FROM loans
                WHERE salesforce_id = :sf_id OR meta_data->>'salesforce_id' = :sf_id
                LIMIT 1
            """), {"sf_id": what_id}).fetchone()
            loan_id = result[0] if result else None

        return lead_id, loan_id

    def _log_sync_event(
        self,
        db: Session,
        integration_profile_id: int,
        result: Dict[str, Any]
    ):
        """Log the sync event"""
        try:
            total_synced = result['events_synced'] + result['tasks_synced']
            total_skipped = result['events_skipped'] + result['tasks_skipped']
            event = IntegrationEvent(
                integration_profile_id=integration_profile_id,
                event_type='calendar_sync_completed' if result['success'] else 'calendar_sync_failed',
                status='success' if result['success'] else 'error',
                direction='inbound',
                records_processed=total_synced + total_skipped,
                records_succeeded=total_synced,
                records_failed=len(result.get('errors', [])),
                event_data={
                    'events_synced': result['events_synced'],
                    'events_skipped': result['events_skipped'],
                    'tasks_synced': result['tasks_synced'],
                    'tasks_skipped': result['tasks_skipped'],
                    'errors': result['errors'][:10]  # Limit errors in log
                }
            )
            db.add(event)
        except Exception as e:
            logger.error(f"Failed to log sync event: {e}")


# Singleton instance
salesforce_calendar_sync = SalesforceCalendarSyncService()
