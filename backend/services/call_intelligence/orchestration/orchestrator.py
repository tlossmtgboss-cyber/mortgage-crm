"""
Call Intelligence Orchestrator

End-to-end workflow orchestration for call intelligence:
- Extraction → Lead creation → Pre-qualification → Documents → Outreach → Scheduling

This is the main entry point for processing a call transcript through
the complete intelligence pipeline.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..unified_extractor import UnifiedExtractionResult

from .prequal_calculator import (
    PreQualificationCalculator,
    PreQualificationResult,
    QualificationStatus,
)
from .lead_service import (
    LeadManagementService,
    LeadResult,
    LeadPriority,
)
from .document_checklist import (
    DocumentChecklistService,
    DocumentChecklist,
)
from .outreach_service import (
    OutreachService,
    OutreachResult,
    OutreachType,
)
from .scheduling_service import (
    SchedulingService,
    ScheduledFollowup,
    AppointmentType,
    FollowupPriority,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class OrchestrationStep(str, Enum):
    """Steps in the orchestration pipeline."""
    EXTRACTION = "extraction"
    LEAD_CREATION = "lead_creation"
    PRE_QUALIFICATION = "pre_qualification"
    DOCUMENT_CHECKLIST = "document_checklist"
    OUTREACH = "outreach"
    SCHEDULING = "scheduling"


class OrchestrationStatus(str, Enum):
    """Overall orchestration status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"  # Some steps failed
    FAILED = "failed"


@dataclass
class StepResult:
    """Result of a single orchestration step."""
    step: OrchestrationStep
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step.value,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class OrchestrationResult:
    """Complete result of orchestration pipeline."""
    call_id: str
    status: OrchestrationStatus = OrchestrationStatus.PENDING

    # Step results
    steps: Dict[OrchestrationStep, StepResult] = field(default_factory=dict)

    # Key outputs
    lead_id: Optional[str] = None
    prequal_result: Optional[PreQualificationResult] = None
    document_checklist: Optional[DocumentChecklist] = None
    outreach_results: List[OutreachResult] = field(default_factory=list)
    scheduled_followup: Optional[ScheduledFollowup] = None

    # Metadata
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_ms: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def successful_steps(self) -> int:
        return sum(1 for s in self.steps.values() if s.success)

    @property
    def failed_steps(self) -> int:
        return sum(1 for s in self.steps.values() if not s.success)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "status": self.status.value,
            "steps": {k.value: v.to_dict() for k, v in self.steps.items()},
            "lead_id": self.lead_id,
            "prequal_result": self.prequal_result.to_dict() if self.prequal_result else None,
            "document_checklist": self.document_checklist.to_dict() if self.document_checklist else None,
            "outreach_results": [o.to_dict() for o in self.outreach_results],
            "scheduled_followup": self.scheduled_followup.to_dict() if self.scheduled_followup else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_ms": self.total_duration_ms,
            "successful_steps": self.successful_steps,
            "failed_steps": self.failed_steps,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class OrchestrationConfig:
    """Configuration for orchestration behavior."""
    # Which steps to run
    run_lead_creation: bool = True
    run_pre_qualification: bool = True
    run_document_checklist: bool = True
    run_outreach: bool = True
    run_scheduling: bool = True

    # Outreach configuration
    send_welcome_email: bool = True
    send_document_request_email: bool = True
    send_prequal_results_email: bool = True

    # Scheduling configuration
    auto_schedule_followup: bool = True
    default_followup_type: AppointmentType = AppointmentType.FOLLOWUP_CALL

    # General settings
    lo_name: str = "Your Loan Officer"
    company_name: str = "Mortgage Company"
    document_upload_link: str = "https://portal.example.com/upload"

    # Error handling
    continue_on_step_failure: bool = True


