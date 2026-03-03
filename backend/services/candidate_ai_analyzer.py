"""
Candidate AI Analyzer Service
Uses Claude AI to analyze candidate data and generate assessment scores.

Features:
- Resume analysis for production history and skills
- Social media profile analysis
- Interview notes analysis
- DISC personality inference
- Strengths/weaknesses identification
- Score suggestions with confidence levels
"""

import os
import re
import json
import hashlib
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from anthropic import Anthropic
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@dataclass
class DISCInference:
    """DISC personality inference results."""
    d_score: int  # 0-100
    i_score: int
    s_score: int
    c_score: int
    primary_style: str  # D, I, S, or C
    secondary_style: str
    confidence: float  # 0-1
    reasoning: str


@dataclass
class ScoreSuggestion:
    """AI-suggested score for a category."""
    category: str
    suggested_score: float
    confidence: float  # 0-1
    reasoning: str
    evidence: List[str] = field(default_factory=list)


@dataclass
class StrengthWeakness:
    """Identified strength or weakness."""
    trait: str
    category: str  # production, personality, character, skills, culture
    is_strength: bool
    evidence: str
    impact_level: str  # high, medium, low


@dataclass
class AIAnalysisResult:
    """Complete AI analysis result."""
    candidate_id: int
    analyzed_at: datetime
    confidence_score: float  # Overall confidence 0-100

    # Score suggestions
    production_suggestion: Optional[ScoreSuggestion] = None
    disc_inference: Optional[DISCInference] = None
    character_suggestion: Optional[ScoreSuggestion] = None
    skills_suggestion: Optional[ScoreSuggestion] = None
    culture_fit_suggestion: Optional[ScoreSuggestion] = None

    # Insights
    strengths: List[StrengthWeakness] = field(default_factory=list)
    weaknesses: List[StrengthWeakness] = field(default_factory=list)

    # Recommendation
    hire_recommendation: str = "maybe"  # strong_hire, hire, maybe, no_hire, strong_no_hire
    recommendation_reasoning: str = ""

    # Red flags and highlights
    red_flags: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)

    # Raw data for debugging
    raw_analysis: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['analyzed_at'] = self.analyzed_at.isoformat()
        return result


