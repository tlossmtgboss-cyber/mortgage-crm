"""
Call Intelligence Orchestration

End-to-end workflow orchestration for call intelligence:
- Extraction → Lead creation → Pre-qualification → Documents → Outreach → Scheduling

Components:
    CallIntelligenceOrchestrator: Main orchestrator coordinating the full workflow
    LeadManagementService: Creates/updates leads from extracted data
    PreQualificationCalculator: Calculates loan eligibility and DTI
    DocumentChecklistService: Generates required document lists
    OutreachService: Sends automated communications
    SchedulingService: Schedules follow-up calls
"""

from .orchestrator import (
    CallIntelligenceOrchestrator,
    OrchestrationResult,
    OrchestrationConfig,
    OrchestrationStatus,
    OrchestrationStep,
    StepResult,
    create_orchestrator,
)
from .prequal_calculator import (
    PreQualificationCalculator,
    PreQualificationResult,
    QualificationStatus,
    LoanProgram,
    IncomeBreakdown,
    DebtBreakdown,
    create_prequal_calculator,
)
from .lead_service import (
    LeadManagementService,
    LeadResult,
    LeadData,
    LeadStatus,
    LeadSource,
    LeadPriority,
    create_lead_service,
)
from .document_checklist import (
    DocumentChecklistService,
    DocumentChecklist,
    DocumentRequirement,
    DocumentCategory,
    DocumentPriority,
    create_document_checklist_service,
)
from .outreach_service import (
    OutreachService,
    OutreachResult,
    OutreachRequest,
    OutreachChannel,
    OutreachType,
    OutreachStatus,
    create_outreach_service,
)
from .scheduling_service import (
    SchedulingService,
    ScheduledFollowup,
    TimeSlot,
    AppointmentType,
    AppointmentStatus,
    FollowupPriority,
    create_scheduling_service,
)

__all__ = [
    # Main orchestrator
    "CallIntelligenceOrchestrator",
    "OrchestrationResult",
    "OrchestrationConfig",
    "OrchestrationStatus",
    "OrchestrationStep",
    "StepResult",
    "create_orchestrator",
    # Lead management
    "LeadManagementService",
    "LeadResult",
    "LeadData",
    "LeadStatus",
    "LeadSource",
    "LeadPriority",
    "create_lead_service",
    # Pre-qualification
    "PreQualificationCalculator",
    "PreQualificationResult",
    "QualificationStatus",
    "LoanProgram",
    "IncomeBreakdown",
    "DebtBreakdown",
    "create_prequal_calculator",
    # Document checklist
    "DocumentChecklistService",
    "DocumentChecklist",
    "DocumentRequirement",
    "DocumentCategory",
    "DocumentPriority",
    "create_document_checklist_service",
    # Outreach
    "OutreachService",
    "OutreachResult",
    "OutreachRequest",
    "OutreachChannel",
    "OutreachType",
    "OutreachStatus",
    "create_outreach_service",
    # Scheduling
    "SchedulingService",
    "ScheduledFollowup",
    "TimeSlot",
    "AppointmentType",
    "AppointmentStatus",
    "FollowupPriority",
    "create_scheduling_service",
]
