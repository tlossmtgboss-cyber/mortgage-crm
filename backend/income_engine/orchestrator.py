"""
Income Orchestrator

Master coordinator that runs all income calculation engines,
aggregates results, and produces final income summary.

Responsibilities:
1. Receive CalculationRequest with all document facts
2. Route document facts to appropriate engines
3. Aggregate income streams and flags
4. Determine approvability based on blocking flags
5. Generate worksheets and audit trails
6. Return CalculationResponse
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
import time

from .base import (
    BaseIncomeEngine,
    EngineResult,
    IncomeStream,
    IncomeFlag,
    FlagRuleId,
)
from .data_contracts import (
    CalculationRequest,
    CalculationResponse,
    IncomeStreamResult,
    CalculationFlag,
    IncomeStreamType,
    FlagSeverity,
)
from .engines import (
    W2Engine,
    ScheduleCEngine,
    RentalEngine,
    K1Engine,
    BankStatementEngine,
)

logger = logging.getLogger(__name__)


class IncomeOrchestrator:
    """
    Master orchestrator for income calculations.

    Coordinates all income engines and produces unified results.
    """

    VERSION = "1.0"
    RULESET_VERSION = "2025.1"

    def __init__(self, db_session=None):
        """
        Initialize orchestrator with all engines.

        Args:
            db_session: SQLAlchemy session for database lookups
        """
        self.db = db_session

        # Initialize all engines
        self.w2_engine = W2Engine(db_session)
        self.schedule_c_engine = ScheduleCEngine(db_session)
        self.rental_engine = RentalEngine(db_session)
        self.k1_engine = K1Engine(db_session)
        self.bank_statement_engine = BankStatementEngine(db_session)

        # Engine mapping for logging
        self._engines = {
            "W2": self.w2_engine,
            "ScheduleC": self.schedule_c_engine,
            "Rental": self.rental_engine,
            "K1": self.k1_engine,
            "BankStatement": self.bank_statement_engine,
        }

    def calculate(
        self,
        request: CalculationRequest,
    ) -> CalculationResponse:
        """
        Calculate income from all provided documents.

        Args:
            request: CalculationRequest with all document facts

        Returns:
            CalculationResponse with aggregated results
        """
        start_time = time.time()

        all_income_streams: List[IncomeStream] = []
        all_flags: List[IncomeFlag] = []
        engine_results: Dict[str, EngineResult] = {}

        try:
            # Run each engine with appropriate document facts
            engine_results = self._run_all_engines(request)

            # Aggregate results from all engines
            for engine_name, result in engine_results.items():
                if result.success:
                    all_income_streams.extend(result.income_streams)
                all_flags.extend(result.flags)

            # Calculate totals
            total_monthly = sum(s.monthly_income for s in all_income_streams)
            total_annual = total_monthly * 12

            # Count flags by severity
            blocking_count = len([f for f in all_flags if f.severity == FlagSeverity.BLOCKING])
            error_count = len([f for f in all_flags if f.severity == FlagSeverity.ERROR])
            warning_count = len([f for f in all_flags if f.severity == FlagSeverity.WARNING])
            info_count = len([f for f in all_flags if f.severity == FlagSeverity.INFO])

            # Determine approvability
            is_approvable = blocking_count == 0

            # Convert internal streams to response format
            response_streams = [
                self._stream_to_result(s) for s in all_income_streams
            ]

            # Convert internal flags to response format
            response_flags = [
                self._flag_to_response(f) for f in all_flags
            ]

            # Generate worksheets if requested
            worksheet_ids = []
            if request.generate_worksheets:
                worksheet_ids = self._generate_worksheets(
                    request, response_streams, response_flags
                )

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            return CalculationResponse(
                loan_id=request.loan_id,
                borrower_id=request.borrower_id,
                total_monthly_income=Decimal(str(total_monthly)),
                total_annual_income=Decimal(str(total_annual)),
                is_approvable=is_approvable,
                income_streams=response_streams,
                flags=response_flags,
                blocking_flags_count=blocking_count,
                error_flags_count=error_count,
                warning_flags_count=warning_count,
                info_flags_count=info_count,
                ruleset_version=self.RULESET_VERSION,
                calculated_at=datetime.now(timezone.utc),
                calculation_duration_ms=duration_ms,
                worksheet_ids=worksheet_ids,
            )

        except Exception as e:
            logger.exception(f"Orchestrator calculation error: {e}")
            duration_ms = int((time.time() - start_time) * 1000)

            return CalculationResponse(
                loan_id=request.loan_id,
                borrower_id=request.borrower_id,
                total_monthly_income=Decimal("0"),
                total_annual_income=Decimal("0"),
                is_approvable=False,
                income_streams=[],
                flags=[
                    CalculationFlag(
                        rule_id="ORCHESTRATOR_ERROR",
                        severity=FlagSeverity.BLOCKING,
                        message=f"Income calculation failed: {str(e)}",
                        required_action="Contact support or retry calculation",
                        auto_create_condition=True,
                    )
                ],
                blocking_flags_count=1,
                error_flags_count=0,
                warning_flags_count=0,
                info_flags_count=0,
                ruleset_version=self.RULESET_VERSION,
                calculated_at=datetime.now(timezone.utc),
                calculation_duration_ms=duration_ms,
            )

    def _run_all_engines(
        self,
        request: CalculationRequest,
    ) -> Dict[str, EngineResult]:
        """Run all applicable engines based on provided documents."""
        results = {}

        # W-2 / Paystub Engine
        if request.w2_facts or request.paystub_facts:
            logger.info(f"Running W2Engine with {len(request.w2_facts)} W-2s, "
                       f"{len(request.paystub_facts)} paystubs")

            # Group W-2s by employer
            employers = self._group_w2s_by_employer(request.w2_facts)

            for employer_name, w2s in employers.items():
                # Find matching paystubs
                employer_paystubs = [
                    p for p in request.paystub_facts
                    if p.employer_name.upper().strip() == employer_name.upper().strip()
                ]

                result = self.w2_engine.calculate(
                    w2_facts=w2s,
                    paystub_facts=employer_paystubs,
                    employer_name=employer_name,
                )
                results[f"W2_{employer_name}"] = result

        # Schedule C Engine
        if request.schedule_c_facts:
            logger.info(f"Running ScheduleCEngine with {len(request.schedule_c_facts)} Schedule Cs")
            result = self.schedule_c_engine.calculate(
                schedule_c_facts=request.schedule_c_facts,
            )
            results["ScheduleC"] = result

        # Rental / Schedule E Engine
        if request.schedule_e_facts:
            logger.info(f"Running RentalEngine with {len(request.schedule_e_facts)} Schedule Es")
            result = self.rental_engine.calculate(
                schedule_e_facts=request.schedule_e_facts,
            )
            results["Rental"] = result

        # K-1 Engine
        if request.k1_facts:
            logger.info(f"Running K1Engine with {len(request.k1_facts)} K-1s")
            result = self.k1_engine.calculate(
                k1_facts=request.k1_facts,
            )
            results["K1"] = result

        # Bank Statement Engine
        if request.bank_statement_facts:
            logger.info(f"Running BankStatementEngine with "
                       f"{len(request.bank_statement_facts)} bank statement sets")
            for idx, bank_facts in enumerate(request.bank_statement_facts):
                result = self.bank_statement_engine.calculate(
                    bank_statement_facts=bank_facts,
                )
                results[f"BankStatement_{idx}"] = result

        return results

    def _group_w2s_by_employer(
        self,
        w2_facts: List,
    ) -> Dict[str, List]:
        """Group W-2s by employer name."""
        employers = {}
        for w2 in w2_facts:
            employer = (w2.employer_name or "Unknown Employer").upper().strip()
            if employer not in employers:
                employers[employer] = []
            employers[employer].append(w2)
        return employers

    def _stream_to_result(self, stream: IncomeStream) -> IncomeStreamResult:
        """Convert internal IncomeStream to response IncomeStreamResult."""
        return IncomeStreamResult(
            stream_type=stream.stream_type,
            stream_name=stream.stream_name,
            monthly_income=stream.monthly_income,
            annual_income=stream.annual_income,
            calculation_inputs=stream.calculation_inputs,
            calculation_steps=stream.calculation_steps,
            add_backs=stream.add_backs,
            subtractions=stream.subtractions,
            document_ids=stream.document_ids,
            tax_years=stream.tax_years,
            trending_direction=stream.trending_direction,
            trending_percentage=stream.trending_percentage,
            year1_income=stream.year1_income,
            year2_income=stream.year2_income,
            uses_lower_year=stream.uses_lower_year,
        )

    def _flag_to_response(self, flag: IncomeFlag) -> CalculationFlag:
        """Convert internal IncomeFlag to response CalculationFlag."""
        return CalculationFlag(
            rule_id=flag.rule_id,
            severity=flag.severity,
            message=flag.message,
            required_action=flag.required_action,
            affected_stream=flag.affected_stream,
            affected_document_id=flag.affected_document_id,
            metadata=flag.metadata,
            auto_create_condition=flag.auto_create_condition,
        )

    def _generate_worksheets(
        self,
        request: CalculationRequest,
        streams: List[IncomeStreamResult],
        flags: List[CalculationFlag],
    ) -> List[int]:
        """
        Generate income worksheets and save to database.

        Returns list of generated worksheet IDs.
        """
        if not self.db:
            logger.warning("No database session available for worksheet generation")
            return []

        try:
            from models.income_engine_models import IncomeWorksheet

            worksheet_ids = []

            # Create main income summary worksheet
            summary_data = {
                "streams": [
                    {
                        "type": s.stream_type.value,
                        "name": s.stream_name,
                        "monthly": float(s.monthly_income),
                        "annual": float(s.annual_income),
                    }
                    for s in streams
                ],
                "flags": [
                    {
                        "rule_id": f.rule_id,
                        "severity": f.severity.value,
                        "message": f.message,
                    }
                    for f in flags
                ],
            }

            worksheet = IncomeWorksheet(
                loan_id=request.loan_id,
                borrower_id=request.borrower_id,
                worksheet_type="INCOME_SUMMARY",
                data=summary_data,
                generated_at=datetime.now(timezone.utc),
            )
            self.db.add(worksheet)
            self.db.flush()
            worksheet_ids.append(worksheet.id)

            # Create individual worksheets by income type
            stream_types = set(s.stream_type for s in streams)
            for stream_type in stream_types:
                type_streams = [s for s in streams if s.stream_type == stream_type]

                type_data = {
                    "streams": [
                        {
                            "name": s.stream_name,
                            "monthly": float(s.monthly_income),
                            "steps": s.calculation_steps,
                            "add_backs": {k: float(v) for k, v in s.add_backs.items()},
                        }
                        for s in type_streams
                    ],
                }

                worksheet = IncomeWorksheet(
                    loan_id=request.loan_id,
                    borrower_id=request.borrower_id,
                    worksheet_type=f"{stream_type.value}_DETAIL",
                    data=type_data,
                    generated_at=datetime.now(timezone.utc),
                )
                self.db.add(worksheet)
                self.db.flush()
                worksheet_ids.append(worksheet.id)

            self.db.commit()
            return worksheet_ids

        except Exception as e:
            logger.exception(f"Failed to generate worksheets: {e}")
            if self.db:
                self.db.rollback()
            return []

    def recalculate_with_override(
        self,
        request: CalculationRequest,
        override_streams: Dict[str, Decimal],
    ) -> CalculationResponse:
        """
        Recalculate with manual overrides for specific streams.

        Args:
            request: Original calculation request
            override_streams: Dict mapping stream names to override monthly amounts

        Returns:
            CalculationResponse with overrides applied
        """
        # Run normal calculation
        response = self.calculate(request)

        # Apply overrides
        for stream in response.income_streams:
            if stream.stream_name in override_streams:
                original_monthly = stream.monthly_income
                override_amount = override_streams[stream.stream_name]

                stream.monthly_income = override_amount
                stream.annual_income = override_amount * 12
                stream.calculation_inputs["manual_override"] = True
                stream.calculation_inputs["original_monthly"] = float(original_monthly)
                stream.calculation_inputs["override_monthly"] = float(override_amount)

                # Add flag noting override
                response.flags.append(
                    CalculationFlag(
                        rule_id="MANUAL_OVERRIDE_APPLIED",
                        severity=FlagSeverity.INFO,
                        message=f"Manual override applied to {stream.stream_name}: "
                               f"${float(original_monthly):,.2f} → ${float(override_amount):,.2f}",
                        affected_stream=stream.stream_name,
                        metadata={
                            "original": float(original_monthly),
                            "override": float(override_amount),
                        }
                    )
                )
                response.info_flags_count += 1

        # Recalculate totals
        response.total_monthly_income = sum(s.monthly_income for s in response.income_streams)
        response.total_annual_income = response.total_monthly_income * 12

        return response

    def validate_documents(
        self,
        request: CalculationRequest,
    ) -> Dict[str, Any]:
        """
        Validate that provided documents are sufficient for calculation.

        Returns validation result with missing documents and recommendations.
        """
        validation = {
            "is_valid": True,
            "has_income_documents": False,
            "document_summary": {},
            "warnings": [],
            "recommendations": [],
        }

        # Check W-2/Paystub
        if request.w2_facts:
            validation["has_income_documents"] = True
            validation["document_summary"]["W2"] = {
                "count": len(request.w2_facts),
                "years": list(set(w.tax_year for w in request.w2_facts)),
            }

            # Check for 2-year history
            years = set(w.tax_year for w in request.w2_facts)
            if len(years) < 2:
                validation["warnings"].append(
                    "Only 1 year of W-2 documents. Variable income may require 2-year history."
                )

        if request.paystub_facts:
            validation["document_summary"]["Paystub"] = {
                "count": len(request.paystub_facts),
            }

        # Check Schedule C
        if request.schedule_c_facts:
            validation["has_income_documents"] = True
            validation["document_summary"]["ScheduleC"] = {
                "count": len(request.schedule_c_facts),
                "years": list(set(s.tax_year for s in request.schedule_c_facts)),
            }

            years = set(s.tax_year for s in request.schedule_c_facts)
            if len(years) < 2:
                validation["warnings"].append(
                    "Self-employment income requires 2-year history. "
                    "Only 1 year of Schedule C provided."
                )
                validation["recommendations"].append(
                    "Obtain prior year tax return with Schedule C."
                )

        # Check Schedule E
        if request.schedule_e_facts:
            validation["has_income_documents"] = True
            validation["document_summary"]["ScheduleE"] = {
                "count": len(request.schedule_e_facts),
                "years": list(set(s.tax_year for s in request.schedule_e_facts)),
            }

        # Check K-1
        if request.k1_facts:
            validation["has_income_documents"] = True
            validation["document_summary"]["K1"] = {
                "count": len(request.k1_facts),
                "years": list(set(k.tax_year for k in request.k1_facts)),
            }

        # Check Bank Statements
        if request.bank_statement_facts:
            validation["has_income_documents"] = True
            total_months = sum(b.months_of_data for b in request.bank_statement_facts)
            validation["document_summary"]["BankStatement"] = {
                "count": len(request.bank_statement_facts),
                "total_months": total_months,
            }

            if total_months < 12:
                validation["warnings"].append(
                    f"Bank statement program requires minimum 12 months. "
                    f"Only {total_months} months provided."
                )

        # Overall validation
        if not validation["has_income_documents"]:
            validation["is_valid"] = False
            validation["warnings"].append("No income documents provided.")
            validation["recommendations"].append(
                "Upload at least one income document type: W-2, paystub, "
                "tax returns (Schedule C/E/K-1), or bank statements."
            )

        return validation

    def get_supported_income_types(self) -> List[Dict[str, Any]]:
        """Return list of supported income types and their requirements."""
        return [
            {
                "type": "W2_WAGES",
                "description": "W-2 wage and salary income",
                "required_documents": ["W-2", "Recent paystubs"],
                "years_required": 2,
                "notes": "Variable income (OT, bonus, commission) requires 2-year average",
            },
            {
                "type": "SELF_EMPLOYMENT",
                "description": "Schedule C self-employment income",
                "required_documents": ["Tax returns with Schedule C"],
                "years_required": 2,
                "notes": "Add-backs for depreciation, mileage, business use of home",
            },
            {
                "type": "RENTAL",
                "description": "Schedule E rental property income",
                "required_documents": ["Tax returns with Schedule E"],
                "years_required": 2,
                "notes": "Depreciation add-back applied. Losses treated as $0",
            },
            {
                "type": "PARTNERSHIP_SCORP",
                "description": "K-1 partnership or S-Corp income",
                "required_documents": ["K-1 (Form 1065 or 1120S)"],
                "years_required": 2,
                "notes": "25%+ ownership or documented distributions required",
            },
            {
                "type": "CCORP",
                "description": "C-Corporation income",
                "required_documents": ["K-1 (Form 1120)", "W-2 from corporation"],
                "years_required": 2,
                "notes": "100% ownership required",
            },
            {
                "type": "BANK_STATEMENT",
                "description": "Bank statement program (Non-QM)",
                "required_documents": ["12-24 months bank statements"],
                "years_required": 1,
                "notes": "Expense ratio applied. Declining income may require 24 months",
            },
        ]
