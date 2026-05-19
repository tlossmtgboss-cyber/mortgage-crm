"""
Application Engine API Routes

REST API endpoints for the Application Engine and Call Intelligence services.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_async_db
from services.application_engine import (
    ApplicationEngineOrchestrator,
    ApplicationAuditRequest,
    ApplicationAuditResponse,
    CallTranscriptData,
    AuditModuleType,
)
from services.call_intelligence import (
    CallIntelligenceProcessor,
    CallIntelligenceRequest,
)

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/application-engine",
    tags=["Application Engine"],

    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# Request/Response Models
# =============================================================================

class CallDataInput(BaseModel):
    """Input model for call transcript data."""
    call_id: str = Field(..., description="Unique call identifier")
    transcript: Optional[str] = Field(None, description="Full transcript text")
    segments: Optional[List[Dict[str, Any]]] = Field(None, description="Parsed transcript segments")
    identity_extractions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    address_extractions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    employment_extractions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    income_extractions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    assets_extractions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    liabilities_extractions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    reo_extractions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    declarations_extractions: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AuditRequest(BaseModel):
    """Request model for application audit."""
    loan_id: int = Field(..., description="Loan ID to audit")
    organization_id: int = Field(..., description="Organization ID")
    call_data: Optional[CallDataInput] = Field(None, description="Call transcript data")
    existing_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    modules_to_run: Optional[List[str]] = Field(None, description="Specific modules to run (all if not specified)")
    generate_tasks: bool = Field(True, description="Generate tasks for missing data")
    include_guideline_recommendations: bool = Field(True, description="Include document recommendations")
    loan_type: Optional[str] = Field(None, description="Loan type (CONVENTIONAL, FHA, VA, etc.)")
    property_type: Optional[str] = Field(None, description="Property type")


class ProcessTranscriptRequest(BaseModel):
    """Request model for processing a call transcript."""
    call_id: str = Field(..., description="Unique call identifier")
    loan_id: Optional[int] = Field(None, description="Associated loan ID")
    organization_id: Optional[int] = Field(None, description="Organization ID")
    transcript: str = Field(..., description="Full transcript text")
    call_type: str = Field("initial_intake", description="Type of call")
    existing_borrower_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ModuleResultResponse(BaseModel):
    """Response model for a single module result."""
    module: str
    status: str
    completion_percentage: float
    fields_total: int
    fields_complete: int
    fields_missing: int
    fields_conflicting: int
    tasks_count: int
    issues: List[str]
    warnings: List[str]


class AuditResponse(BaseModel):
    """Response model for application audit."""
    loan_id: int
    overall_status: str
    overall_completion: float
    module_results: Dict[str, ModuleResultResponse]
    tasks_summary: Dict[str, int]
    field_summary: Dict[str, int]
    document_recommendations: List[Dict[str, Any]]
    processed_at: str
    total_duration_ms: int


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/audit", response_model=Dict[str, Any])
async def audit_application(
    request: AuditRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Run application audit on loan data.

    Processes call transcript extractions through 8 audit modules:
    - Identity
    - Address
    - Employment
    - Income
    - Assets
    - Liabilities
    - REO (Real Estate Owned)
    - Declarations

    Returns audit results with completion status and generated tasks.
    """
    try:
        orchestrator = ApplicationEngineOrchestrator(db)

        # Convert call data if provided
        call_data = None
        if request.call_data:
            call_data = CallTranscriptData(
                call_id=request.call_data.call_id,
                identity_extractions=request.call_data.identity_extractions or {},
                address_extractions=request.call_data.address_extractions or {},
                employment_extractions=request.call_data.employment_extractions or {},
                income_extractions=request.call_data.income_extractions or {},
                assets_extractions=request.call_data.assets_extractions or {},
                liabilities_extractions=request.call_data.liabilities_extractions or {},
                reo_extractions=request.call_data.reo_extractions or {},
                declarations_extractions=request.call_data.declarations_extractions or {},
            )

        # Convert module names to enum if provided
        modules_to_run = None
        if request.modules_to_run:
            modules_to_run = [
                AuditModuleType(m) for m in request.modules_to_run
            ]

        # Create audit request
        audit_request = ApplicationAuditRequest(
            loan_id=request.loan_id,
            organization_id=request.organization_id,
            call_data=call_data,
            existing_data=request.existing_data or {},
            modules_to_run=modules_to_run or list(AuditModuleType),
            generate_tasks=request.generate_tasks,
            include_guideline_recommendations=request.include_guideline_recommendations,
            loan_type=request.loan_type,
            property_type=request.property_type,
        )

        # Run audit
        response = orchestrator.audit(audit_request)

        return response.to_dict()

    except Exception as e:
        logger.exception(f"Application audit failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/process-transcript", response_model=Dict[str, Any])
