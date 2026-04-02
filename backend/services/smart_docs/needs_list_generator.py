"""
Smart Document Collection - Needs List Generator

Generates intelligent document requirements (needs list) based on:
- Loan program (Conventional, FHA, VA, USDA)
- Occupancy type (Primary, Second Home, Investment)
- Income type (W2, Self-Employed, Retirement)
- Borrower profile and loan characteristics

Uses configurable templates stored in NeedsListTemplate table.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models.smart_docs_models import (
    DocumentRequest, NeedsListTemplate, DocPolicyEvent,
    DocType, RequestStatus, RequestPriority, AppliesTo,
    PayrollFrequency, DocPolicyEventType
)

logger = logging.getLogger(__name__)


class NeedsListGenerator:
    """
    Generates and manages document needs lists for loan applications.

    The needs list is generated based on:
    1. Loan program requirements (Conventional, FHA, VA, etc.)
    2. Income verification requirements based on employment type
    3. Property-specific requirements based on occupancy
    4. Borrower-specific requirements (co-borrower, special circumstances)
    """

    # Freshness requirements by document type (in days)
    FRESHNESS_REQUIREMENTS = {
        DocType.PAYSTUB: 30,
        DocType.BANK_STATEMENT: 90,
        DocType.INVESTMENT_STATEMENT: 90,
        DocType.PROFIT_LOSS: 90,
        DocType.BALANCE_SHEET: 90,
    }

    # Documents that support auto-renewal
    AUTO_RENEW_ELIGIBLE = {
        DocType.PAYSTUB,
        DocType.BANK_STATEMENT,
        DocType.INVESTMENT_STATEMENT,
        DocType.PROFIT_LOSS,
    }

    def __init__(self, db: Session):
        self.db = db

    def generate_needs_list(
        self,
        loan_id: int,
        loan_program: str,
        occupancy_type: str,
        income_type: str,
        borrower_id: int,
        co_borrower_id: Optional[int] = None,
        has_gift_funds: bool = False,
        is_self_employed: bool = False,
        has_bankruptcy: bool = False,
        property_type: Optional[str] = None,
        income_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a complete needs list for a loan application.

        Args:
            loan_id: The loan ID to generate needs list for
            loan_program: CONVENTIONAL, FHA, VA, USDA
            occupancy_type: PRIMARY, SECOND_HOME, INVESTMENT
            income_type: W2, SELF_EMPLOYED, RETIREMENT (legacy broad type)
            borrower_id: Primary borrower ID
            co_borrower_id: Optional co-borrower ID
            has_gift_funds: Whether gift funds are being used
            is_self_employed: Whether borrower is self-employed
            has_bankruptcy: Whether borrower has bankruptcy history
            property_type: Type of property (for condo requirements, etc.)
            income_types: List of specific income types (e.g., ['W2_SALARY', 'RENTAL_SCHEDULE_E'])

        Returns:
            Dict with generated needs list details
        """
        logger.info(f"Generating needs list for loan {loan_id}, income_types={income_types}")

        # Find matching template
        template = self._find_matching_template(
            loan_program, occupancy_type, income_type
        )

        if not template:
            logger.warning(f"No template found for {loan_program}/{occupancy_type}/{income_type}, using defaults")
            requests = self._generate_default_requirements(
                loan_id, borrower_id, income_type
            )
        else:
            requests = self._generate_from_template(
                template, loan_id, borrower_id
            )

        # Add conditional requirements
        if co_borrower_id:
            requests.extend(
                self._generate_co_borrower_requirements(loan_id, co_borrower_id)
            )

        if has_gift_funds:
            requests.append(
                self._create_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    doc_type=DocType.GIFT_LETTER,
                    title="Gift Letter",
                    description="Gift letter and donor documentation",
                    instructions="Upload a signed gift letter and proof of donor's ability to gift.",
                    priority=RequestPriority.HIGH,
                )
            )

        if has_bankruptcy:
            requests.append(
                self._create_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    doc_type=DocType.BANKRUPTCY_DISCHARGE,
                    title="Bankruptcy Discharge Papers",
                    description="Proof of bankruptcy discharge",
                    instructions="Upload complete bankruptcy discharge documents.",
                    priority=RequestPriority.HIGH,
                )
            )

        # Add income-type-specific document requests
        if income_types:
            income_requests = self._generate_income_type_specific_requests(
                loan_id=loan_id,
                borrower_id=borrower_id,
                income_types=income_types
            )
            requests.extend(income_requests)

        # Bulk insert all requests
        self.db.add_all(requests)
        self.db.flush()

        # Log the event
        event = DocPolicyEvent(
            loan_id=loan_id,
            event_type=DocPolicyEventType.NEEDS_LIST_GENERATED,
            payload={
                "request_count": len(requests),
                "template_used": template.slug if template else "default",
                "loan_program": loan_program,
                "occupancy_type": occupancy_type,
                "income_type": income_type,
            }
        )
        self.db.add(event)
        self.db.commit()

        logger.info(f"Generated {len(requests)} document requests for loan {loan_id}")

        return {
            "loan_id": loan_id,
            "request_count": len(requests),
            "requests": [self._request_to_dict(r) for r in requests],
            "template_used": template.slug if template else "default",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _find_matching_template(
        self,
        loan_program: str,
        occupancy_type: str,
        income_type: str,
    ) -> Optional[NeedsListTemplate]:
        """Find the best matching template for given criteria."""
        import json

        templates = self.db.query(NeedsListTemplate).filter(
            NeedsListTemplate.is_active == True
        ).all()

        best_match = None
        best_score = 0

        for template in templates:
            score = 0

            # Parse JSON fields
            programs = json.loads(template.loan_programs) if template.loan_programs else []
            occupancies = json.loads(template.occupancy_types) if template.occupancy_types else []
            incomes = json.loads(template.income_types) if template.income_types else []

            # Score based on matches
            if loan_program.upper() in programs:
                score += 3
            if occupancy_type.upper() in occupancies:
                score += 2
            if income_type.upper() in incomes:
                score += 1

            if score > best_score:
                best_score = score
                best_match = template

        return best_match if best_score > 0 else None

    def _generate_from_template(
        self,
        template: NeedsListTemplate,
        loan_id: int,
        borrower_id: int,
    ) -> List[DocumentRequest]:
        """Generate document requests from a template."""
        import json

        requests = []
        request_templates = json.loads(template.request_templates)

        for req_template in request_templates:
            doc_type = DocType(req_template["doc_type"])
            priority = RequestPriority(req_template.get("priority", "NORMAL"))
            applies_to = AppliesTo(req_template.get("applies_to", "BORROWER"))

            request = self._create_request(
                loan_id=loan_id,
                borrower_id=borrower_id if applies_to != AppliesTo.CO_BORROWER else None,
                doc_type=doc_type,
                title=req_template["title"],
                description=req_template.get("description"),
                instructions=req_template.get("instructions"),
                required_count=req_template.get("required_count", 1),
                priority=priority,
                applies_to=applies_to,
                freshness_days=req_template.get("freshness_days"),
                auto_renew=req_template.get("auto_renew", False),
            )
            requests.append(request)

        return requests

    def _generate_default_requirements(
        self,
        loan_id: int,
        borrower_id: int,
        income_type: str,
    ) -> List[DocumentRequest]:
        """Generate default requirements when no template matches."""
        requests = []

        # ID
        requests.append(
            self._create_request(
                loan_id=loan_id,
                borrower_id=borrower_id,
                doc_type=DocType.DRIVERS_LICENSE,
                title="Government-Issued ID",
                description="Valid driver's license or passport",
                priority=RequestPriority.HIGH,
            )
        )

        # Income docs
        if income_type.upper() != "SELF_EMPLOYED":
            requests.append(
                self._create_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    doc_type=DocType.PAYSTUB,
                    title="Recent Pay Stubs",
                    description="Most recent 30 days of pay stubs",
                    required_count=2,
                    priority=RequestPriority.HIGH,
                    freshness_days=30,
                    auto_renew=True,
                )
            )
            requests.append(
                self._create_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    doc_type=DocType.W2,
                    title="W-2 Forms",
                    description="W-2s for the past 2 years",
                    required_count=2,
                    priority=RequestPriority.HIGH,
                )
            )
        else:
            requests.append(
                self._create_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    doc_type=DocType.TAX_RETURN,
                    title="Personal Tax Returns",
                    description="Complete tax returns for past 2 years",
                    required_count=2,
                    priority=RequestPriority.HIGH,
                )
            )
            requests.append(
                self._create_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    doc_type=DocType.BUSINESS_TAX_RETURN,
                    title="Business Tax Returns",
                    description="Business tax returns for past 2 years",
                    required_count=2,
                    priority=RequestPriority.HIGH,
                )
            )
            requests.append(
                self._create_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    doc_type=DocType.PROFIT_LOSS,
                    title="Year-to-Date P&L",
                    description="Current year profit and loss statement",
                    priority=RequestPriority.HIGH,
                    freshness_days=90,
                    auto_renew=True,
                )
            )

        # Bank statements
        requests.append(
            self._create_request(
                loan_id=loan_id,
                borrower_id=borrower_id,
                doc_type=DocType.BANK_STATEMENT,
                title="Bank Statements",
                description="Most recent 2 months of bank statements",
                required_count=2,
                priority=RequestPriority.HIGH,
                freshness_days=90,
                auto_renew=True,
            )
        )

        return requests

    def _generate_income_type_specific_requests(
        self,
        loan_id: int,
        borrower_id: int,
        income_types: List[str]
    ) -> List[DocumentRequest]:
        """
        Generate document requests specific to the selected income types.
        This ensures we request exactly the documents needed for each income type
        the borrower selected during application.
        """
        requests = []
        seen_doc_types = set()  # Avoid duplicates

        # Income type to document requirements mapping
        # Uses existing DocType values - SSA_LETTER, PENSION_STATEMENT, BUSINESS_LICENSE use OTHER
        income_doc_requirements = {
            "W2_HOURLY": [
                {"doc_type": DocType.PAYSTUB, "title": "Recent Pay Stubs", "description": "Most recent 30 days of pay stubs showing hourly rate and hours worked", "count": 2, "freshness": 30, "auto_renew": True},
                {"doc_type": DocType.W2, "title": "W-2 Forms", "description": "W-2s for the past 2 years", "count": 2},
            ],
            "W2_SALARY": [
                {"doc_type": DocType.PAYSTUB, "title": "Recent Pay Stubs", "description": "Most recent 30 days of pay stubs", "count": 2, "freshness": 30, "auto_renew": True},
                {"doc_type": DocType.W2, "title": "W-2 Forms", "description": "W-2s for the past 2 years", "count": 2},
            ],
            "OT_BONUS": [
                {"doc_type": DocType.PAYSTUB, "title": "YTD Pay Stubs", "description": "Pay stubs showing year-to-date overtime/bonus", "count": 2, "freshness": 30, "auto_renew": True},
                {"doc_type": DocType.W2, "title": "W-2 Forms", "description": "W-2s showing overtime/bonus for past 2 years", "count": 2},
            ],
            "COMMISSION": [
                {"doc_type": DocType.PAYSTUB, "title": "Commission Pay Stubs", "description": "Pay stubs showing commission earnings YTD", "count": 2, "freshness": 30, "auto_renew": True},
                {"doc_type": DocType.W2, "title": "W-2 Forms", "description": "W-2s for the past 2 years", "count": 2},
                {"doc_type": DocType.TAX_RETURN, "title": "Tax Returns with Form 2106", "description": "Tax returns with unreimbursed employee expenses if applicable", "count": 2},
            ],
            "NONTAX_SS": [
                {"doc_type": DocType.OTHER, "title": "Social Security Award Letter", "description": "SSA-1099 or benefit verification letter showing monthly benefit amount", "count": 1},
            ],
            "NONTAX_OTHER": [
                {"doc_type": DocType.OTHER, "title": "Pension/Retirement Statement", "description": "Proof of pension, IRA, or retirement income", "count": 1},
                {"doc_type": DocType.BANK_STATEMENT, "title": "Bank Statements", "description": "Bank statements showing deposits", "count": 2, "freshness": 90},
            ],
            "BANK_PERSONAL": [
                {"doc_type": DocType.BANK_STATEMENT, "title": "Personal Bank Statements (12-24 months)", "description": "Complete personal bank statements for income qualification", "count": 12, "freshness": 90, "auto_renew": True},
            ],
            "BANK_BUSINESS": [
                {"doc_type": DocType.BANK_STATEMENT, "title": "Business Bank Statements (12-24 months)", "description": "Complete business bank statements for income qualification", "count": 12, "freshness": 90, "auto_renew": True},
                {"doc_type": DocType.OTHER, "title": "Business License", "description": "Current business license or registration", "count": 1},
            ],
            "RENTAL_SCHEDULE_E": [
                {"doc_type": DocType.TAX_RETURN, "title": "Tax Returns with Schedule E", "description": "Tax returns with Schedule E showing rental income/loss", "count": 2},
                {"doc_type": DocType.LEASE_AGREEMENT, "title": "Lease Agreements", "description": "Current signed lease agreements for rental properties", "count": 1},
            ],
            "SELF_EMPLOYMENT_1084": [
                {"doc_type": DocType.TAX_RETURN, "title": "Personal Tax Returns", "description": "Complete personal tax returns for past 2 years", "count": 2},
                {"doc_type": DocType.BUSINESS_TAX_RETURN, "title": "Business Tax Returns", "description": "Business tax returns (Schedule C, K-1, 1120/1120S) for past 2 years", "count": 2},
                {"doc_type": DocType.PROFIT_LOSS, "title": "Year-to-Date P&L", "description": "Current year profit and loss statement signed by borrower", "count": 1, "freshness": 90, "auto_renew": True},
                {"doc_type": DocType.OTHER, "title": "Business License", "description": "Current business license or registration", "count": 1},
            ],
        }

        for income_type in income_types:
            requirements = income_doc_requirements.get(income_type, [])

            for req in requirements:
                doc_type = req["doc_type"]
                # Skip if we've already added this doc type
                if doc_type in seen_doc_types:
                    continue
                seen_doc_types.add(doc_type)

                request = self._create_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    doc_type=doc_type,
                    title=req["title"],
                    description=req["description"],
                    required_count=req.get("count", 1),
                    priority=RequestPriority.HIGH,
                    freshness_days=req.get("freshness"),
                    auto_renew=req.get("auto_renew", False),
                )
                requests.append(request)

        logger.info(f"Generated {len(requests)} income-type-specific document requests for loan {loan_id}")
        return requests

    def _generate_co_borrower_requirements(
        self,
        loan_id: int,
        co_borrower_id: int,
    ) -> List[DocumentRequest]:
        """Generate requirements specific to co-borrower."""
        requests = []

        # Co-borrower needs same core documents
        requests.append(
            self._create_request(
                loan_id=loan_id,
                borrower_id=co_borrower_id,
                doc_type=DocType.DRIVERS_LICENSE,
                title="Co-Borrower ID",
                description="Government-issued ID for co-borrower",
                priority=RequestPriority.HIGH,
                applies_to=AppliesTo.CO_BORROWER,
            )
        )
        requests.append(
            self._create_request(
                loan_id=loan_id,
                borrower_id=co_borrower_id,
                doc_type=DocType.PAYSTUB,
                title="Co-Borrower Pay Stubs",
                description="Most recent 30 days of pay stubs",
                required_count=2,
                priority=RequestPriority.HIGH,
                applies_to=AppliesTo.CO_BORROWER,
                freshness_days=30,
                auto_renew=True,
            )
        )
        requests.append(
            self._create_request(
                loan_id=loan_id,
                borrower_id=co_borrower_id,
                doc_type=DocType.W2,
                title="Co-Borrower W-2s",
                description="W-2s for the past 2 years",
                required_count=2,
                priority=RequestPriority.HIGH,
                applies_to=AppliesTo.CO_BORROWER,
            )
        )

        return requests

    def _create_request(
        self,
        loan_id: int,
        borrower_id: Optional[int],
        doc_type: DocType,
        title: str,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        required_count: int = 1,
        priority: RequestPriority = RequestPriority.NORMAL,
        applies_to: AppliesTo = AppliesTo.BORROWER,
        freshness_days: Optional[int] = None,
        auto_renew: bool = False,
        due_date: Optional[datetime] = None,
    ) -> DocumentRequest:
        """Create a single document request."""
        # Use default freshness if not specified
        if freshness_days is None and doc_type in self.FRESHNESS_REQUIREMENTS:
            freshness_days = self.FRESHNESS_REQUIREMENTS[doc_type]

        # Only allow auto-renew for eligible document types
        if auto_renew and doc_type not in self.AUTO_RENEW_ELIGIBLE:
            auto_renew = False

        return DocumentRequest(
            loan_id=loan_id,
            borrower_id=borrower_id,
            doc_type=doc_type,
            title=title,
            description=description,
            instructions=instructions,
            required_count=required_count,
            applies_to=applies_to,
            priority=priority,
            freshness_days=freshness_days,
            auto_renew=auto_renew,
            status=RequestStatus.OPEN,
            due_date=due_date,
        )

    def _request_to_dict(self, request: DocumentRequest) -> Dict[str, Any]:
        """Convert request to dictionary for API response."""
        return {
            "id": request.id,
            "borrower_id": request.borrower_id,
            "doc_type": request.doc_type.value,
            "title": request.title,
            "description": request.description,
            "instructions": request.instructions,
            "required_count": request.required_count,
            "applies_to": request.applies_to.value,
            "priority": request.priority.value,
            "status": request.status.value,
            "freshness_days": request.freshness_days,
            "auto_renew": request.auto_renew,
            "due_date": request.due_date.isoformat() if request.due_date else None,
        }

    def get_needs_list(self, loan_id: int) -> Dict[str, Any]:
        """Get current needs list for a loan."""
        requests = self.db.query(DocumentRequest).filter(
            DocumentRequest.loan_id == loan_id
        ).order_by(
            DocumentRequest.priority.desc(),
            DocumentRequest.created_at
        ).all()

        # Group by status
        by_status = {
            "open": [],
            "pending_review": [],
            "accepted": [],
            "rejected": [],
            "waived": [],
        }

        for request in requests:
            status_key = request.status.value.lower()
            if status_key in by_status:
                by_status[status_key].append(self._request_to_dict(request))

        return {
            "loan_id": loan_id,
            "total_requests": len(requests),
            "open_count": len(by_status["open"]),
            "pending_review_count": len(by_status["pending_review"]),
            "accepted_count": len(by_status["accepted"]),
            "requests_by_status": by_status,
            "all_requests": [self._request_to_dict(r) for r in requests],
        }

    def add_custom_request(
        self,
        loan_id: int,
        borrower_id: int,
        title: str,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        priority: str = "NORMAL",
        due_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Add a custom document request (not from template)."""
        request = self._create_request(
            loan_id=loan_id,
            borrower_id=borrower_id,
            doc_type=DocType.OTHER,
            title=title,
            description=description,
            instructions=instructions,
            priority=RequestPriority(priority),
            due_date=due_date,
        )

        self.db.add(request)
        self.db.commit()

        logger.info(f"Added custom document request '{title}' for loan {loan_id}")

        return self._request_to_dict(request)

    def waive_request(
        self,
        request_id: int,
        reason: str,
        waived_by: str,
    ) -> Dict[str, Any]:
        """Waive a document request."""
        request = self.db.query(DocumentRequest).filter(
            DocumentRequest.id == request_id
        ).first()

        if not request:
            raise ValueError(f"Request {request_id} not found")

        request.status = RequestStatus.WAIVED
        request.updated_at = datetime.now(timezone.utc)

        # Log the waiver
        event = DocPolicyEvent(
            loan_id=request.loan_id,
            request_id=request_id,
            event_type=DocPolicyEventType.NEEDS_LIST_GENERATED,  # Could add a WAIVED event type
            payload={
                "action": "waived",
                "reason": reason,
                "waived_by": waived_by,
            }
        )
        self.db.add(event)
        self.db.commit()

        logger.info(f"Waived request {request_id} for loan {request.loan_id}")

        return self._request_to_dict(request)