class CandidateAIAnalyzer:
    """
    AI-powered candidate analysis service.

    Uses Claude to analyze candidate data and generate:
    - Score suggestions for each category
    - DISC personality inference
    - Strengths and weaknesses
    - Hire recommendation
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-20250514"

    async def analyze_candidate(
        self,
        candidate_id: int,
        include_resume: bool = True,
        include_social: bool = True,
        include_interviews: bool = True,
        include_notes: bool = True,
        triggered_by: Optional[int] = None,
        organization_id: Optional[int] = None
    ) -> AIAnalysisResult:
        """
        Run comprehensive AI analysis on a candidate.

        Gathers all available data and uses Claude to analyze and score.
        """
        # Gather candidate data
        candidate_data = await self._gather_candidate_data(
            candidate_id,
            include_resume,
            include_social,
            include_interviews,
            include_notes
        )

        # Run analysis
        analysis = await self._run_analysis(candidate_id, candidate_data)

        # Reset transaction state before storing (in case earlier queries had issues)
        try:
            self.db.rollback()
        except Exception as e:
            logger.exception(f"Failed to rollback transaction before storing analysis for candidate {candidate_id}: {e}")

        # Store results in database
        await self._store_analysis(candidate_id, analysis)

        # Log AI audit trail
        if triggered_by and organization_id:
            self._log_ai_audit(
                candidate_id=candidate_id,
                organization_id=organization_id,
                triggered_by=triggered_by,
                analysis=analysis,
            )

        return analysis

    async def _gather_candidate_data(
        self,
        candidate_id: int,
        include_resume: bool,
        include_social: bool,
        include_interviews: bool,
        include_notes: bool
    ) -> Dict[str, Any]:
        """Gather all available candidate data for analysis."""
        from sqlalchemy import text

        data = {"candidate_id": candidate_id}

        # Get basic candidate info - use simple query without JOINs to avoid table existence issues
        try:
            candidate = self.db.execute(text("""
                SELECT
                    c.id, c.first_name, c.last_name, c.email, c.phone,
                    c.source, c.status, c.target_role_name, c.applied_at,
                    c.resume_url, c.linkedin_url,
                    c.years_mortgage_experience, c.years_experience,
                    c.talent_profile, c.previous_companies,
                    c.interview_notes, c.recruiter_notes, c.hiring_manager_notes,
                    c.overall_score, c.vetting_score, c.behavioral_score,
                    c.technical_score, c.culture_fit_score
                FROM mm_candidates c
                WHERE c.id = :candidate_id
            """), {"candidate_id": candidate_id}).fetchone()
        except SQLAlchemyError as e:
            # If query fails, try to rollback and re-query with minimal columns
            self.db.rollback()
            candidate = self.db.execute(text("""
                SELECT id, first_name, last_name, email, phone, status
                FROM mm_candidates
                WHERE id = :candidate_id
            """), {"candidate_id": candidate_id}).fetchone()

        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")

        # Use getattr with defaults for optional columns
        data["basic_info"] = {
            "name": f"{candidate.first_name} {candidate.last_name}",
            "email": candidate.email,
            "phone": candidate.phone,
            "source": getattr(candidate, 'source', None),
            "status": candidate.status,
            "target_role": getattr(candidate, 'target_role_name', None),
            "applied_at": str(getattr(candidate, 'applied_at', None)) if getattr(candidate, 'applied_at', None) else None
        }

        # Extract production data from talent_profile JSONB if available
        talent_profile = getattr(candidate, 'talent_profile', None) or {}
        data["production"] = {
            "annual_volume": talent_profile.get("annual_volume") if isinstance(talent_profile, dict) else None,
            "annual_units": talent_profile.get("annual_units") if isinstance(talent_profile, dict) else None,
            "nmls_id": talent_profile.get("nmls_id") if isinstance(talent_profile, dict) else None,
            "current_company": talent_profile.get("current_company") if isinstance(talent_profile, dict) else None,
            "current_title": talent_profile.get("current_title") if isinstance(talent_profile, dict) else None,
            "years_mortgage": getattr(candidate, 'years_mortgage_experience', None),
            "years_total": getattr(candidate, 'years_experience', None),
            "previous_companies": getattr(candidate, 'previous_companies', None)
        }

        # Current scores for reference
        data["current_scores"] = {
            "overall": getattr(candidate, 'overall_score', None),
            "vetting": getattr(candidate, 'vetting_score', None),
            "behavioral": getattr(candidate, 'behavioral_score', None),
            "technical": getattr(candidate, 'technical_score', None),
            "culture_fit": getattr(candidate, 'culture_fit_score', None)
        }

        resume_url = getattr(candidate, 'resume_url', None)
        if include_resume and resume_url:
            data["resume_url"] = resume_url
            # Note: We don't have resume text stored, only URL

        if include_social:
            data["social_media"] = {
                "linkedin_url": getattr(candidate, 'linkedin_url', None)
            }

            # Try to get social media activity if the table exists
            try:
                social_activity = self.db.execute(text("""
                    SELECT platform, content, posted_at, engagement_data
                    FROM mm_candidate_social_posts
                    WHERE candidate_id = :candidate_id
                    ORDER BY posted_at DESC
                    LIMIT 20
                """), {"candidate_id": candidate_id}).fetchall()

                if social_activity:
                    data["social_posts"] = [
                        {
                            "platform": post.platform,
                            "content": post.content,
                            "posted_at": str(post.posted_at),
                            "engagement": post.engagement_data
                        }
                        for post in social_activity
                    ]
            except Exception as e:
                logger.exception(f"Failed to query social media posts for candidate {candidate_id}: {e}")

        if include_interviews:
            # Try mm_interviews table first
            try:
                interviews = self.db.execute(text("""
                    SELECT
                        round, interview_type, status, scheduled_at,
                        interviewer_notes, score, feedback
                    FROM mm_interviews
                    WHERE candidate_id = :candidate_id
                    ORDER BY round ASC
                """), {"candidate_id": candidate_id}).fetchall()

                if interviews:
                    data["interviews"] = [
                        {
                            "round": i.round,
                            "type": i.interview_type,
                            "status": i.status,
                            "date": str(i.scheduled_at) if i.scheduled_at else None,
                            "notes": i.interviewer_notes,
                            "score": i.score,
                            "feedback": i.feedback
                        }
                        for i in interviews
                    ]
            except Exception as e:
                logger.exception(f"Failed to query interviews for candidate {candidate_id}: {e}")

            # Also include interview notes from candidate record
            interview_notes = getattr(candidate, 'interview_notes', None)
            if interview_notes:
                data["interview_notes_from_candidate"] = interview_notes

        if include_notes:
            # Include notes from candidate record itself
            notes_list = []
            recruiter_notes = getattr(candidate, 'recruiter_notes', None)
            if recruiter_notes:
                notes_list.append({
                    "content": recruiter_notes,
                    "type": "recruiter",
                    "source": "candidate_record"
                })
            hiring_manager_notes = getattr(candidate, 'hiring_manager_notes', None)
            if hiring_manager_notes:
                notes_list.append({
                    "content": hiring_manager_notes,
                    "type": "hiring_manager",
                    "source": "candidate_record"
                })

            # Try to get notes from separate table if it exists
            try:
                notes = self.db.execute(text("""
                    SELECT content, note_type, created_at, created_by
                    FROM mm_candidate_notes
                    WHERE candidate_id = :candidate_id
                    ORDER BY created_at DESC
                """), {"candidate_id": candidate_id}).fetchall()

                if notes:
                    for n in notes:
                        notes_list.append({
                            "content": n.content,
                            "type": n.note_type,
                            "date": str(n.created_at)
                        })
            except Exception as e:
                logger.exception(f"Failed to query candidate notes for candidate {candidate_id}: {e}")

            if notes_list:
                data["notes"] = notes_list

        return data

    async def _run_analysis(
        self,
        candidate_id: int,
        candidate_data: Dict[str, Any]
    ) -> AIAnalysisResult:
        """Run Claude analysis on the gathered candidate data."""

        prompt = self._build_analysis_prompt(candidate_data)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                system=self._get_system_prompt()
            )

            # Parse the response
            response_text = response.content[0].text
            analysis_data = self._parse_analysis_response(response_text)

            # Build result object
            result = self._build_analysis_result(candidate_id, analysis_data)
            result.raw_analysis = {
                "prompt_tokens": response.usage.input_tokens,
                "response_tokens": response.usage.output_tokens,
                "model": self.model,
                "raw_response": response_text
            }

            return result

        except Exception as e:
            logger.exception(f"Error running AI analysis for candidate {candidate_id}")
            raise

    def _get_system_prompt(self) -> str:
        """Get the system prompt for candidate analysis."""
        return """You are an expert mortgage industry recruiter and HR analyst specializing in evaluating Loan Officer candidates. You have deep knowledge of:

1. PRODUCTION METRICS for Loan Officers:
   - Elite producers: $50M+ annual volume, 100+ units
   - Strong producers: $25-50M volume, 50-100 units
   - Average producers: $10-25M volume, 25-50 units
   - Entry level: <$10M volume, <25 units

2. DISC PERSONALITY ASSESSMENT for LO roles:
   - High I (Influence) is most important - relationship building, communication
   - High D (Dominance) is valuable - drive, closing ability
   - Moderate S (Steadiness) helps with process and follow-through
   - Moderate C (Conscientiousness) ensures compliance
   - Ideal LO profile: High I, High D, Moderate S, Moderate C

3. CHARACTER TRAITS to evaluate:
   - Integrity: Honesty, ethics, trustworthiness
   - Coachability: Willingness to learn, accept feedback
   - Resilience: Handle rejection, bounce back from setbacks
   - Work Ethic: Self-motivation, dedication, hustle

4. SKILLS to assess:
   - Technical: Loan products, guidelines, calculations
   - Product Knowledge: Various loan programs, rates, terms
   - Market Expertise: Local market conditions, trends
   - Technology: CRM, LOS systems, digital tools

5. CULTURE FIT considerations:
   - Values alignment with company mission
   - Team compatibility
   - Communication style
   - Growth mindset

You must respond in valid JSON format only. Be analytical, objective, and evidence-based in your assessments."""

    def _build_analysis_prompt(self, candidate_data: Dict[str, Any]) -> str:
        """Build the analysis prompt from candidate data."""

        prompt = f"""Analyze this Loan Officer candidate and provide a comprehensive assessment.

## CANDIDATE DATA

### Basic Information
{json.dumps(candidate_data.get('basic_info', {}), indent=2)}

### Production History
{json.dumps(candidate_data.get('production', {}), indent=2)}
"""

        if candidate_data.get('resume_text'):
            prompt += f"""
