"""
Brand Guard Agent — Domain 7 Marketing Sub-Agent

All marketing/outbound content passes through this agent before publish.
Checks tone consistency, compliance language, NMLS# presence, fair lending
language, and screens for discriminatory terms.

Uses Claude for nuanced compliance checking when rule-based analysis is
insufficient.

Usage:
    from services.marketing.brand_guard_agent import BrandGuardAgent

    agent = BrandGuardAgent()
    result = await agent.review_content(
        content="Check out our amazing rates!",
        content_type="social_post",
        org_id=1,
        db=session,
    )
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database.models.core import User, Organization
from database.models.communication import Activity
from database.enums import ActivityType

logger = logging.getLogger(__name__)

# Content types that this agent can review
SUPPORTED_CONTENT_TYPES = {
    "email",
    "sms",
    "social_post",
    "blog_post",
    "landing_page",
    "voicemail_script",
    "seminar_invite",
    "flyer",
    "video_script",
    "ad_copy",
}

# ---------------------------------------------------------------------------
# Fair lending / compliance patterns
# ---------------------------------------------------------------------------

# Terms that violate fair housing / ECOA / fair lending rules.
# These are prohibited in any marketing content.
PROHIBITED_TERMS: List[re.Pattern] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        # Protected classes — cannot reference in marketing
        r"\b(whites?[\s-]?only|no\s+(?:blacks?|hispanics?|asians?|minorities))\b",
        r"\b(christian\s+(?:community|neighborhood|families))\b",
        r"\b(no\s+children|adults?\s+only\s+community)\b",
        r"\b(able[- ]bodied\s+only)\b",
        r"\b(ideal\s+for\s+(?:young\s+)?couples?(?:\s+only)?)\b",
        # Steering language
        r"\b(perfect\s+(?:for|neighborhood\s+for)\s+(?:families|singles|retirees))\b",
        r"\b(exclusive\s+(?:community|neighborhood))\b",
        # Discriminatory lending language
        r"\b(no\s+(?:immigrants?|foreigners?|non-citizens?))\b",
        r"\b(english[\s-]?speakers?\s+only)\b",
    ]
]

# Trigger phrases: not prohibited but require mandatory disclaimers
TRIGGER_PHRASES: List[Dict[str, Any]] = [
    {
        "pattern": re.compile(r"\bguaranteed?\s+(?:approval|rate|closing)\b", re.IGNORECASE),
        "issue": "Cannot guarantee loan approval, rates, or closing — this is misleading.",
        "suggestion": "Replace with 'subject to credit approval' or 'rates may vary'.",
    },
    {
        "pattern": re.compile(r"\b(?:lowest|best)\s+rates?\b", re.IGNORECASE),
        "issue": "Superlative rate claims require substantiation under TILA/Reg Z.",
        "suggestion": "Use 'competitive rates' instead, or add date-specific APR disclosure.",
    },
    {
        "pattern": re.compile(r"\bno\s+(?:closing\s+costs?|fees?)\b", re.IGNORECASE),
        "issue": "'No closing costs' claims must disclose how costs are covered (e.g., higher rate).",
        "suggestion": "Add disclaimer: 'Closing costs may be covered by a higher interest rate.'",
    },
    {
        "pattern": re.compile(r"\bpre[- ]?approved?\b", re.IGNORECASE),
        "issue": "'Pre-approved' must clarify it is not a commitment to lend.",
        "suggestion": "Add: 'Pre-approval is not a commitment to lend. Final approval subject to underwriting.'",
    },
    {
        "pattern": re.compile(r"\bfree\b", re.IGNORECASE),
        "issue": "'Free' offers must clarify any conditions.",
        "suggestion": "Specify what is free and any conditions that apply.",
    },
    {
        "pattern": re.compile(r"\b\d+(?:\.\d+)?%\s*(?:APR|rate|interest)\b", re.IGNORECASE),
        "issue": "Specific rate quotes trigger Regulation Z disclosure requirements.",
        "suggestion": "Include APR, payment example, and 'rates subject to change' disclaimer.",
    },
]

# NMLS disclosure pattern: matches "NMLS #123456" or "NMLS ID: 123456" etc.
NMLS_PATTERN = re.compile(r"NMLS\s*#?\s*(?:ID:?\s*)?\d{4,}", re.IGNORECASE)

# Equal Housing Lender / Equal Housing Opportunity
EQUAL_HOUSING_PATTERN = re.compile(
    r"equal\s+housing\s+(?:lender|opportunity)", re.IGNORECASE
)

# Content types that REQUIRE NMLS disclosure
NMLS_REQUIRED_TYPES = {
    "email",
    "social_post",
    "blog_post",
    "landing_page",
    "flyer",
    "ad_copy",
    "seminar_invite",
}

# Content types that REQUIRE Equal Housing notice
EQUAL_HOUSING_REQUIRED_TYPES = {
    "email",
    "blog_post",
    "landing_page",
    "flyer",
    "ad_copy",
}

# Minimum content length to be meaningful (avoid false positives on fragments)
MIN_CONTENT_LENGTH = 10


class BrandGuardAgent:
    """Content compliance gatekeeper for all outbound marketing.

    Every piece of marketing content passes through this agent before
    publication. It performs rule-based checks for compliance language,
    NMLS# presence, fair lending violations, and discriminatory terms,
    and can optionally delegate nuanced checks to Claude.
    """

    def __init__(self) -> None:
        self.agent_name = "brand_guard"
        self.agent_version = "1.0"

    # ------------------------------------------------------------------
    # Primary review entry point
    # ------------------------------------------------------------------

    async def review_content(
        self,
        content: str,
        content_type: str,
        org_id: int,
        db: Session,
    ) -> Dict[str, Any]:
        """Review content for compliance, tone, and brand consistency.

        Args:
            content: The raw content text to review.
            content_type: One of SUPPORTED_CONTENT_TYPES.
            org_id: Organization ID for tenant-specific rules.
            db: SQLAlchemy session.

        Returns:
            dict with:
                approved (bool): Whether content passed all checks.
                issues (list): List of issue descriptions.
                suggestions (list): Remediation suggestions.
                compliance_score (float): 0.0 (fail) to 1.0 (perfect).
        """
        try:
            if not content or len(content.strip()) < MIN_CONTENT_LENGTH:
                return {
                    "approved": False,
                    "issues": ["Content is empty or too short to evaluate."],
                    "suggestions": ["Provide meaningful content for review."],
                    "compliance_score": 0.0,
                }

            if content_type not in SUPPORTED_CONTENT_TYPES:
                logger.warning(
                    "Unsupported content type '%s' — reviewing as generic text", content_type
                )

            issues: List[str] = []
            suggestions: List[str] = []

            # 1. Check for prohibited / discriminatory terms
            fair_lending_result = await self.check_fair_lending(content)
            if fair_lending_result.get("violations"):
                issues.extend(fair_lending_result["violations"])
                suggestions.append(
                    "Remove all discriminatory or protected-class references."
                )

            # 2. Check trigger phrases requiring disclaimers
            trigger_issues = self._check_trigger_phrases(content)
            for ti in trigger_issues:
                issues.append(ti["issue"])
                suggestions.append(ti["suggestion"])

            # 3. Check NMLS presence (for types that require it)
            if content_type in NMLS_REQUIRED_TYPES:
                has_nmls = NMLS_PATTERN.search(content) is not None
                if not has_nmls:
                    issues.append(
                        "NMLS# is missing. Federal law requires NMLS identifier in advertising."
                    )
                    suggestions.append(
                        "Add your NMLS# (e.g., 'NMLS #123456') to the content."
                    )

            # 4. Check Equal Housing notice (for types that require it)
            if content_type in EQUAL_HOUSING_REQUIRED_TYPES:
                has_equal_housing = EQUAL_HOUSING_PATTERN.search(content) is not None
                if not has_equal_housing:
                    issues.append(
                        "Equal Housing Lender/Opportunity notice is missing."
                    )
                    suggestions.append(
                        "Add 'Equal Housing Lender' or 'Equal Housing Opportunity' to the content."
                    )

            # 5. Calculate compliance score
            # Start at 1.0, deduct based on severity
            score = 1.0
            if fair_lending_result.get("violations"):
                # Discriminatory content is an automatic fail
                score = 0.0
            else:
                # Each non-critical issue reduces score
                deduction_per_issue = 0.15
                score = max(0.0, score - (len(issues) * deduction_per_issue))

            approved = len(issues) == 0

            # Log review activity
            try:
                activity = Activity(
                    organization_id=org_id,
                    type=ActivityType.NOTE,
                    content=(
                        f"BrandGuard review: {content_type} — "
                        f"{'APPROVED' if approved else f'REJECTED ({len(issues)} issues)'} "
                        f"(score: {score:.2f})"
                    ),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(activity)
                db.commit()
            except Exception as e:
                logger.exception("Failed to log review activity: %s", e)
                db.rollback()

            logger.info(
                "Content review: type=%s, org=%d, approved=%s, score=%.2f, issues=%d",
                content_type,
                org_id,
                approved,
                score,
                len(issues),
            )

            return {
                "approved": approved,
                "issues": issues,
                "suggestions": suggestions,
                "compliance_score": round(score, 2),
            }

        except Exception as e:
            logger.exception("Content review failed: %s", e)
            # Fail closed — do not approve content if review fails
            return {
                "approved": False,
                "issues": [f"Review system error: {str(e)}"],
                "suggestions": ["Retry review or escalate to compliance officer."],
                "compliance_score": 0.0,
            }

    # ------------------------------------------------------------------
    # NMLS presence check
    # ------------------------------------------------------------------

    async def check_nmls_presence(
        self,
        content: str,
        user_id: int,
        db: Session,
    ) -> bool:
        """Check whether the user's NMLS# is present in the content.

        Args:
            content: Text to search.
            user_id: User ID to look up their NMLS number.
            db: SQLAlchemy session.

        Returns:
            True if the user's specific NMLS# is found in content.
        """
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning("User %d not found for NMLS check", user_id)
                return False

            # User may have nmls_number or nmls_id
            nmls = user.nmls_number or user.nmls_id
            if not nmls:
                logger.warning(
                    "User %d has no NMLS number on file — cannot verify presence",
                    user_id,
                )
                return False

            # Strip any non-digit characters for matching
            nmls_digits = re.sub(r"\D", "", nmls)
            if not nmls_digits:
                return False

            # Check if those digits appear in the content near "NMLS"
            # Allow for variations: "NMLS #123456", "NMLS ID: 123456", etc.
            pattern = re.compile(
                rf"NMLS\s*#?\s*(?:ID:?\s*)?{re.escape(nmls_digits)}\b",
                re.IGNORECASE,
            )
            found = pattern.search(content) is not None

            if not found:
                # Also check for just the bare number (less strict)
                found = nmls_digits in content

            logger.debug(
                "NMLS check for user %d (NMLS %s): %s",
                user_id,
                nmls_digits,
                "found" if found else "missing",
            )

            return found

        except Exception as e:
            logger.exception("NMLS presence check failed for user %d: %s", user_id, e)
            return False

    # ------------------------------------------------------------------
    # Fair lending check
    # ------------------------------------------------------------------

    async def check_fair_lending(
        self,
        content: str,
    ) -> Dict[str, Any]:
        """Screen content for fair lending and fair housing violations.

        Checks for discriminatory terms, protected-class references,
        and steering language that violate ECOA, FHA, or fair lending rules.

        Args:
            content: Text to analyze.

        Returns:
            dict with:
                passed (bool): True if no violations found.
                violations (list): Descriptions of violations found.
                severity (str): 'none', 'warning', or 'critical'.
        """
        try:
            violations: List[str] = []

            for pattern in PROHIBITED_TERMS:
                matches = pattern.findall(content)
                if matches:
                    for match in matches:
                        violations.append(
                            f"Prohibited term detected: '{match}' — violates fair lending/fair housing rules."
                        )

            if violations:
                severity = "critical"
                passed = False
            else:
                severity = "none"
                passed = True

            logger.debug(
                "Fair lending check: %d violations, severity=%s",
                len(violations),
                severity,
            )

            return {
                "passed": passed,
                "violations": violations,
                "severity": severity,
            }

        except Exception as e:
            logger.exception("Fair lending check failed: %s", e)
            # Fail closed
            return {
                "passed": False,
                "violations": [f"Fair lending check error: {str(e)}"],
                "severity": "critical",
            }

    # ------------------------------------------------------------------
    # AI-assisted review (Claude integration)
    # ------------------------------------------------------------------

    async def review_with_ai(
        self,
        content: str,
        content_type: str,
        org_id: int,
        db: Session,
    ) -> Dict[str, Any]:
        """Perform AI-assisted nuanced compliance review using Claude.

        Delegates to Claude for tone analysis, contextual compliance issues
        that rule-based checks might miss, and brand voice consistency.

        Args:
            content: Text to analyze.
            content_type: Type of content.
            org_id: Organization ID.
            db: SQLAlchemy session.

        Returns:
            dict with AI analysis results merged with rule-based results.
        """
        try:
            # First run rule-based review
            rule_result = await self.review_content(content, content_type, org_id, db)

            # Build prompt for Claude
            prompt = self._build_ai_review_prompt(content, content_type)

            # Attempt AI review via the agent service
            ai_analysis: Optional[Dict[str, Any]] = None
            try:
                from services.ai_service import get_ai_response

                ai_response = await get_ai_response(
                    prompt=prompt,
                    system_message=(
                        "You are a mortgage marketing compliance reviewer. "
                        "Analyze the content for regulatory compliance, tone consistency, "
                        "and brand appropriateness. Return a JSON object with: "
                        "tone_assessment (str), additional_issues (list of str), "
                        "additional_suggestions (list of str), brand_score (float 0-1)."
                    ),
                    max_tokens=500,
                )
                if ai_response:
                    ai_analysis = {"raw_response": ai_response}
            except ImportError:
                logger.debug("AI service not available — skipping AI review")
            except Exception as e:
                logger.warning("AI review failed (non-critical): %s", e)

            # Merge results
            result = {
                "approved": rule_result["approved"],
                "issues": rule_result["issues"],
                "suggestions": rule_result["suggestions"],
                "compliance_score": rule_result["compliance_score"],
                "ai_review": ai_analysis,
            }

            return result

        except Exception as e:
            logger.exception("AI-assisted review failed: %s", e)
            # Fall back to rule-based only
            return await self.review_content(content, content_type, org_id, db)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_trigger_phrases(self, content: str) -> List[Dict[str, str]]:
        """Check content against trigger phrases that need disclaimers."""
        results: List[Dict[str, str]] = []
        for trigger in TRIGGER_PHRASES:
            if trigger["pattern"].search(content):
                results.append({
                    "issue": trigger["issue"],
                    "suggestion": trigger["suggestion"],
                })
        return results

    def _build_ai_review_prompt(self, content: str, content_type: str) -> str:
        """Build the prompt for Claude-based review."""
        return (
            f"Review this {content_type} for a mortgage loan officer:\n\n"
            f"---\n{content}\n---\n\n"
            "Check for:\n"
            "1. Regulatory compliance (TILA, RESPA, ECOA, FHA, Reg Z, MAP Rule)\n"
            "2. Tone: professional but approachable — no high-pressure sales language\n"
            "3. Accuracy: no misleading claims or unsupported promises\n"
            "4. Required disclosures present or flagged as missing\n"
            "5. Brand consistency: clear, helpful, trustworthy\n\n"
            "Return your analysis as a JSON object."
        )
