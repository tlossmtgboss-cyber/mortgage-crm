"""
Compliance Monitor Call Agent

Monitors live mortgage calls for required RESPA/TRID disclosures, NMLS
identification, Equal Housing Opportunity statements, recording consent,
and rate/fee discussion compliance. Maintains a real-time checklist of
which required disclosures have been covered and which remain outstanding.

Compliance Requirements Tracked:
    - Recording consent: LO must notify borrower the call is being recorded
    - NMLS disclosure: LO must state their NMLS number
    - Equal Housing Opportunity: Must be mentioned on qualifying calls
    - Rate/fee transparency: When quoting rates/fees, required context must
      be provided (APR, loan type, assumptions)
    - RESPA anti-kickback: Flag potential RESPA violations in referral language
    - TRID timing: Remind LO of disclosure timing requirements when relevant

Returns a compliance score (0-100) and a checklist of required vs covered
disclosures, enabling both real-time alerts and post-call audit trails.

Runs in parallel with other live call agents during every active call session.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DisclosureItem:
    """A single required disclosure and its detection status."""
    name: str
    description: str
    required: bool  # Whether this is mandatory for every call
    weight: int  # 0-100 contribution to compliance score
    detected: bool = False
    detected_at: Optional[float] = None  # seconds from call start
    transcript_excerpt: str = ""


@dataclass
class ComplianceViolation:
    """A potential compliance violation flagged during the call."""
    violation_type: str
    description: str
    severity: str  # "warning" or "critical"
    transcript_excerpt: str
    timestamp: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

_RECORDING_CONSENT_PATTERN = re.compile(
    r"(this\s+call\s+(is\s+being\s+|may\s+be\s+|will\s+be\s+)?(recorded|monitored))|"
    r"(recording\s+this\s+(call|conversation))|"
    r"(for\s+quality\s+(and\s+training\s+)?purposes)|"
    r"(do\s+(you\s+)?(consent|agree)\s+to\s+(be(ing)?\s+)?record)",
    re.IGNORECASE,
)

_NMLS_PATTERN = re.compile(
    r"(nmls\s*(#|number|id)?\s*\d{4,8})|"
    r"(my\s+(nmls|license)\s+(number|id)\s+is)|"
    r"(licensed\s+(mortgage\s+)?loan\s+o(fficer|riginator))",
    re.IGNORECASE,
)

_EQUAL_HOUSING_PATTERN = re.compile(
    r"(equal\s+housing\s+(opportunity|lender))|"
    r"(fair\s+housing\s+act)|"
    r"(regardless\s+of\s+(race|color|religion|national\s+origin|sex|familial\s+status|disability))",
    re.IGNORECASE,
)

_RATE_QUOTE_PATTERN = re.compile(
    r"(\d+\.?\d*\s*%?\s*(interest\s+)?rate)|"
    r"(rate\s+(of|is|would\s+be)\s+\d)|"
    r"(apr\s+(is|of|would\s+be)\s+\d)|"
    r"(lock(ed)?\s+(at|in)\s+\d)",
    re.IGNORECASE,
)

_APR_DISCLOSURE_PATTERN = re.compile(
    r"(apr|annual\s+percentage\s+rate)\s+(is|of|would\s+be)\s+\d",
    re.IGNORECASE,
)

_RESPA_VIOLATION_PATTERN = re.compile(
    r"(we'?ll\s+(give|pay|send)\s+(you\s+)?(a\s+)?referral\s+(fee|bonus))|"
    r"(kickback|referral\s+fee\s+for\s+sending)|"
    r"(if\s+you\s+(refer|send)\s+(me|us)\s+.*(pay|compensat|reward))",
    re.IGNORECASE,
)

_TRID_TIMING_PATTERN = re.compile(
    r"(loan\s+estimate|LE)\s+(will\s+be|within\s+three|3\s+(business\s+)?days?)|"
    r"(closing\s+disclosure|CD)\s+(at\s+least\s+three|3\s+(business\s+)?days?\s+before)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ComplianceMonitorCallAgent:
    """Real-time compliance monitor for live mortgage calls.

    Tracks required RESPA/TRID disclosures, NMLS identification, recording
    consent, and rate/fee discussion compliance. Returns a checklist and
    compliance score (0-100).

    Usage:
        agent = ComplianceMonitorCallAgent(db=session)
        result = await agent.process(transcript_chunk, call_context)
    """

    def __init__(self, db: Session = None):
        self.db = db
        self._call_id: Optional[str] = None
        self._violations: List[ComplianceViolation] = []
        self._rate_quoted: bool = False
        self._apr_disclosed: bool = False

        # Initialise the disclosure checklist
        self._checklist: Dict[str, DisclosureItem] = {
            "recording_consent": DisclosureItem(
                name="Recording Consent",
                description="Borrower informed that call is being recorded",
                required=True,
                weight=25,
            ),
            "nmls_disclosure": DisclosureItem(
                name="NMLS Disclosure",
                description="LO stated NMLS number or licensing",
                required=True,
                weight=20,
            ),
            "equal_housing": DisclosureItem(
                name="Equal Housing Opportunity",
                description="Equal Housing Opportunity statement made",
                required=False,  # Required on certain call types
                weight=15,
            ),
            "rate_fee_transparency": DisclosureItem(
                name="Rate/Fee Transparency",
                description="APR disclosed when rate was quoted",
                required=False,  # Only required when rate is discussed
                weight=20,
            ),
            "trid_timing": DisclosureItem(
                name="TRID Timing Disclosure",
                description="LE/CD delivery timing requirements mentioned",
                required=False,  # Only required when discussing estimates
                weight=10,
            ),
            "respa_clean": DisclosureItem(
                name="RESPA Anti-Kickback Clean",
                description="No prohibited referral-fee language detected",
                required=True,
                weight=10,
                detected=True,  # Clean until proven otherwise
            ),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, transcript_chunk: str, call_context: dict) -> dict:
        """Scan a transcript chunk for compliance disclosures and violations.

        Args:
            transcript_chunk: Latest text from the transcription agent.
            call_context: Dict with call_id, elapsed_seconds, speaker, etc.

        Returns:
            Dict with checklist status, compliance_score, and any new violations.
        """
        try:
            self._call_id = call_context.get("call_id", self._call_id)
            elapsed = call_context.get("elapsed_seconds", 0.0)
            speaker = call_context.get("speaker", "unknown")
            text = transcript_chunk.strip()

            if not text:
                return self._build_response(new_violations=[])

            new_violations: List[ComplianceViolation] = []

            # --- Positive disclosure detection (primarily LO speech) ---
            if speaker in ("lo", "loan_officer", "agent", "unknown"):
                self._check_recording_consent(text, elapsed)
                self._check_nmls_disclosure(text, elapsed)
                self._check_equal_housing(text, elapsed)
                self._check_trid_timing(text, elapsed)

                # Rate quote triggers APR requirement
                if _RATE_QUOTE_PATTERN.search(text):
                    self._rate_quoted = True
                    self._checklist["rate_fee_transparency"].required = True

                if _APR_DISCLOSURE_PATTERN.search(text):
                    self._apr_disclosed = True
                    self._checklist["rate_fee_transparency"].detected = True
                    self._checklist["rate_fee_transparency"].detected_at = elapsed
                    self._checklist["rate_fee_transparency"].transcript_excerpt = text[:200]

            # --- Violation detection (any speaker) ---
            respa_match = _RESPA_VIOLATION_PATTERN.search(text)
            if respa_match:
                violation = ComplianceViolation(
                    violation_type="respa_anti_kickback",
                    description="Potential RESPA anti-kickback violation: referral fee language detected",
                    severity="critical",
                    transcript_excerpt=text[:300],
                    timestamp=elapsed,
                )
                new_violations.append(violation)
                self._violations.append(violation)
                self._checklist["respa_clean"].detected = False
                logger.warning(
                    "RESPA violation flagged at %.1fs in call %s",
                    elapsed,
                    self._call_id,
                )

            # Check for rate quoted without APR (after sufficient time)
            if (
                self._rate_quoted
                and not self._apr_disclosed
                and elapsed > 120  # Give 2 minutes after rate quote
            ):
                # Only flag once
                if not any(
                    v.violation_type == "missing_apr" for v in self._violations
                ):
                    violation = ComplianceViolation(
                        violation_type="missing_apr",
                        description="Rate was quoted but APR has not been disclosed",
                        severity="warning",
                        transcript_excerpt="(Rate quoted earlier without corresponding APR)",
                        timestamp=elapsed,
                    )
                    new_violations.append(violation)
                    self._violations.append(violation)

            return self._build_response(new_violations=new_violations)

        except Exception as e:
            logger.error(
                "ComplianceMonitorCallAgent.process failed: %s", e, exc_info=True
            )
            return {
                "agent": "compliance_monitor",
                "error": str(e),
                "call_id": self._call_id,
                "compliance_score": self._calculate_score(),
                "new_violations": [],
            }

    def get_checklist(self) -> List[dict]:
        """Return the full disclosure checklist."""
        return [
            {
                "name": item.name,
                "description": item.description,
                "required": item.required,
                "detected": item.detected,
                "detected_at": item.detected_at,
            }
            for item in self._checklist.values()
        ]

    def get_violations(self) -> List[dict]:
        """Return all flagged violations."""
        return [
            {
                "violation_type": v.violation_type,
                "description": v.description,
                "severity": v.severity,
                "transcript_excerpt": v.transcript_excerpt,
                "timestamp": v.timestamp,
            }
            for v in self._violations
        ]

    # ------------------------------------------------------------------
    # Disclosure checkers
    # ------------------------------------------------------------------

    def _check_recording_consent(self, text: str, elapsed: float) -> None:
        item = self._checklist["recording_consent"]
        if not item.detected and _RECORDING_CONSENT_PATTERN.search(text):
            item.detected = True
            item.detected_at = elapsed
            item.transcript_excerpt = text[:200]
            logger.debug("Recording consent detected at %.1fs", elapsed)

    def _check_nmls_disclosure(self, text: str, elapsed: float) -> None:
        item = self._checklist["nmls_disclosure"]
        if not item.detected and _NMLS_PATTERN.search(text):
            item.detected = True
            item.detected_at = elapsed
            item.transcript_excerpt = text[:200]
            logger.debug("NMLS disclosure detected at %.1fs", elapsed)

    def _check_equal_housing(self, text: str, elapsed: float) -> None:
        item = self._checklist["equal_housing"]
        if not item.detected and _EQUAL_HOUSING_PATTERN.search(text):
            item.detected = True
            item.detected_at = elapsed
            item.transcript_excerpt = text[:200]
            logger.debug("Equal Housing Opportunity detected at %.1fs", elapsed)

    def _check_trid_timing(self, text: str, elapsed: float) -> None:
        item = self._checklist["trid_timing"]
        if not item.detected and _TRID_TIMING_PATTERN.search(text):
            item.detected = True
            item.detected_at = elapsed
            item.transcript_excerpt = text[:200]
            logger.debug("TRID timing disclosure detected at %.1fs", elapsed)

    # ------------------------------------------------------------------
    # Score calculation
    # ------------------------------------------------------------------

    def _calculate_score(self) -> int:
        """Calculate compliance score 0-100 based on checklist weights."""
        total_weight = 0
        earned_weight = 0

        for item in self._checklist.values():
            if item.required:
                total_weight += item.weight
                if item.detected:
                    earned_weight += item.weight

        if total_weight == 0:
            return 100

        raw = (earned_weight / total_weight) * 100
        return max(0, min(100, int(round(raw))))

    # ------------------------------------------------------------------
    # Response builder
    # ------------------------------------------------------------------

    def _build_response(self, new_violations: List[ComplianceViolation]) -> dict:
        required_items = [
            i for i in self._checklist.values() if i.required
        ]
        covered = [i for i in required_items if i.detected]
        missed = [i for i in required_items if not i.detected]

        return {
            "agent": "compliance_monitor",
            "call_id": self._call_id,
            "compliance_score": self._calculate_score(),
            "checklist": {
                key: {
                    "name": item.name,
                    "required": item.required,
                    "detected": item.detected,
                    "detected_at": item.detected_at,
                }
                for key, item in self._checklist.items()
            },
            "required_covered": [i.name for i in covered],
            "required_missed": [i.name for i in missed],
            "new_violations": [
                {
                    "violation_type": v.violation_type,
                    "description": v.description,
                    "severity": v.severity,
                    "timestamp": v.timestamp,
                }
                for v in new_violations
            ],
            "total_violations": len(self._violations),
        }
