"""
Application Engine Orchestrator

Master coordinator that runs all audit modules,
aggregates results, and produces comprehensive application audit.

Responsibilities:
1. Receive call transcript extractions
2. Load existing application data from database
3. Route data to appropriate audit modules
4. Aggregate results and generate task lists
5. Trigger Guideline Intelligence for document recommendations
6. Return ApplicationAuditResponse
"""

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional

from .base import BaseAuditModule
from .data_contracts import (
    AuditModuleType,
    AuditStatus,
    AuditResult,
    ApplicationAuditRequest,
    ApplicationAuditResponse,
    GeneratedTask,
    TaskAssignee,
    CallTranscriptData,
)

# Import audit modules
from .modules.identity_module import IdentityAuditModule
from .modules.address_module import AddressAuditModule
from .modules.employment_module import EmploymentAuditModule
from .modules.income_module import IncomeAuditModule
from .modules.assets_module import AssetsAuditModule
from .modules.liabilities_module import LiabilitiesAuditModule
from .modules.reo_module import REOAuditModule
from .modules.declarations_module import DeclarationsAuditModule

logger = logging.getLogger(__name__)


class ApplicationEngineOrchestrator:
    """
    Master orchestrator for application audits.

    Coordinates all audit modules and produces unified results.
    """

    VERSION = "1.0"

    def __init__(self, db_session=None):
        """
        Initialize orchestrator with all audit modules.

        Args:
            db_session: SQLAlchemy session for database operations
        """
        self.db = db_session

        # Initialize all modules
        self.identity_module = IdentityAuditModule(db_session)
        self.address_module = AddressAuditModule(db_session)
        self.employment_module = EmploymentAuditModule(db_session)
        self.income_module = IncomeAuditModule(db_session)
        self.assets_module = AssetsAuditModule(db_session)
        self.liabilities_module = LiabilitiesAuditModule(db_session)
        self.reo_module = REOAuditModule(db_session)
        self.declarations_module = DeclarationsAuditModule(db_session)

        # Module mapping
        self._modules: Dict[AuditModuleType, BaseAuditModule] = {
            AuditModuleType.IDENTITY: self.identity_module,
            AuditModuleType.ADDRESS: self.address_module,
            AuditModuleType.EMPLOYMENT: self.employment_module,
            AuditModuleType.INCOME: self.income_module,
            AuditModuleType.ASSETS: self.assets_module,
            AuditModuleType.LIABILITIES: self.liabilities_module,
            AuditModuleType.REO: self.reo_module,
            AuditModuleType.DECLARATIONS: self.declarations_module,
        }

    def audit(
        self,
        request: ApplicationAuditRequest,
    ) -> ApplicationAuditResponse:
        """
        Perform complete application audit.

        Args:
            request: ApplicationAuditRequest with call data and options

        Returns:
            ApplicationAuditResponse with all module results and tasks
        """
        start_time = time.time()
        logger.info(f"Starting application audit for loan {request.loan_id}")

        try:
            # Load existing application data if not provided
            existing_data = request.existing_data
            if not existing_data and self.db:
                existing_data = self._load_existing_data(request.loan_id)

            # Prepare call extractions
            call_extractions = self._prepare_call_extractions(request.call_data)

            # Run all requested modules
            module_results: Dict[AuditModuleType, AuditResult] = {}
            all_tasks: List[GeneratedTask] = []

            for module_type in request.modules_to_run:
                if module_type not in self._modules:
                    logger.warning(f"Unknown module type: {module_type}")
                    continue

                module = self._modules[module_type]

                # Get module-specific extractions
                module_extractions = call_extractions.get(module_type.value, {})
                module_existing = existing_data.get(module_type.value, {})

                # Run audit
                result = module.audit(
                    call_extractions=module_extractions,
                    existing_data=module_existing,
                    generate_tasks=request.generate_tasks,
                    loan_id=request.loan_id,
                )

                module_results[module_type] = result
                all_tasks.extend(result.tasks)

                logger.info(
                    f"Module {module_type.value}: {result.status.value}, "
                    f"{result.completion_percentage}% complete, "
                    f"{len(result.tasks)} tasks"
                )

            # Calculate overall metrics
            total_fields = sum(r.fields_total for r in module_results.values())
            complete_fields = sum(r.fields_complete for r in module_results.values())
            missing_fields = sum(r.fields_missing for r in module_results.values())
            conflicting_fields = sum(r.fields_conflicting for r in module_results.values())

            overall_completion = (
                (complete_fields / total_fields * 100) if total_fields > 0 else 0
            )

            # Determine overall status
            overall_status = self._determine_overall_status(module_results)

            # Separate tasks by assignee
            borrower_tasks = [t for t in all_tasks if t.assignee == TaskAssignee.BORROWER]
            pa_tasks = [t for t in all_tasks if t.assignee in [TaskAssignee.PA, TaskAssignee.LO]]

            # Get document recommendations if requested
            document_recommendations = []
            if request.include_guideline_recommendations:
                document_recommendations = self._get_document_recommendations(
                    module_results=module_results,
                    loan_type=request.loan_type,
                    property_type=request.property_type,
                )

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            response = ApplicationAuditResponse(
                loan_id=request.loan_id,
                overall_status=overall_status,
                overall_completion=round(overall_completion, 1),
                module_results=module_results,
                all_tasks=all_tasks,
                borrower_tasks=borrower_tasks,
                pa_tasks=pa_tasks,
                document_recommendations=document_recommendations,
                total_fields=total_fields,
                complete_fields=complete_fields,
                missing_fields=missing_fields,
                conflicting_fields=conflicting_fields,
                total_duration_ms=duration_ms,
            )

            logger.info(
                f"Application audit complete for loan {request.loan_id}: "
                f"{overall_status.value}, {overall_completion:.1f}% complete, "
                f"{len(all_tasks)} tasks generated"
            )

            # Save audit results to database
            if self.db:
                self._save_audit_results(request.loan_id, response)

            return response

        except Exception as e:
            logger.exception(f"Application audit error for loan {request.loan_id}: {e}")
            duration_ms = int((time.time() - start_time) * 1000)

            return ApplicationAuditResponse(
                loan_id=request.loan_id,
                overall_status=AuditStatus.ERROR,
                overall_completion=0,
                total_duration_ms=duration_ms,
            )

    def audit_from_call(
        self,
        loan_id: int,
        organization_id: int,
        call_data: CallTranscriptData,
        loan_type: Optional[str] = None,
    ) -> ApplicationAuditResponse:
        """
        Convenience method to audit from call data.

        Args:
            loan_id: The loan ID
            organization_id: The organization ID
            call_data: Extracted call transcript data
            loan_type: Optional loan type for guideline recommendations

        Returns:
            ApplicationAuditResponse
        """
        request = ApplicationAuditRequest(
            loan_id=loan_id,
            organization_id=organization_id,
            call_data=call_data,
            loan_type=loan_type,
            generate_tasks=True,
            include_guideline_recommendations=True,
        )
        return self.audit(request)

    def _prepare_call_extractions(
        self,
        call_data: Optional[CallTranscriptData],
    ) -> Dict[str, Dict[str, Any]]:
        """Prepare call extractions by module."""
        if not call_data:
            return {}

        return {
            "identity": call_data.identity_extractions,
            "address": call_data.address_extractions,
            "employment": call_data.employment_extractions,
            "income": call_data.income_extractions,
            "assets": call_data.assets_extractions,
            "liabilities": call_data.liabilities_extractions,
            "reo": call_data.reo_extractions,
            "declarations": call_data.declarations_extractions,
        }

    def _load_existing_data(self, loan_id: int) -> Dict[str, Dict[str, Any]]:
        """Load existing application data from database."""
        existing = {}

        try:
            # Load borrower data
            from models import Loan, Lead, LoanBorrower

            loan = self.db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return existing

            # Load borrower information
            borrowers = self.db.query(LoanBorrower).filter(
                LoanBorrower.loan_id == loan_id
            ).all()

            # Identity data
            if borrowers:
                primary = borrowers[0] if borrowers else None
                if primary:
                    existing["identity"] = {
                        "first_name": primary.first_name,
                        "last_name": primary.last_name,
                        "email": primary.email,
                        "phone": primary.phone,
                        "ssn": primary.ssn_last4 if hasattr(primary, 'ssn_last4') else None,
                        "date_of_birth": primary.date_of_birth if hasattr(primary, 'date_of_birth') else None,
                        "citizenship_status": primary.citizenship_status if hasattr(primary, 'citizenship_status') else None,
                    }

            # Address data
            if hasattr(loan, 'property_address'):
                existing["address"] = {
                    "current_address": {
                        "street": loan.property_address,
                        "city": loan.property_city if hasattr(loan, 'property_city') else None,
                        "state": loan.property_state if hasattr(loan, 'property_state') else None,
                        "zip": loan.property_zip if hasattr(loan, 'property_zip') else None,
                    }
                }

            # Employment data
            if hasattr(loan, 'borrower_employer'):
                existing["employment"] = {
                    "current_employer": loan.borrower_employer,
                }

            # Income data
            if hasattr(loan, 'monthly_income'):
                existing["income"] = {
                    "monthly_income": float(loan.monthly_income) if loan.monthly_income else None,
                }

            # Liabilities data
            if hasattr(loan, 'total_monthly_debt'):
                existing["liabilities"] = {
                    "total_monthly_payments": float(loan.total_monthly_debt) if loan.total_monthly_debt else None,
                }

        except Exception as e:
            logger.warning(f"Error loading existing data for loan {loan_id}: {e}")

        return existing

    def _determine_overall_status(
        self,
        module_results: Dict[AuditModuleType, AuditResult],
    ) -> AuditStatus:
        """Determine overall audit status from module results."""
        if not module_results:
            return AuditStatus.ERROR

        statuses = [r.status for r in module_results.values()]

        # If any error, overall is error
        if AuditStatus.ERROR in statuses:
            return AuditStatus.ERROR

        # If any needs review, overall needs review
        if AuditStatus.NEEDS_REVIEW in statuses:
            return AuditStatus.NEEDS_REVIEW

        # If any incomplete, overall is incomplete
        if AuditStatus.INCOMPLETE in statuses:
            return AuditStatus.INCOMPLETE

        return AuditStatus.COMPLETE

    def _get_document_recommendations(
        self,
        module_results: Dict[AuditModuleType, AuditResult],
        loan_type: Optional[str],
        property_type: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Get document recommendations from Guideline Intelligence."""
        recommendations = []

        try:
            # Build document requirements based on extracted data
            # This integrates with the Guideline Intelligence Service

            # Income-based recommendations
            income_result = module_results.get(AuditModuleType.INCOME)
            if income_result and income_result.data:
                income_data = income_result.data

                # Check for self-employment
                for source in getattr(income_data, 'income_sources', []):
                    if getattr(source, 'income_type', '') == 'SELF_EMPLOYMENT':
                        recommendations.append({
                            "category": "income",
                            "document_type": "TAX_RETURNS",
                            "description": "2 years of personal and business tax returns required for self-employment income",
                            "priority": "high",
                            "years_required": 2,
                        })
                        recommendations.append({
                            "category": "income",
                            "document_type": "PROFIT_LOSS",
                            "description": "Year-to-date profit and loss statement",
                            "priority": "medium",
                        })

            # Employment-based recommendations
            employment_result = module_results.get(AuditModuleType.EMPLOYMENT)
            if employment_result and employment_result.status != AuditStatus.COMPLETE:
                recommendations.append({
                    "category": "employment",
                    "document_type": "VOE",
                    "description": "Verification of Employment (VOE) or recent paystubs",
                    "priority": "high",
                })

            # Asset-based recommendations
            assets_result = module_results.get(AuditModuleType.ASSETS)
            if assets_result:
                recommendations.append({
                    "category": "assets",
                    "document_type": "BANK_STATEMENTS",
                    "description": "2 months of bank statements for all accounts",
                    "priority": "high",
                    "months_required": 2,
                })

            # Loan type specific
            if loan_type == "FHA":
                recommendations.append({
                    "category": "loan_type",
                    "document_type": "CAIVRS",
                    "description": "CAIVRS clearance required for FHA loans",
                    "priority": "medium",
                })
            elif loan_type == "VA":
                recommendations.append({
                    "category": "loan_type",
                    "document_type": "COE",
                    "description": "Certificate of Eligibility required for VA loans",
                    "priority": "high",
                })

        except Exception as e:
            logger.warning(f"Error generating document recommendations: {e}")

        return recommendations

    def _save_audit_results(
        self,
        loan_id: int,
        response: ApplicationAuditResponse,
    ) -> None:
        """Save audit results to database."""
        try:
            # Create audit log entry
            from sqlalchemy import text

            self.db.execute(
                text("""
                    INSERT INTO application_audit_logs
                    (loan_id, overall_status, overall_completion, total_fields,
                     complete_fields, missing_fields, tasks_generated, created_at)
                    VALUES
                    (:loan_id, :status, :completion, :total, :complete, :missing, :tasks, :created_at)
                """),
                {
                    "loan_id": loan_id,
                    "status": response.overall_status.value,
                    "completion": response.overall_completion,
                    "total": response.total_fields,
                    "complete": response.complete_fields,
                    "missing": response.missing_fields,
                    "tasks": len(response.all_tasks),
                    "created_at": datetime.utcnow(),
                }
            )
            self.db.commit()

        except Exception as e:
            logger.warning(f"Error saving audit results: {e}")
            # Don't fail the audit if logging fails
            try:
                self.db.rollback()
            except Exception:
                pass

    def get_module_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all available modules."""
        return [
            {
                "module": AuditModuleType.IDENTITY.value,
                "name": "Identity Verification",
                "description": "Collects and verifies borrower identity information including name, SSN, DOB, contact info",
                "urla_sections": ["Section 1a"],
            },
            {
                "module": AuditModuleType.ADDRESS.value,
                "name": "Address History",
                "description": "Collects current and previous addresses with residency details",
                "urla_sections": ["Section 1b"],
            },
            {
                "module": AuditModuleType.EMPLOYMENT.value,
                "name": "Employment History",
                "description": "Collects current and previous employment information",
                "urla_sections": ["Section 1c"],
            },
            {
                "module": AuditModuleType.INCOME.value,
                "name": "Income Analysis",
                "description": "Identifies and categorizes all income sources",
                "urla_sections": ["Section 1d"],
            },
            {
                "module": AuditModuleType.ASSETS.value,
                "name": "Assets & Accounts",
                "description": "Collects bank accounts, investments, and other assets",
                "urla_sections": ["Section 2a"],
            },
            {
                "module": AuditModuleType.LIABILITIES.value,
                "name": "Liabilities & Debts",
                "description": "Identifies all liabilities and monthly obligations",
                "urla_sections": ["Section 2b"],
            },
            {
                "module": AuditModuleType.REO.value,
                "name": "Real Estate Owned",
                "description": "Documents all real estate properties owned",
                "urla_sections": ["Section 2c"],
            },
            {
                "module": AuditModuleType.DECLARATIONS.value,
                "name": "Declarations",
                "description": "Collects URLA declaration responses",
                "urla_sections": ["Sections J, K"],
            },
        ]

    def run_single_module(
        self,
        module_type: AuditModuleType,
        loan_id: int,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any] = None,
    ) -> AuditResult:
        """
        Run a single audit module.

        Useful for re-running specific modules after data updates.
        """
        if module_type not in self._modules:
            raise ValueError(f"Unknown module type: {module_type}")

        module = self._modules[module_type]

        return module.audit(
            call_extractions=call_extractions,
            existing_data=existing_data or {},
            generate_tasks=True,
            loan_id=loan_id,
        )