### Resume Content
{self._sanitize_for_prompt(candidate_data['resume_text'][:5000])}
"""

        if candidate_data.get('social_media'):
            prompt += f"""
### Social Media Profiles
{json.dumps(candidate_data.get('social_media', {}), indent=2)}
"""

        if candidate_data.get('social_posts'):
            prompt += f"""
### Recent Social Media Posts
{json.dumps(candidate_data.get('social_posts', [])[:10], indent=2)}
"""

        if candidate_data.get('interviews'):
            prompt += f"""
### Interview History
{json.dumps(candidate_data.get('interviews', []), indent=2)}
"""

        if candidate_data.get('notes'):
            sanitized_notes = []
            for note in candidate_data.get('notes', [])[:10]:
                sanitized_note = dict(note)
                if 'content' in sanitized_note:
                    sanitized_note['content'] = self._sanitize_for_prompt(sanitized_note['content'])
                sanitized_notes.append(sanitized_note)
            prompt += f"""
### Recruiter Notes
{json.dumps(sanitized_notes, indent=2)}
"""

        prompt += """

## REQUIRED ANALYSIS

Provide your analysis in the following JSON format:

```json
{
  "overall_confidence": <0-100>,

  "production_assessment": {
    "suggested_score": <0-100>,
    "confidence": <0-1>,
    "reasoning": "<explanation>",
    "evidence": ["<point1>", "<point2>"]
  },

  "disc_inference": {
    "d_score": <0-100>,
    "i_score": <0-100>,
    "s_score": <0-100>,
    "c_score": <0-100>,
    "primary_style": "<D|I|S|C>",
    "secondary_style": "<D|I|S|C>",
    "confidence": <0-1>,
    "reasoning": "<explanation>"
  },

  "character_assessment": {
    "suggested_score": <0-100>,
    "confidence": <0-1>,
    "reasoning": "<explanation>",
    "breakdown": {
      "integrity": <0-100>,
      "coachability": <0-100>,
      "resilience": <0-100>,
      "work_ethic": <0-100>
    }
  },

  "skills_assessment": {
    "suggested_score": <0-100>,
    "confidence": <0-1>,
    "reasoning": "<explanation>",
    "breakdown": {
      "technical": <0-100>,
      "product_knowledge": <0-100>,
      "market_expertise": <0-100>,
      "technology": <0-100>
    }
  },

  "culture_fit_assessment": {
    "suggested_score": <0-100>,
    "confidence": <0-1>,
    "reasoning": "<explanation>"
  },

  "strengths": [
    {
      "trait": "<strength name>",
      "category": "<production|personality|character|skills|culture>",
      "evidence": "<supporting evidence>",
      "impact_level": "<high|medium|low>"
    }
  ],

  "weaknesses": [
    {
      "trait": "<weakness name>",
      "category": "<production|personality|character|skills|culture>",
      "evidence": "<supporting evidence>",
      "impact_level": "<high|medium|low>"
    }
  ],

  "red_flags": ["<flag1>", "<flag2>"],
  "highlights": ["<highlight1>", "<highlight2>"],

  "hire_recommendation": "<strong_hire|hire|maybe|no_hire|strong_no_hire>",
  "recommendation_reasoning": "<detailed explanation>"
}
```