async def process_transcript(
    request: ProcessTranscriptRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Process a call transcript through Call Intelligence.

    Extracts structured data from the transcript using 6 specialized AI agents:
    - Identity Agent
    - Property Agent
    - Employment Agent
    - Financial Agent
    - Compliance Agent
    - Intent Agent

    Returns extracted data ready for Application Engine audit.
    """
    try:
        processor = CallIntelligenceProcessor(db)

        ci_request = CallIntelligenceRequest(
            call_id=request.call_id,
            loan_id=request.loan_id,
            organization_id=request.organization_id,
            transcript=request.transcript,
            existing_borrower_data=request.existing_borrower_data or {},
        )

        response = await processor.process_transcript(ci_request)

        return response.to_dict()

    except Exception as e:
        logger.exception(f"Transcript processing failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/process-and-audit", response_model=Dict[str, Any])
async def process_and_audit(
    call_id: str = Body(...),
    loan_id: int = Body(...),
    organization_id: int = Body(...),
    transcript: str = Body(...),
    call_type: str = Body("initial_intake"),
    loan_type: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Process call transcript and run application audit in one step.

    1. Processes transcript through Call Intelligence
    2. Runs Application Engine audit with extracted data
    3. Returns combined results with tasks and recommendations
    """
    try:
        # Step 1: Process transcript
        ci_processor = CallIntelligenceProcessor(db)

        ci_request = CallIntelligenceRequest(
            call_id=call_id,
            loan_id=loan_id,
            organization_id=organization_id,
            transcript=transcript,
        )

        ci_response = await ci_processor.process_transcript(ci_request)

        if not ci_response.success:
            return {
                "success": False,
                "error": "Call Intelligence processing failed",
                "errors": ci_response.errors,
            }

        # Step 2: Create call data for audit
        call_data = CallTranscriptData(
            call_id=call_id,
            call_type=call_type,
            identity_extractions=ci_response.identity_extractions,
            address_extractions=ci_response.address_extractions,
            employment_extractions=ci_response.employment_extractions,
            income_extractions=ci_response.income_extractions,
            assets_extractions=ci_response.assets_extractions,
            liabilities_extractions=ci_response.liabilities_extractions,
            reo_extractions=ci_response.reo_extractions,
            declarations_extractions=ci_response.declarations_extractions,
        )

        # Step 3: Run audit
        orchestrator = ApplicationEngineOrchestrator(db)

        audit_request = ApplicationAuditRequest(
            loan_id=loan_id,
            organization_id=organization_id,
            call_data=call_data,
            loan_type=loan_type,
            generate_tasks=True,
            include_guideline_recommendations=True,
        )

        audit_response = orchestrator.audit(audit_request)

        return {
            "success": True,
            "call_intelligence": ci_response.to_dict(),
            "application_audit": audit_response.to_dict(),
        }

    except Exception as e:
        logger.exception(f"Process and audit failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/modules")
async def get_modules():
    """Get list of available audit modules."""
    orchestrator = ApplicationEngineOrchestrator()
    return orchestrator.get_module_summary()


@router.get("/loan/{loan_id}/status")
async def get_loan_audit_status(
    loan_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """Get the latest audit status for a loan."""
    try:
        from sqlalchemy import text

        result = (await db.execute(
            text("""
                SELECT overall_status, overall_completion, total_fields,
                       complete_fields, missing_fields, tasks_generated, created_at
                FROM application_audit_logs
                WHERE loan_id = :loan_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"loan_id": loan_id}
        )).fetchone()

        if not result:
            return {
                "loan_id": loan_id,
                "has_audit": False,
                "message": "No audit found for this loan"
            }

        return {
            "loan_id": loan_id,
            "has_audit": True,
            "overall_status": result[0],
            "overall_completion": result[1],
            "total_fields": result[2],
            "complete_fields": result[3],
            "missing_fields": result[4],
            "tasks_generated": result[5],
            "last_audit_at": result[6].isoformat() if result[6] else None,
        }

    except Exception as e:
        logger.exception(f"Error fetching audit status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/module/{module_name}/audit")
async def audit_single_module(
    module_name: str,
    loan_id: int = Body(...),
    call_extractions: Dict[str, Any] = Body(default_factory=dict),
    existing_data: Dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Run audit on a single module.

    Useful for re-running specific modules after data updates.
    """
    try:
        # Validate module name
        try:
            module_type = AuditModuleType(module_name)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid module name: {module_name}. Valid modules: {[m.value for m in AuditModuleType]}"
            )

        orchestrator = ApplicationEngineOrchestrator(db)

        result = orchestrator.run_single_module(
            module_type=module_type,
            loan_id=loan_id,
            call_extractions=call_extractions,
            existing_data=existing_data,
        )

        return result.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Single module audit failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Call Intelligence Endpoints
# =============================================================================

@router.get("/call-intelligence/agents")
async def get_call_intelligence_agents():
    """Get list of available Call Intelligence extraction agents."""
    processor = CallIntelligenceProcessor()
    return processor.get_supported_agents()


@router.post("/call-intelligence/extract")
async def extract_from_transcript(
    request: ProcessTranscriptRequest,
    agents: Optional[List[str]] = Query(None, description="Specific agents to run"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Extract data from transcript using Call Intelligence.

    Optionally specify which agents to run (all if not specified).
    """
    try:
        processor = CallIntelligenceProcessor(db)

        ci_request = CallIntelligenceRequest(
            call_id=request.call_id,
            loan_id=request.loan_id,
            organization_id=request.organization_id,
            transcript=request.transcript,
            agents_to_run=agents,
            existing_borrower_data=request.existing_borrower_data or {},
        )

        response = await processor.process_transcript(ci_request)

        return response.to_dict()

    except Exception as e:
        logger.exception(f"Extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
