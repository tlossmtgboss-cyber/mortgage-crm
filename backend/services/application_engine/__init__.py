"""
Application Engine

A comprehensive application audit system that:
1. Processes call transcript extractions from Call Intelligence
2. Audits 8 sections of the mortgage application (URLA)
3. Identifies missing/conflicting data
4. Generates tasks for borrowers and production assistants
5. Integrates with Guideline Intelligence for document recommendations

Usage:
    from services.application_engine import ApplicationEngineOrchestrator
    from services.application_engine.data_contracts import (
        ApplicationAuditRequest,
        CallTranscriptData,
    )

    # Initialize orchestrator
    orchestrator = ApplicationEngineOrchestrator(db_session)

    # Process call data
    call_data = CallTranscriptData(
        call_id="call_123",
        identity_extractions={"first_name": "John", "last_name": "Doe"},
        income_extractions={"salary": 8500},
    )

    request = ApplicationAuditRequest(
        loan_id=123,
        organization_id=1,
        call_data=call_data,
    )

    response = orchestrator.audit(request)

    print(f"Completion: {response.overall_completion}%")
    print(f"Tasks generated: {len(response.all_tasks)}")
"""

from .orchestrator import ApplicationEngineOrchestrator
from .data_contracts import (
    # Enums
    AuditModuleType,
    AuditStatus,
    FieldStatus,
    TaskPriority,
    TaskAssignee,
    ConfidenceLevel,

    # Data classes
    ExtractedField,
    IdentityData,
    AddressData,
    EmploymentData,
    IncomeData,
    IncomeSourceData,
    AssetsData,
    AssetData,
    LiabilitiesData,
    LiabilityData,
    REOData,
    RealEstateData,
    DeclarationData,

    # Tasks
    GeneratedTask,

    # Results
    AuditResult,

    # Request/Response
    CallTranscriptData,
    ApplicationAuditRequest,
    ApplicationAuditResponse,
)

from .base import BaseAuditModule, FieldDefinition, ValidationRule

# Module exports
from .modules import (
    IdentityAuditModule,
    AddressAuditModule,
    EmploymentAuditModule,
    IncomeAuditModule,
    AssetsAuditModule,
    LiabilitiesAuditModule,
    REOAuditModule,
    DeclarationsAuditModule,
)

__all__ = [
    # Main orchestrator
    "ApplicationEngineOrchestrator",

    # Enums
    "AuditModuleType",
    "AuditStatus",
    "FieldStatus",
    "TaskPriority",
    "TaskAssignee",
    "ConfidenceLevel",

    # Data classes
    "ExtractedField",
    "IdentityData",
    "AddressData",
    "EmploymentData",
    "IncomeData",
    "IncomeSourceData",
    "AssetsData",
    "AssetData",
    "LiabilitiesData",
    "LiabilityData",
    "REOData",
    "RealEstateData",
    "DeclarationData",

    # Tasks
    "GeneratedTask",

    # Results
    "AuditResult",

    # Request/Response
    "CallTranscriptData",
    "ApplicationAuditRequest",
    "ApplicationAuditResponse",

    # Base classes
    "BaseAuditModule",
    "FieldDefinition",
    "ValidationRule",

    # Modules
    "IdentityAuditModule",
    "AddressAuditModule",
    "EmploymentAuditModule",
    "IncomeAuditModule",
    "AssetsAuditModule",
    "LiabilitiesAuditModule",
    "REOAuditModule",
    "DeclarationsAuditModule",
]

__version__ = "1.0.0"
