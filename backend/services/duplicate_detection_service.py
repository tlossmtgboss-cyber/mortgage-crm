"""
Duplicate Detection Service

Identifies duplicate leads/loans based on email, name, phone and creates
tasks for users to review and merge duplicates.
"""

import logging
from typing import List, Dict, Optional, Tuple, Union
from uuid import UUID
from datetime import datetime
from sqlalchemy import func, or_, and_, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class DuplicateDetectionService:
    """Service for detecting and managing duplicate records."""

    # Matching thresholds
    EMAIL_MATCH_WEIGHT = 100  # Exact email match is definitive
    PHONE_MATCH_WEIGHT = 80   # Same phone number
    NAME_MATCH_WEIGHT = 60    # Same first + last name
    PARTIAL_NAME_WEIGHT = 30  # Same last name only

    DUPLICATE_THRESHOLD = 80  # Score needed to flag as duplicate

    def __init__(self, db: Session):
        self.db = db

    def find_duplicate_leads(self, lead_id: Optional[Union[UUID, str]] = None) -> List[Dict]:
        """
        Find duplicate leads in the database using raw SQL to avoid
        ORM enum deserialization issues with mismatched stage values.

        Args:
            lead_id: Optional specific lead to check for duplicates.
                     If None, scans entire database.

        Returns:
            List of duplicate groups with confidence scores.
        """
        # Use raw SQL to avoid SQLAlchemy enum deserialization crashes
        # when leads have stage values that don't match the Python enum names
        if lead_id:
            result = self.db.execute(
                text("SELECT id, name, email, phone, loan_number, stage::text as stage, created_at FROM leads WHERE id = :lead_id"),
                {"lead_id": str(lead_id)}
            )
        else:
            result = self.db.execute(
                text("SELECT id, name, email, phone, loan_number, stage::text as stage, created_at FROM leads")
            )

        leads = result.fetchall()
        columns = result.keys()
        leads = [dict(zip(columns, row)) for row in leads]

        logger.info(f"Found {len(leads)} leads to scan for duplicates (using raw SQL)")

        # Group leads by email (simple approach like frontend)
        email_groups = {}
        for lead in leads:
            if lead.get('email'):
                email_lower = lead['email'].lower()
                if email_lower not in email_groups:
                    email_groups[email_lower] = []
                email_groups[email_lower].append(lead)

        duplicates = []
        checked_pairs = set()

        # Find groups with duplicates
        for email, lead_group in email_groups.items():
            if len(lead_group) < 2:
                continue

            # Create duplicate entries for each pair
            for i, lead1 in enumerate(lead_group):
                for lead2 in lead_group[i+1:]:
                    # Avoid duplicate pairs
                    pair_key = tuple(sorted([str(lead1['id']), str(lead2['id'])]))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    name1 = lead1.get('name') or 'Unknown'
                    name2 = lead2.get('name') or 'Unknown'

                    created1 = lead1.get('created_at')
                    created2 = lead2.get('created_at')

                    duplicates.append({
                        'type': 'lead',
                        'record_1': {
                            'id': str(lead1['id']),
                            'name': name1,
                            'email': lead1.get('email'),
                            'phone': lead1.get('phone'),
                            'loan_number': lead1.get('loan_number'),
                            'created_at': created1.isoformat() if created1 else None,
                            'stage': lead1.get('stage'),
                            'status': None
                        },
                        'record_2': {
                            'id': str(lead2['id']),
                            'name': name2,
                            'email': lead2.get('email'),
                            'phone': lead2.get('phone'),
                            'loan_number': lead2.get('loan_number'),
                            'created_at': created2.isoformat() if created2 else None,
                            'stage': lead2.get('stage'),
                            'status': None
                        },
                        'confidence_score': self.EMAIL_MATCH_WEIGHT,  # 100% for email match
                        'match_reasons': [f"Same email: {email}"]
                    })

        logger.info(f"Found {len(duplicates)} duplicate pairs")
        return duplicates

    def _calculate_match_score(self, lead1, lead2) -> Tuple[int, List[str]]:
        """Calculate duplicate confidence score between two leads."""
        score = 0
        reasons = []

        # Email match
        if lead1.email and lead2.email and lead1.email.lower() == lead2.email.lower():
            score += self.EMAIL_MATCH_WEIGHT
            reasons.append(f"Same email: {lead1.email}")

        # Phone match
        if lead1.phone and lead2.phone:
            phone1 = self._normalize_phone(lead1.phone)
            phone2 = self._normalize_phone(lead2.phone)
            if phone1 and phone2 and phone1 == phone2:
                score += self.PHONE_MATCH_WEIGHT
                reasons.append(f"Same phone: {lead1.phone}")

        # Name match
        if lead1.first_name and lead1.last_name and lead2.first_name and lead2.last_name:
            if (lead1.first_name.lower() == lead2.first_name.lower() and
                lead1.last_name.lower() == lead2.last_name.lower()):
                score += self.NAME_MATCH_WEIGHT
                reasons.append(f"Same name: {lead1.first_name} {lead1.last_name}")
        elif lead1.last_name and lead2.last_name:
            if lead1.last_name.lower() == lead2.last_name.lower():
                score += self.PARTIAL_NAME_WEIGHT
                reasons.append(f"Same last name: {lead1.last_name}")

        return score, reasons

    def _normalize_phone(self, phone: str) -> Optional[str]:
        """Normalize phone number to digits only."""
        if not phone:
            return None
        digits = ''.join(c for c in phone if c.isdigit())
        # Remove country code if present
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        return digits if len(digits) == 10 else None

    def find_duplicate_loans(self) -> List[Dict]:
        """Find duplicate loans based on borrower email using raw SQL."""
        # Use raw SQL to avoid ORM enum issues (stage is a String column)
        result = self.db.execute(
            text("""
                SELECT id, loan_number, borrower_name, borrower_email,
                       amount, stage, created_at
                FROM loans
                WHERE stage IS NULL
                   OR stage NOT IN ('FUNDED', 'DEAD')
            """)
        )
        loans = result.fetchall()
        columns = result.keys()
        loans = [dict(zip(columns, row)) for row in loans]

        # Group by borrower email
        email_groups = {}
        for loan in loans:
            if loan.get('borrower_email'):
                email_lower = loan['borrower_email'].lower()
                if email_lower not in email_groups:
                    email_groups[email_lower] = []
                email_groups[email_lower].append(loan)

        duplicates = []
        checked_pairs = set()

        for email, loan_group in email_groups.items():
            if len(loan_group) < 2:
                continue

            for i, loan in enumerate(loan_group):
                for match in loan_group[i+1:]:
                    pair_key = tuple(sorted([loan['id'], match['id']]))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    duplicates.append({
                        'type': 'loan',
                        'record_1': {
                            'id': loan['id'],
                            'loan_number': loan.get('loan_number'),
                            'borrower_name': loan.get('borrower_name') or '',
                            'borrower_email': loan.get('borrower_email'),
                            'amount': float(loan['amount']) if loan.get('amount') else None,
                            'status': loan.get('stage'),
                            'created_at': loan['created_at'].isoformat() if loan.get('created_at') else None
                        },
                        'record_2': {
                            'id': match['id'],
                            'loan_number': match.get('loan_number'),
                            'borrower_name': match.get('borrower_name') or '',
                            'borrower_email': match.get('borrower_email'),
                            'amount': float(match['amount']) if match.get('amount') else None,
                            'status': match.get('stage'),
                            'created_at': match['created_at'].isoformat() if match.get('created_at') else None
                        },
                        'confidence_score': 100,
                        'match_reasons': [f"Same borrower email: {email}"]
                    })

        return duplicates

    def create_merge_task(
        self,
        duplicate_info: Dict,
        assigned_to_user_id: int
    ) -> Dict:
        """
        Create a task to review and merge duplicate records.

        Args:
            duplicate_info: Dict with duplicate records info
            assigned_to_user_id: User ID to assign the task to

        Returns:
            Created task info
        """
        from database.models import Task

        record_type = duplicate_info['type']
        record_1 = duplicate_info['record_1']
        record_2 = duplicate_info['record_2']
        reasons = duplicate_info['match_reasons']
        score = duplicate_info['confidence_score']

        # Build task description
        name_1 = record_1.get('name') or record_1.get('borrower_name', 'Unknown')
        name_2 = record_2.get('name') or record_2.get('borrower_name', 'Unknown')

        title = f"Review Duplicate {record_type.title()}: {name_1}"

        description = f"""Potential duplicate {record_type} records detected.

**Match Confidence: {score}%**
**Match Reasons:** {', '.join(reasons)}

---

**Record 1:**
- Name: {name_1}
- Email: {record_1.get('email') or record_1.get('borrower_email', 'N/A')}
- {record_type.title()} #: {record_1.get('loan_number', 'N/A')}
- Status: {record_1.get('status', 'N/A')}
- Created: {record_1.get('created_at', 'N/A')}

**Record 2:**
- Name: {name_2}
- Email: {record_2.get('email') or record_2.get('borrower_email', 'N/A')}
- {record_type.title()} #: {record_2.get('loan_number', 'N/A')}
- Status: {record_2.get('status', 'N/A')}
- Created: {record_2.get('created_at', 'N/A')}

---

**Action Required:** Review these records and merge if they are duplicates.
"""

        # Check if task already exists for this duplicate pair
        logger.info(f"Checking for existing task with title: {title}")
        existing_task = self.db.query(Task).filter(
            Task.title == title,
            Task.status != 'completed'
        ).first()

        if existing_task:
            logger.info(f"Task already exists: {existing_task.id} - {existing_task.title}")
            return {
                'task_id': existing_task.id,
                'status': 'existing',
                'message': 'Task already exists for this duplicate'
            }

        # Create task
        # Note: Task model uses Integer FKs - lead_id refs leads.id, loan_id refs loans.id
        # LeadProfile uses UUID, so we can't link to Task.lead_id
        # Only link loan_id for loan duplicates
        task = Task(
            title=title,
            description=description,
            status='pending',
            priority='high' if score >= 90 else 'medium',
            owner_id=assigned_to_user_id,
            related_type=f'duplicate_{record_type}',
            related_contact_name=name_1,
            loan_id=record_1['id'] if record_type == 'loan' and isinstance(record_1.get('id'), int) else None
        )

        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        logger.info(f"Created merge task {task.id} for duplicate {record_type}: {name_1}")

        return {
            'task_id': task.id,
            'status': 'created',
            'message': f'Task created to review duplicate {record_type}'
        }

    def scan_and_create_tasks(self, assigned_to_user_id: int) -> Dict:
        """
        Scan for all duplicates and create tasks for each.

        Returns:
            Summary of scan results
        """
        import traceback

        results = {
            'lead_duplicates_found': 0,
            'loan_duplicates_found': 0,
            'tasks_created': 0,
            'tasks_existing': 0,
            'duplicates': [],
            'errors': []
        }

        # Scan leads
        try:
            lead_duplicates = self.find_duplicate_leads()
            results['lead_duplicates_found'] = len(lead_duplicates)
            logger.info(f"Found {len(lead_duplicates)} lead duplicates")
        except Exception as e:
            logger.error(f"Error finding lead duplicates: {e}")
            lead_duplicates = []
            results['errors'].append(f"Lead scan error: {str(e)}")

        for dup in lead_duplicates:
            try:
                task_result = self.create_merge_task(dup, assigned_to_user_id)
                if task_result['status'] == 'created':
                    results['tasks_created'] += 1
                else:
                    results['tasks_existing'] += 1
                results['duplicates'].append({
                    **dup,
                    'task': task_result
                })
            except Exception as e:
                logger.error(f"Error creating task for lead duplicate: {e}")
                results['errors'].append(f"Task creation error: {str(e)}")

        # Scan loans
        try:
            loan_duplicates = self.find_duplicate_loans()
            results['loan_duplicates_found'] = len(loan_duplicates)
            logger.info(f"Found {len(loan_duplicates)} loan duplicates")
        except Exception as e:
            logger.error(f"Error finding loan duplicates: {e}")
            loan_duplicates = []
            results['errors'].append(f"Loan scan error: {str(e)}")

        for dup in loan_duplicates:
            try:
                task_result = self.create_merge_task(dup, assigned_to_user_id)
                if task_result['status'] == 'created':
                    results['tasks_created'] += 1
                else:
                    results['tasks_existing'] += 1
                results['duplicates'].append({
                    **dup,
                    'task': task_result
                })
            except Exception as e:
                logger.error(f"Error creating task for loan duplicate: {e}")
                results['errors'].append(f"Task creation error: {str(e)}")

        logger.info(
            f"Duplicate scan complete: {results['lead_duplicates_found']} lead duplicates, "
            f"{results['loan_duplicates_found']} loan duplicates, "
            f"{results['tasks_created']} tasks created, {len(results['errors'])} errors"
        )

        return results


def get_duplicate_detection_service(db: Session) -> DuplicateDetectionService:
    """Factory function for DuplicateDetectionService."""
    return DuplicateDetectionService(db)
