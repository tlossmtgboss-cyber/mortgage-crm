"""
Duplicate Detection Service

Identifies duplicate leads/loans based on email, name, phone and creates
tasks for users to review and merge duplicates.
"""

import logging
from typing import List, Dict, Optional, Tuple, Union
from uuid import UUID
from datetime import datetime
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

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
        Find duplicate leads in the database.

        Args:
            lead_id: Optional specific lead to check for duplicates.
                     If None, scans entire database.

        Returns:
            List of duplicate groups with confidence scores.
        """
        from models.lead_profile import LeadProfile

        # Get leads to check
        if lead_id:
            leads = self.db.query(LeadProfile).filter(LeadProfile.id == lead_id).all()
        else:
            leads = self.db.query(LeadProfile).filter(
                LeadProfile.status != 'archived'
            ).all()

        duplicates = []
        checked_pairs = set()

        for lead in leads:
            # Find potential matches
            potential_matches = self._find_potential_lead_matches(lead)

            for match, score, reasons in potential_matches:
                # Avoid duplicate pairs
                pair_key = tuple(sorted([str(lead.id), str(match.id)]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                if score >= self.DUPLICATE_THRESHOLD:
                    duplicates.append({
                        'type': 'lead',
                        'record_1': {
                            'id': str(lead.id),
                            'name': f"{lead.first_name or ''} {lead.last_name or ''}".strip(),
                            'email': lead.email,
                            'phone': lead.phone,
                            'loan_number': lead.loan_number,
                            'created_at': lead.lead_created_date.isoformat() if lead.lead_created_date else None,
                            'stage': lead.stage,
                            'status': lead.status
                        },
                        'record_2': {
                            'id': str(match.id),
                            'name': f"{match.first_name or ''} {match.last_name or ''}".strip(),
                            'email': match.email,
                            'phone': match.phone,
                            'loan_number': match.loan_number,
                            'created_at': match.lead_created_date.isoformat() if match.lead_created_date else None,
                            'stage': match.stage,
                            'status': match.status
                        },
                        'confidence_score': score,
                        'match_reasons': reasons
                    })

        return duplicates

    def _find_potential_lead_matches(self, lead) -> List[Tuple]:
        """Find potential duplicate matches for a lead."""
        from models.lead_profile import LeadProfile

        matches = []

        # Build query for potential matches
        conditions = []

        # Email match (strongest signal)
        if lead.email:
            conditions.append(
                and_(
                    LeadProfile.email == lead.email,
                    LeadProfile.id != lead.id
                )
            )

        # Phone match
        if lead.phone:
            normalized_phone = self._normalize_phone(lead.phone)
            if normalized_phone:
                conditions.append(
                    and_(
                        func.regexp_replace(LeadProfile.phone, '[^0-9]', '', 'g') == normalized_phone,
                        LeadProfile.id != lead.id
                    )
                )

        # Name match (first + last)
        if lead.first_name and lead.last_name:
            conditions.append(
                and_(
                    func.lower(LeadProfile.first_name) == lead.first_name.lower(),
                    func.lower(LeadProfile.last_name) == lead.last_name.lower(),
                    LeadProfile.id != lead.id
                )
            )

        if not conditions:
            return []

        potential_matches = self.db.query(LeadProfile).filter(
            LeadProfile.status != 'archived',
            or_(*conditions)
        ).all()

        # Score each match
        for match in potential_matches:
            score, reasons = self._calculate_match_score(lead, match)
            if score > 0:
                matches.append((match, score, reasons))

        return matches

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
        """Find duplicate loans based on borrower info."""
        from main import Loan, LoanStage

        # Get all active loans (exclude funded and dead loans)
        loans = self.db.query(Loan).filter(
            Loan.stage.notin_([LoanStage.FUNDED, LoanStage.DEAD])
        ).all()

        duplicates = []
        checked_pairs = set()

        for loan in loans:
            # Check for loans with same borrower email
            if loan.borrower_email:
                matches = self.db.query(Loan).filter(
                    Loan.id != loan.id,
                    Loan.borrower_email == loan.borrower_email,
                    Loan.stage.notin_([LoanStage.FUNDED, LoanStage.DEAD])
                ).all()

                for match in matches:
                    pair_key = tuple(sorted([loan.id, match.id]))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    duplicates.append({
                        'type': 'loan',
                        'record_1': {
                            'id': loan.id,
                            'loan_number': loan.loan_number,
                            'borrower_name': loan.borrower_name or '',
                            'borrower_email': loan.borrower_email,
                            'amount': float(loan.amount) if loan.amount else None,
                            'status': str(loan.stage.value) if loan.stage else loan.status,
                            'created_at': loan.created_at.isoformat() if loan.created_at else None
                        },
                        'record_2': {
                            'id': match.id,
                            'loan_number': match.loan_number,
                            'borrower_name': match.borrower_name or '',
                            'borrower_email': match.borrower_email,
                            'amount': float(match.amount) if match.amount else None,
                            'status': str(match.stage.value) if match.stage else match.status,
                            'created_at': match.created_at.isoformat() if match.created_at else None
                        },
                        'confidence_score': 100,
                        'match_reasons': [f"Same borrower email: {loan.borrower_email}"]
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
        from main import Task

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
        existing_task = self.db.query(Task).filter(
            Task.title == title,
            Task.status != 'completed'
        ).first()

        if existing_task:
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
            logger.error(f"Error finding lead duplicates: {e}\n{traceback.format_exc()}")
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
                logger.error(f"Error creating task for lead duplicate: {e}\n{traceback.format_exc()}")
                results['errors'].append(f"Task creation error: {str(e)}")

        # Scan loans
        try:
            loan_duplicates = self.find_duplicate_loans()
            results['loan_duplicates_found'] = len(loan_duplicates)
            logger.info(f"Found {len(loan_duplicates)} loan duplicates")
        except Exception as e:
            logger.error(f"Error finding loan duplicates: {e}\n{traceback.format_exc()}")
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
                logger.error(f"Error creating task for loan duplicate: {e}\n{traceback.format_exc()}")
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