class CallIntelligenceOrchestrator:
    """
    Orchestrates the end-to-end call intelligence workflow.

    Usage:
        orchestrator = CallIntelligenceOrchestrator()

        # Process extracted call data through full pipeline
        result = await orchestrator.orchestrate(
            call_id="call_123",
            extracted_data=extraction_result,
            loan_id=None,
            organization_id=1,
        )

        print(f"Lead created: {result.lead_id}")
        print(f"Pre-qual status: {result.prequal_result.status}")
        print(f"Documents needed: {result.document_checklist.total_required}")
    """

    def __init__(
        self,
        lead_service: Optional[LeadManagementService] = None,
        prequal_calculator: Optional[PreQualificationCalculator] = None,
        document_service: Optional[DocumentChecklistService] = None,
        outreach_service: Optional[OutreachService] = None,
        scheduling_service: Optional[SchedulingService] = None,
        config: Optional[OrchestrationConfig] = None,
    ):
        """
        Initialize orchestrator with services.

        Args:
            lead_service: Lead management service
            prequal_calculator: Pre-qualification calculator
            document_service: Document checklist service
            outreach_service: Outreach/communication service
            scheduling_service: Scheduling service
            config: Orchestration configuration
        """
        self.lead_service = lead_service or LeadManagementService()
        self.prequal_calculator = prequal_calculator or PreQualificationCalculator()
        self.document_service = document_service or DocumentChecklistService()
        self.outreach_service = outreach_service or OutreachService()
        self.scheduling_service = scheduling_service or SchedulingService()
        self.config = config or OrchestrationConfig()

    async def orchestrate(
        self,
        call_id: str,
        extracted_data: Dict[str, Any],
        loan_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        assigned_to: Optional[str] = None,
        config_override: Optional[OrchestrationConfig] = None,
    ) -> OrchestrationResult:
        """
        Run the complete orchestration pipeline.

        Args:
            call_id: Unique call identifier
            extracted_data: Data extracted from the call (unified extraction result)
            loan_id: Associated loan ID (if exists)
            organization_id: Organization ID
            assigned_to: User ID to assign lead/followup to
            config_override: Override default configuration

        Returns:
            OrchestrationResult with all step results
        """
        config = config_override or self.config
        result = OrchestrationResult(call_id=call_id)
        result.started_at = datetime.now(timezone.utc)
        result.status = OrchestrationStatus.IN_PROGRESS

        # Normalize extracted data format
        normalized_data = self._normalize_extracted_data(extracted_data)

        # Determine loan type and purpose for downstream steps
        intent = normalized_data.get("intent", {})
        property_info = normalized_data.get("property", {})

        loan_type = self._get_value(intent, "loan_type_preference") or "conventional"
        loan_purpose = self._get_value(intent, "loan_purpose") or "purchase"

        logger.info(f"Starting orchestration for call {call_id}")

        # Step 1: Lead Creation
        if config.run_lead_creation:
            step_result = await self._run_step(
                OrchestrationStep.LEAD_CREATION,
                self._create_lead,
                normalized_data,
                call_id,
                loan_id,
                organization_id,
                assigned_to,
            )
            result.steps[OrchestrationStep.LEAD_CREATION] = step_result

            if step_result.success and step_result.data:
                result.lead_id = step_result.data.get("lead_id")
            elif not config.continue_on_step_failure:
                result.status = OrchestrationStatus.FAILED
                result.errors.append("Lead creation failed")
                return self._finalize_result(result)

        # Step 2: Pre-Qualification
        if config.run_pre_qualification:
            step_result = await self._run_step(
                OrchestrationStep.PRE_QUALIFICATION,
                self._calculate_prequal,
                normalized_data,
            )
            result.steps[OrchestrationStep.PRE_QUALIFICATION] = step_result

            if step_result.success and step_result.data:
                result.prequal_result = step_result.data.get("prequal_result")
            elif not config.continue_on_step_failure:
                result.status = OrchestrationStatus.FAILED
                result.errors.append("Pre-qualification failed")
                return self._finalize_result(result)

        # Step 3: Document Checklist
        if config.run_document_checklist:
            step_result = await self._run_step(
                OrchestrationStep.DOCUMENT_CHECKLIST,
                self._generate_document_checklist,
                normalized_data,
                call_id,
                loan_type,
                loan_purpose,
                loan_id,
            )
            result.steps[OrchestrationStep.DOCUMENT_CHECKLIST] = step_result

            if step_result.success and step_result.data:
                result.document_checklist = step_result.data.get("checklist")
            elif not config.continue_on_step_failure:
                result.status = OrchestrationStatus.FAILED
                result.errors.append("Document checklist generation failed")
                return self._finalize_result(result)

        # Step 4: Outreach
        if config.run_outreach:
            step_result = await self._run_step(
                OrchestrationStep.OUTREACH,
                self._send_outreach,
                normalized_data,
                result,
                config,
            )
            result.steps[OrchestrationStep.OUTREACH] = step_result

            if step_result.success and step_result.data:
                result.outreach_results = step_result.data.get("outreach_results", [])

        # Step 5: Scheduling
        if config.run_scheduling and config.auto_schedule_followup:
            step_result = await self._run_step(
                OrchestrationStep.SCHEDULING,
                self._schedule_followup,
                normalized_data,
                call_id,
                config.default_followup_type,
                assigned_to,
            )
            result.steps[OrchestrationStep.SCHEDULING] = step_result

            if step_result.success and step_result.data:
                result.scheduled_followup = step_result.data.get("followup")

        # Determine final status
        result = self._finalize_result(result)

        logger.info(
            f"Orchestration completed for call {call_id}: "
            f"status={result.status.value}, "
            f"steps={result.successful_steps}/{len(result.steps)}"
        )

        return result

    async def _run_step(
        self,
        step: OrchestrationStep,
        func,
        *args,
        **kwargs,
    ) -> StepResult:
        """Run a single orchestration step with timing and error handling."""
        start_time = datetime.now(timezone.utc)

        try:
            data = await func(*args, **kwargs)
            duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            return StepResult(
                step=step,
                success=True,
                data=data,
                duration_ms=duration,
            )

        except Exception as e:
            duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            logger.exception(f"Orchestration step {step.value} failed: {e}")

            return StepResult(
                step=step,
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    async def _create_lead(
        self,
        extracted_data: Dict[str, Any],
        call_id: str,
        loan_id: Optional[int],
        organization_id: Optional[int],
        assigned_to: Optional[str],
    ) -> Dict[str, Any]:
        """Create or update lead from extracted data."""
        lead_result = await self.lead_service.create_or_update_lead(
            extracted_data=extracted_data,
            call_id=call_id,
            loan_id=loan_id,
            organization_id=organization_id,
            assigned_to=assigned_to,
        )

        return {
            "lead_id": lead_result.lead_id,
            "action": lead_result.action,
            "changes": lead_result.changes_made,
        }

    async def _calculate_prequal(
        self,
        extracted_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate pre-qualification."""
        # Map extracted data to prequal format
        prequal_data = self._map_to_prequal_format(extracted_data)

        prequal_result = self.prequal_calculator.calculate(prequal_data)

        return {
            "prequal_result": prequal_result,
            "status": prequal_result.status.value,
            "qualified_programs": [p.value for p in prequal_result.qualified_programs],
        }

    async def _generate_document_checklist(
        self,
        extracted_data: Dict[str, Any],
        call_id: str,
        loan_type: str,
        loan_purpose: str,
        loan_id: Optional[int],
    ) -> Dict[str, Any]:
        """Generate document checklist."""
        checklist = self.document_service.generate_checklist(
            extracted_data=extracted_data,
            call_id=call_id,
            loan_type=loan_type,
            loan_purpose=loan_purpose,
            loan_id=loan_id,
        )

        return {
            "checklist": checklist,
            "required_count": checklist.total_required,
            "conditional_count": checklist.total_conditional,
        }

    async def _send_outreach(
        self,
        extracted_data: Dict[str, Any],
        orchestration_result: OrchestrationResult,
        config: OrchestrationConfig,
    ) -> Dict[str, Any]:
        """Send outreach communications."""
        outreach_results = []

        # Welcome email
        if config.send_welcome_email:
            result = await self.outreach_service.send_welcome_email(
                extracted_data=extracted_data,
                lo_name=config.lo_name,
                company_name=config.company_name,
            )
            outreach_results.append(result)

        # Document request email
        if config.send_document_request_email and orchestration_result.document_checklist:
            result = await self.outreach_service.send_document_request(
                extracted_data=extracted_data,
                required_documents=orchestration_result.document_checklist.required_documents,
                lo_name=config.lo_name,
                company_name=config.company_name,
                upload_link=config.document_upload_link,
            )
            outreach_results.append(result)

        # Pre-qual results email
        if config.send_prequal_results_email and orchestration_result.prequal_result:
            if orchestration_result.prequal_result.status != QualificationStatus.INSUFFICIENT_DATA:
                result = await self.outreach_service.send_prequal_results(
                    extracted_data=extracted_data,
                    prequal_result=orchestration_result.prequal_result.to_dict(),
                    lo_name=config.lo_name,
                    company_name=config.company_name,
                )
                outreach_results.append(result)

        return {
            "outreach_results": outreach_results,
            "sent_count": sum(1 for r in outreach_results if r.success),
        }

    async def _schedule_followup(
        self,
        extracted_data: Dict[str, Any],
        call_id: str,
        appointment_type: AppointmentType,
        assigned_to: Optional[str],
    ) -> Dict[str, Any]:
        """Schedule follow-up appointment."""
        followup = await self.scheduling_service.schedule_followup(
            extracted_data=extracted_data,
            call_id=call_id,
            appointment_type=appointment_type,
            assigned_to=assigned_to,
        )

        return {
            "followup": followup,
            "followup_id": followup.followup_id,
            "scheduled_date": followup.scheduled_date.isoformat() if followup.scheduled_date else None,
        }

    def _normalize_extracted_data(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize extracted data from various formats.

        Handles both UnifiedExtractionResult format and direct dict format.
        """
        # If it's already a dict with expected structure, return as-is
        if "identity" in extracted_data or "financial" in extracted_data:
            return extracted_data

        # If it has domain attributes (UnifiedExtractionResult-like)
        normalized = {}

        # Map from UnifiedExtractionResult attribute names
        domain_mappings = [
            ("identity", "identity"),
            ("property_info", "property"),
            ("employment", "employment"),
            ("financial", "financial"),
            ("compliance", "compliance"),
            ("intent", "intent"),
        ]

        for attr, key in domain_mappings:
            if attr in extracted_data:
                # Convert ExtractedValue dicts to simple value dicts
                domain_data = extracted_data[attr]
                if isinstance(domain_data, dict):
                    normalized[key] = {
                        field: self._extract_value(value)
                        for field, value in domain_data.items()
                    }
                else:
                    normalized[key] = domain_data
            elif hasattr(extracted_data, attr):
                domain_data = getattr(extracted_data, attr)
                if isinstance(domain_data, dict):
                    normalized[key] = {
                        field: self._extract_value(value)
                        for field, value in domain_data.items()
                    }

        return normalized if normalized else extracted_data

    def _extract_value(self, value: Any) -> Any:
        """Extract value from ExtractedValue or dict."""
        if isinstance(value, dict):
            return value.get("value", value)
        if hasattr(value, "value"):
            return value.value
        return value

    def _map_to_prequal_format(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map extracted data to pre-qualification calculator format."""
        return {
            "identity": extracted_data.get("identity", {}),
            "income": extracted_data.get("financial", {}),
            "liabilities": extracted_data.get("financial", {}),
            "assets": extracted_data.get("financial", {}),
            "address": extracted_data.get("property", {}),
            "declarations": extracted_data.get("compliance", {}),
            "employment": extracted_data.get("employment", {}),
        }

    def _get_value(self, data: Dict, field: str) -> Any:
        """Get value from extraction dict."""
        if not data:
            return None

        value = data.get(field)
        if isinstance(value, dict):
            return value.get("value")
        return value

    def _finalize_result(self, result: OrchestrationResult) -> OrchestrationResult:
        """Finalize the orchestration result."""
        result.completed_at = datetime.now(timezone.utc)

        if result.started_at:
            result.total_duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )

        # Collect errors from failed steps
        for step, step_result in result.steps.items():
            if not step_result.success and step_result.error:
                result.errors.append(f"{step.value}: {step_result.error}")

        # Determine final status
        if result.failed_steps == 0:
            result.status = OrchestrationStatus.COMPLETED
        elif result.successful_steps == 0:
            result.status = OrchestrationStatus.FAILED
        else:
            result.status = OrchestrationStatus.PARTIAL

        return result


# =============================================================================
# Factory
# =============================================================================

def create_orchestrator(
    db_session=None,
    email_client=None,
    sms_client=None,
    calendar_client=None,
    config: Optional[OrchestrationConfig] = None,
) -> CallIntelligenceOrchestrator:
    """
    Create fully configured orchestrator instance.

    Args:
        db_session: Database session for persistence
        email_client: Email sending client
        sms_client: SMS sending client
        calendar_client: Calendar integration client
        config: Orchestration configuration

    Returns:
        Configured CallIntelligenceOrchestrator
    """
    return CallIntelligenceOrchestrator(
        lead_service=LeadManagementService(db_session),
        prequal_calculator=PreQualificationCalculator(),
        document_service=DocumentChecklistService(),
        outreach_service=OutreachService(email_client, sms_client),
        scheduling_service=SchedulingService(calendar_client),
        config=config,
    )