Be thorough but objective. Base scores only on available evidence. If data is limited, lower confidence accordingly."""

        return prompt

    @staticmethod
    def _sanitize_for_prompt(text_input: str) -> str:
        """Strip potential injection patterns from user-provided text before sending to AI."""
        if not text_input:
            return ""
        # Remove common prompt injection patterns
        sanitized = re.sub(
            r'(?i)(ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?'
            r'|you\s+are\s+now\s+(?:a|an)\s+'
            r'|system\s*:\s*'
            r'|<\/?(?:system|instruction|prompt)>)',
            '[REDACTED]',
            text_input
        )
        # Limit length to prevent token abuse
        return sanitized[:10000]

    def _log_ai_audit(
        self,
        candidate_id: int,
        organization_id: int,
        triggered_by: int,
        analysis: AIAnalysisResult,
    ) -> None:
        """Log AI analysis invocation to recruit_ai_audit_log and audit_logs."""
        from sqlalchemy import text as sql_text

        raw = analysis.raw_analysis or {}
        prompt_tokens = raw.get("prompt_tokens")
        response_tokens = raw.get("response_tokens")
        model_used = raw.get("model", self.model)

        # Compute prompt hash for reproducibility (hash of raw response is a proxy)
        raw_response = raw.get("raw_response", "")
        prompt_hash = hashlib.sha256(raw_response.encode("utf-8")).hexdigest()[:64] if raw_response else None

        try:
            self.db.execute(sql_text("""
                INSERT INTO recruit_ai_audit_log (
                    organization_id, candidate_id, triggered_by,
                    model_used, prompt_hash, prompt_tokens, response_tokens,
                    confidence_score, hire_recommendation, analysis_summary,
                    created_at
                ) VALUES (
                    :org_id, :candidate_id, :triggered_by,
                    :model_used, :prompt_hash, :prompt_tokens, :response_tokens,
                    :confidence, :recommendation, :summary,
                    CURRENT_TIMESTAMP
                )
            """), {
                "org_id": organization_id,
                "candidate_id": candidate_id,
                "triggered_by": triggered_by,
                "model_used": model_used,
                "prompt_hash": prompt_hash,
                "prompt_tokens": prompt_tokens,
                "response_tokens": response_tokens,
                "confidence": analysis.confidence_score,
                "recommendation": analysis.hire_recommendation,
                "summary": json.dumps({
                    "strengths_count": len(analysis.strengths),
                    "weaknesses_count": len(analysis.weaknesses),
                    "red_flags": analysis.red_flags,
                    "highlights": analysis.highlights,
                }),
            })

            # Also insert into generic audit_logs for cross-module visibility
            self.db.execute(sql_text("""
                INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details, created_at)
                VALUES (:user_id, 'ai_analysis_run', 'candidate', :entity_id, :details, CURRENT_TIMESTAMP)
            """), {
                "user_id": triggered_by,
                "entity_id": str(candidate_id),
                "details": json.dumps({
                    "model": model_used,
                    "confidence": analysis.confidence_score,
                    "recommendation": analysis.hire_recommendation,
                    "prompt_tokens": prompt_tokens,
                    "response_tokens": response_tokens,
                }),
            })

            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to log AI audit for candidate {candidate_id}: {e}")
            try:
                self.db.rollback()
            except Exception:
                pass

    def _parse_analysis_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the JSON response from Claude."""
        # Extract JSON from response (may be wrapped in markdown code blocks)
        import re

        # Try to find JSON in code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Assume entire response is JSON
            json_str = response_text

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.debug(f"Response text: {response_text}")
            # Return minimal valid structure
            return {
                "overall_confidence": 0,
                "error": "Internal server error",
                "raw_response": response_text
            }

    def _build_analysis_result(
        self,
        candidate_id: int,
        analysis_data: Dict[str, Any]
    ) -> AIAnalysisResult:
        """Build AIAnalysisResult from parsed analysis data."""

        result = AIAnalysisResult(
            candidate_id=candidate_id,
            analyzed_at=datetime.utcnow(),
            confidence_score=analysis_data.get("overall_confidence", 0)
        )

        # Production suggestion
        if prod := analysis_data.get("production_assessment"):
            result.production_suggestion = ScoreSuggestion(
                category="production",
                suggested_score=prod.get("suggested_score", 0),
                confidence=prod.get("confidence", 0),
                reasoning=prod.get("reasoning", ""),
                evidence=prod.get("evidence", [])
            )

        # DISC inference
        if disc := analysis_data.get("disc_inference"):
            result.disc_inference = DISCInference(
                d_score=disc.get("d_score", 50),
                i_score=disc.get("i_score", 50),
                s_score=disc.get("s_score", 50),
                c_score=disc.get("c_score", 50),
                primary_style=disc.get("primary_style", "I"),
                secondary_style=disc.get("secondary_style", "D"),
                confidence=disc.get("confidence", 0),
                reasoning=disc.get("reasoning", "")
            )

        # Character suggestion
        if char := analysis_data.get("character_assessment"):
            result.character_suggestion = ScoreSuggestion(
                category="character",
                suggested_score=char.get("suggested_score", 0),
                confidence=char.get("confidence", 0),
                reasoning=char.get("reasoning", ""),
                evidence=[]
            )

        # Skills suggestion
        if skills := analysis_data.get("skills_assessment"):
            result.skills_suggestion = ScoreSuggestion(
                category="skills",
                suggested_score=skills.get("suggested_score", 0),
                confidence=skills.get("confidence", 0),
                reasoning=skills.get("reasoning", ""),
                evidence=[]
            )

        # Culture fit suggestion
        if culture := analysis_data.get("culture_fit_assessment"):
            result.culture_fit_suggestion = ScoreSuggestion(
                category="culture_fit",
                suggested_score=culture.get("suggested_score", 0),
                confidence=culture.get("confidence", 0),
                reasoning=culture.get("reasoning", ""),
                evidence=[]
            )

        # Strengths
        for s in analysis_data.get("strengths", []):
            result.strengths.append(StrengthWeakness(
                trait=s.get("trait", ""),
                category=s.get("category", ""),
                is_strength=True,
                evidence=s.get("evidence", ""),
                impact_level=s.get("impact_level", "medium")
            ))

        # Weaknesses
        for w in analysis_data.get("weaknesses", []):
            result.weaknesses.append(StrengthWeakness(
                trait=w.get("trait", ""),
                category=w.get("category", ""),
                is_strength=False,
                evidence=w.get("evidence", ""),
                impact_level=w.get("impact_level", "medium")
            ))

        # Red flags and highlights
        result.red_flags = analysis_data.get("red_flags", [])
        result.highlights = analysis_data.get("highlights", [])

        # Recommendation
        result.hire_recommendation = analysis_data.get("hire_recommendation", "maybe")
        result.recommendation_reasoning = analysis_data.get("recommendation_reasoning", "")

        return result

    def rebuild_from_stored(
        self,
        candidate_id: int,
        raw_analysis: Dict[str, Any],
        confidence_score: float = 0
    ) -> AIAnalysisResult:
        """
        Rebuild an AIAnalysisResult from stored raw_analysis data.

        This avoids re-running the AI analysis when applying suggestions.
        """
        # The raw_analysis contains 'raw_response' which has the actual analysis JSON
        raw_response = raw_analysis.get("raw_response", "")

        # Parse the raw response
        analysis_data = self._parse_analysis_response(raw_response)

        # Build the result
        result = self._build_analysis_result(candidate_id, analysis_data)
        result.confidence_score = confidence_score or analysis_data.get("overall_confidence", 0)
        result.raw_analysis = raw_analysis

        return result

    async def _store_analysis(
        self,
        candidate_id: int,
        analysis: AIAnalysisResult
    ) -> None:
        """Store analysis results in the database."""
        from sqlalchemy import text

        # Use upsert pattern - insert if not exists, update if exists
        self.db.execute(text("""
            INSERT INTO mm_candidate_assessments (
                candidate_id,
                ai_analysis_run_at,
                ai_confidence_score,
                ai_raw_analysis,
                strengths,
                weaknesses,
                assessment_status,
                created_at,
                updated_at
            ) VALUES (
                :candidate_id,
                :analyzed_at,
                :confidence,
                :raw_analysis,
                :strengths,
                :weaknesses,
                'ai_analyzed',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (candidate_id) DO UPDATE SET
                ai_analysis_run_at = :analyzed_at,
                ai_confidence_score = :confidence,
                ai_raw_analysis = :raw_analysis,
                strengths = :strengths,
                weaknesses = :weaknesses,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "candidate_id": candidate_id,
            "analyzed_at": analysis.analyzed_at,
            "confidence": analysis.confidence_score,
            "raw_analysis": json.dumps(analysis.raw_analysis),
            "strengths": [s.trait for s in analysis.strengths],
            "weaknesses": [w.trait for w in analysis.weaknesses]
        })

        self.db.commit()

    async def apply_suggestions(
        self,
        candidate_id: int,
        analysis: AIAnalysisResult,
        apply_production: bool = True,
        apply_disc: bool = True,
        apply_character: bool = True,
        apply_skills: bool = True,
        apply_culture: bool = True,
        applied_by: int = None
    ) -> Dict[str, Any]:
        """
        Apply AI-suggested scores to the candidate's assessment.

        Optionally select which categories to apply.
        Also calculates grades and overall score.
        """
        from sqlalchemy import text
        from services.candidate_grading_service import (
            CandidateGradingService,
            WEIGHT_PRODUCTION, WEIGHT_DISC, WEIGHT_CHARACTER, WEIGHT_SKILLS, WEIGHT_CULTURE_FIT
        )

        updates = []
        params = {"candidate_id": candidate_id}

        # Track scores for overall calculation
        scores = {
            "production": None,
            "disc": None,
            "character": None,
            "skills": None,
            "culture_fit": None
        }

        if apply_production and analysis.production_suggestion:
            score = analysis.production_suggestion.suggested_score
            grade = CandidateGradingService.get_grade_from_score(score)
            updates.extend([
                "production_score = :prod_score",
                "production_grade = :prod_grade"
            ])
            params["prod_score"] = score
            params["prod_grade"] = grade
            scores["production"] = score

        if apply_disc and analysis.disc_inference:
            disc = analysis.disc_inference
            # Calculate composite using LO weights: I=40%, D=30%, S=15%, C=15%
            composite = (disc.i_score * 0.40) + (disc.d_score * 0.30) + (disc.s_score * 0.15) + (disc.c_score * 0.15)
            grade = CandidateGradingService.get_grade_from_score(composite)
            updates.extend([
                "disc_d_score = :d_score",
                "disc_i_score = :i_score",
                "disc_s_score = :s_score",
                "disc_c_score = :c_score",
                "disc_primary_style = :primary_style",
                "disc_secondary_style = :secondary_style",
                "disc_composite_score = :disc_composite",
                "disc_grade = :disc_grade",
                "disc_assessment_source = 'ai_inferred'"
            ])
            params.update({
                "d_score": disc.d_score,
                "i_score": disc.i_score,
                "s_score": disc.s_score,
                "c_score": disc.c_score,
                "primary_style": disc.primary_style,
                "secondary_style": disc.secondary_style,
                "disc_composite": composite,
                "disc_grade": grade
            })
            scores["disc"] = composite

        if apply_character and analysis.character_suggestion:
            score = analysis.character_suggestion.suggested_score
            grade = CandidateGradingService.get_grade_from_score(score)
            updates.extend([
                "character_score = :char_score",
                "character_grade = :char_grade"
            ])
            params["char_score"] = score
            params["char_grade"] = grade
            scores["character"] = score

        if apply_skills and analysis.skills_suggestion:
            score = analysis.skills_suggestion.suggested_score
            grade = CandidateGradingService.get_grade_from_score(score)
            updates.extend([
                "skills_score = :skills_score",
                "skills_grade = :skills_grade"
            ])
            params["skills_score"] = score
            params["skills_grade"] = grade
            scores["skills"] = score

        if apply_culture and analysis.culture_fit_suggestion:
            score = analysis.culture_fit_suggestion.suggested_score
            grade = CandidateGradingService.get_grade_from_score(score)
            updates.extend([
                "culture_fit_score = :culture_score",
                "culture_fit_grade = :culture_grade"
            ])
            params["culture_score"] = score
            params["culture_grade"] = grade
            scores["culture_fit"] = score

        if not updates:
            return {"applied": False, "message": "No suggestions to apply"}

        # Calculate overall score using category weights
        overall_score = (
            (scores["production"] or 0) * WEIGHT_PRODUCTION +
            (scores["disc"] or 0) * WEIGHT_DISC +
            (scores["character"] or 0) * WEIGHT_CHARACTER +
            (scores["skills"] or 0) * WEIGHT_SKILLS +
            (scores["culture_fit"] or 0) * WEIGHT_CULTURE_FIT
        )
        overall_grade = CandidateGradingService.get_grade_from_score(overall_score)

        updates.extend([
            "overall_score = :overall_score",
            "overall_grade = :overall_grade",
            "assessed_at = COALESCE(assessed_at, CURRENT_TIMESTAMP)",
            "updated_at = CURRENT_TIMESTAMP"
        ])
        params["overall_score"] = round(overall_score, 1)
        params["overall_grade"] = overall_grade

        if applied_by:
            updates.append("assessed_by = :assessed_by")
            params["assessed_by"] = applied_by

        self.db.execute(text(f"""
            UPDATE mm_candidate_assessments
            SET {', '.join(updates)}
            WHERE candidate_id = :candidate_id
        """), params)

        self.db.commit()

        return {
            "applied": True,
            "categories_updated": [
                cat for cat, apply in [
                    ("production", apply_production),
                    ("disc", apply_disc),
                    ("character", apply_character),
                    ("skills", apply_skills),
                    ("culture_fit", apply_culture)
                ] if apply
            ],
            "overall_score": round(overall_score, 1),
            "overall_grade": overall_grade
        }
