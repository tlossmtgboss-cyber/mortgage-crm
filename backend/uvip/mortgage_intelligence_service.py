"""
UVIP - Mortgage Intelligence Service
Detects mortgage-specific signals in conversations to help LOs close more loans.
"""

from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)


class MortgageIntelligenceService:
    """Detect mortgage-specific signals in conversations"""

    def __init__(self):
        # Borrower concern patterns
        self.concern_patterns = {
            "rate_anxiety": [
                r"rates?\s+(going\s+up|increasing|rising)",
                r"too\s+expensive",
                r"can'?t\s+afford",
                r"monthly\s+payment.*too\s+high",
                r"worried\s+about.*rate",
                r"scared.*rates?",
                r"rate.*going.*up",
                r"payment.*too\s+much"
            ],
            "timeline_pressure": [
                r"need\s+to\s+(close|move)\s+(quickly|fast|soon)",
                r"deadline",
                r"running\s+out\s+of\s+time",
                r"seller.*waiting",
                r"lease.*ending",
                r"time\s+sensitive",
                r"how\s+long.*take",
                r"need.*by\s+(monday|tuesday|wednesday|thursday|friday|next\s+week)"
            ],
            "confusion": [
                r"don'?t\s+understand",
                r"confused",
                r"what\s+does.*mean",
                r"can\s+you\s+explain",
                r"i'?m\s+not\s+sure",
                r"lost\s+me",
                r"wait,?\s+what",
                r"i\s+don'?t\s+get"
            ],
            "competing_offers": [
                r"other\s+lender",
                r"shopping\s+around",
                r"comparing.*rates?",
                r"got\s+another\s+(quote|offer)",
                r"someone\s+else.*offered",
                r"better\s+deal"
            ],
            "document_overwhelm": [
                r"so\s+many\s+documents?",
                r"paperwork.*overwhelming",
                r"what\s+do\s+you\s+need.*again",
                r"confused.*documents?",
                r"why\s+do\s+you\s+need.*again"
            ],
            "affordability_concern": [
                r"can\s+i\s+afford",
                r"stretch.*budget",
                r"comfortable\s+with.*payment",
                r"save.*down\s+payment",
                r"not\s+sure.*qualify"
            ],
            "trust_hesitation": [
                r"how\s+do\s+i\s+know",
                r"heard\s+bad\s+things",
                r"been\s+burned\s+before",
                r"what'?s\s+the\s+catch",
                r"hidden\s+fees?"
            ]
        }

        # Compliance risk patterns
        self.compliance_patterns = {
            "steering": [
                r"you\s+should\s+(definitely\s+)?go\s+with",
                r"i\s+recommend.*over",
                r"better\s+off\s+with",
                r"don'?t\s+do.*(?:fha|va|conventional)",
                r"stay\s+away\s+from",
                r"(?:fha|va)\s+is\s+(?:bad|worse)"
            ],
            "discrimination": [
                r"your\s+age",
                r"because\s+you'?re\s+(?:single|married|divorced)",
                r"family\s+status",
                r"where\s+you'?re\s+from",
                r"your\s+(?:race|religion|gender)",
                r"(?:maternity|pregnancy)\s+leave"
            ],
            "pressure": [
                r"need\s+to\s+decide\s+(?:now|today)",
                r"rate\s+expires?\s+(?:today|tonight|soon)",
                r"if\s+you\s+don'?t.*lose",
                r"limited\s+time\s+offer",
                r"won'?t\s+be\s+available",
                r"last\s+chance"
            ],
            "kickback_mention": [
                r"get\s+paid\s+(?:more\s+)?if",
                r"commission.*higher",
                r"bonus.*this\s+loan",
                r"make\s+more\s+(?:money|on\s+this)"
            ],
            "missing_disclosure": [
                r"don'?t\s+worry\s+about.*(?:fees|costs)",
                r"ignore\s+(?:that|those)\s+(?:numbers|fees)",
                r"doesn'?t\s+matter"
            ]
        }

        # Competitor list
        self.competitors = [
            "rocket mortgage", "quicken", "better.com", "guaranteed rate",
            "loandepot", "loan depot", "united wholesale", "uwm",
            "chase", "wells fargo", "bank of america", "boa",
            "citi", "citibank", "usaa", "navy federal",
            "pennymac", "freedom mortgage", "caliber home loans",
            "fairway", "guild mortgage", "movement mortgage",
            "crosscountry", "amerisave", "sofi"
        ]

    async def analyze_mortgage_intelligence(
        self,
        recording_id: int,
        transcript_text: str,
        transcript_segments: List[Dict],
        db: Session,
        models: Dict
    ) -> Dict:
        """Analyze transcript for mortgage-specific intelligence"""

        MortgageIntelligence = models.get('MortgageIntelligence')
        if not MortgageIntelligence:
            logger.error("MortgageIntelligence model not available")
            return {}

        intelligence = {
            "recording_id": recording_id,
            "borrower_concerns": self._detect_concerns(transcript_text, transcript_segments),
            "compliance_risks": self._detect_compliance_risks(transcript_text, transcript_segments),
            "competitor_mentions": self._detect_competitors(transcript_text, transcript_segments),
            "objections": self._extract_objections(transcript_segments),
            "explanation_effectiveness": self._assess_explanation_effectiveness(transcript_segments),
            "loan_details": self._extract_loan_details(transcript_text),
            "next_steps_clarity": self._assess_next_steps_clarity(transcript_text, transcript_segments)
        }

        # Calculate overall risk score
        risk_score = self._calculate_risk_score(intelligence)
        intelligence["overall_risk_score"] = risk_score

        # Extract priority flags
        intelligence["priority_flags"] = self._extract_priority_flags(intelligence)

        # Save to database
        intel_record = MortgageIntelligence(
            recording_id=recording_id,
            borrower_concerns=intelligence["borrower_concerns"],
            compliance_risks=intelligence["compliance_risks"],
            competitor_mentions=intelligence["competitor_mentions"],
            objections=intelligence["objections"],
            explanation_effectiveness=intelligence["explanation_effectiveness"],
            loan_details=intelligence["loan_details"],
            next_steps_clarity=intelligence["next_steps_clarity"],
            overall_risk_score=risk_score,
            priority_flags=intelligence["priority_flags"]
        )
        db.add(intel_record)
        db.commit()
        db.refresh(intel_record)

        intelligence["id"] = intel_record.id
        return intelligence

    def _detect_concerns(
        self,
        full_text: str,
        segments: List[Dict]
    ) -> List[Dict]:
        """Detect borrower concerns with timestamps"""

        concerns_found = []
        text_lower = full_text.lower()

        for concern_type, patterns in self.concern_patterns.items():
            for pattern in patterns:
                try:
                    matches = list(re.finditer(pattern, text_lower, re.IGNORECASE))

                    for match in matches:
                        segment = self._find_segment_by_position(
                            match.start(),
                            full_text,
                            segments
                        )

                        concerns_found.append({
                            "concern_type": concern_type,
                            "matched_text": match.group(),
                            "context": segment.get("text", "") if segment else match.group(),
                            "timestamp": segment.get("start_time", 0) if segment else 0,
                            "speaker": segment.get("speaker_label", "unknown") if segment else "unknown",
                            "severity": self._assess_concern_severity(concern_type)
                        })
                except re.error as e:
                    logger.warning(f"Regex error for pattern '{pattern}': {e}")

        return self._deduplicate_concerns(concerns_found)

    def _detect_compliance_risks(
        self,
        full_text: str,
        segments: List[Dict]
    ) -> List[Dict]:
        """Detect potential compliance issues"""

        risks = []
        text_lower = full_text.lower()

        for risk_type, patterns in self.compliance_patterns.items():
            for pattern in patterns:
                try:
                    matches = list(re.finditer(pattern, text_lower, re.IGNORECASE))

                    for match in matches:
                        segment = self._find_segment_by_position(
                            match.start(),
                            full_text,
                            segments
                        )

                        if segment:
                            speaker = segment.get("speaker_label", "").lower()
                            # Only flag if it looks like LO said it (speaker 1, host, etc.)
                            if "1" in speaker or "host" in speaker or "loan" in speaker:
                                risks.append({
                                    "risk_type": risk_type,
                                    "matched_text": match.group(),
                                    "context": segment.get("text", ""),
                                    "timestamp": segment.get("start_time", 0),
                                    "severity": "high" if risk_type in ["discrimination", "steering"] else "medium",
                                    "recommendation": self._get_compliance_recommendation(risk_type)
                                })
                except re.error as e:
                    logger.warning(f"Regex error for pattern '{pattern}': {e}")

        return risks

    def _detect_competitors(
        self,
        full_text: str,
        segments: List[Dict]
    ) -> Dict:
        """Track competitor mentions"""

        mentions = []
        text_lower = full_text.lower()

        for competitor in self.competitors:
            if competitor.lower() in text_lower:
                pattern = re.escape(competitor)
                try:
                    matches = list(re.finditer(pattern, text_lower, re.IGNORECASE))

                    for match in matches:
                        segment = self._find_segment_by_position(
                            match.start(),
                            full_text,
                            segments
                        )

                        mentions.append({
                            "competitor": competitor.title(),
                            "context": segment.get("text", "") if segment else "",
                            "timestamp": segment.get("start_time", 0) if segment else 0,
                            "speaker": segment.get("speaker_label", "unknown") if segment else "unknown"
                        })
                except re.error:
                    pass

        # Build summary
        competitor_summary = {}
        for mention in mentions:
            comp = mention["competitor"]
            if comp not in competitor_summary:
                competitor_summary[comp] = {
                    "count": 0,
                    "contexts": []
                }
            competitor_summary[comp]["count"] += 1
            if mention["context"] and mention["context"] not in competitor_summary[comp]["contexts"]:
                competitor_summary[comp]["contexts"].append(mention["context"])

        return {
            "mentions": mentions,
            "summary": competitor_summary,
            "total_mentions": len(mentions)
        }

    def _extract_objections(
        self,
        segments: List[Dict]
    ) -> List[Dict]:
        """Extract borrower objections and how LO handled them"""

        objection_keywords = [
            "but", "however", "concerned", "worried", "problem",
            "issue", "too expensive", "can't afford", "not sure",
            "don't think", "hesitant", "i'm nervous", "uncomfortable"
        ]

        objections = []

        for i, segment in enumerate(segments):
            text_lower = segment.get("text", "").lower()

            if any(keyword in text_lower for keyword in objection_keywords):
                speaker = segment.get("speaker_label", "").lower()

                # Check if this is the borrower speaking (speaker 2, borrower, client, etc.)
                if "2" in speaker or "borrower" in speaker or "client" in speaker or "guest" in speaker:
                    # Get LO's response (next 1-2 segments)
                    lo_response = ""
                    if i + 1 < len(segments):
                        lo_response = segments[i + 1].get("text", "")
                    if i + 2 < len(segments) and len(lo_response) < 100:
                        lo_response += " " + segments[i + 2].get("text", "")

                    handled_well = self._assess_objection_handling(lo_response)

                    objections.append({
                        "objection": segment.get("text", ""),
                        "timestamp": segment.get("start_time", 0),
                        "lo_response": lo_response[:500],  # Limit length
                        "handled_well": handled_well,
                        "handling_tips": self._get_objection_handling_tips(handled_well)
                    })

        return objections[:10]  # Limit to top 10

    def _assess_objection_handling(self, response: str) -> bool:
        """Assess if LO handled objection well"""

        response_lower = response.lower()

        good_indicators = [
            "understand", "makes sense", "let me explain",
            "here's how", "good question", "many people",
            "i can help", "we can work with", "great point",
            "i hear you", "that's common", "absolutely"
        ]

        bad_indicators = [
            "but", "however", "actually", "wrong",
            "you should", "you need to", "trust me",
            "don't worry", "just sign"
        ]

        good_score = sum(1 for indicator in good_indicators if indicator in response_lower)
        bad_score = sum(1 for indicator in bad_indicators if indicator in response_lower)

        return good_score > bad_score

    def _assess_explanation_effectiveness(
        self,
        segments: List[Dict]
    ) -> Dict:
        """Assess if borrower understood explanations"""

        understanding_signals = {
            "positive": [
                "i understand", "makes sense", "got it", "okay",
                "that helps", "clear now", "i see", "perfect",
                "oh okay", "ah", "great", "sounds good"
            ],
            "negative": [
                "still confused", "don't get it", "what do you mean",
                "can you explain again", "lost me", "not following",
                "huh", "wait what", "i'm lost", "confused"
            ]
        }

        positive_count = 0
        negative_count = 0
        confusion_moments = []

        for segment in segments:
            text_lower = segment.get("text", "").lower()
            speaker = segment.get("speaker_label", "").lower()

            # Only check borrower segments
            if "2" in speaker or "borrower" in speaker or "client" in speaker or "guest" in speaker:
                for signal in understanding_signals["positive"]:
                    if signal in text_lower:
                        positive_count += 1

                for signal in understanding_signals["negative"]:
                    if signal in text_lower:
                        negative_count += 1
                        confusion_moments.append({
                            "text": segment.get("text", ""),
                            "timestamp": segment.get("start_time", 0)
                        })

        total_signals = positive_count + negative_count

        if total_signals == 0:
            effectiveness = "unknown"
            score = 0.5
        elif positive_count > negative_count * 2:
            effectiveness = "excellent"
            score = 0.9
        elif positive_count > negative_count:
            effectiveness = "good"
            score = 0.7
        elif negative_count > positive_count:
            effectiveness = "needs_improvement"
            score = 0.3
        else:
            effectiveness = "unclear"
            score = 0.5

        return {
            "effectiveness": effectiveness,
            "score": round(score, 2),
            "positive_signals": positive_count,
            "negative_signals": negative_count,
            "confusion_moments": confusion_moments[:5],  # Top 5
            "recommendation": self._get_explanation_recommendation(effectiveness)
        }

    def _extract_loan_details(self, full_text: str) -> Dict:
        """Extract mentioned loan details"""

        text_lower = full_text.lower()

        details = {
            "loan_amount": None,
            "loan_type": None,
            "rate_mentioned": False,
            "rate_value": None,
            "down_payment": None,
            "property_value": None,
            "credit_score_mentioned": False,
            "term_mentioned": None
        }

        # Extract loan amount
        amount_pattern = r'\$[\d,]+(?:k|,000)?'
        amounts = re.findall(amount_pattern, full_text)
        if amounts:
            # Take the largest amount as likely loan amount
            details["loan_amount"] = max(amounts, key=lambda x: self._parse_amount(x))

        # Extract loan type
        loan_types = {
            "conventional": ["conventional"],
            "fha": ["fha"],
            "va": ["va", "veterans"],
            "usda": ["usda", "rural"],
            "jumbo": ["jumbo"]
        }
        for loan_type, keywords in loan_types.items():
            if any(kw in text_lower for kw in keywords):
                details["loan_type"] = loan_type
                break

        # Check if rate was discussed
        if "rate" in text_lower or "interest" in text_lower:
            details["rate_mentioned"] = True

            # Try to extract rate value
            rate_pattern = r'(\d+\.?\d*)\s*%'
            rates = re.findall(rate_pattern, full_text)
            if rates:
                # Filter reasonable mortgage rates (2-12%)
                valid_rates = [r for r in rates if 2 <= float(r) <= 12]
                if valid_rates:
                    details["rate_value"] = valid_rates[0] + "%"

        # Check credit score mention
        if "credit score" in text_lower or "credit" in text_lower:
            details["credit_score_mentioned"] = True
            # Try to extract score
            score_pattern = r'\b([6-8]\d{2})\b'
            scores = re.findall(score_pattern, full_text)
            if scores:
                details["credit_score_value"] = scores[0]

        # Check for term
        term_patterns = ["30 year", "30-year", "15 year", "15-year", "20 year"]
        for term in term_patterns:
            if term in text_lower:
                details["term_mentioned"] = term.replace("-", " ")
                break

        return details

    def _assess_next_steps_clarity(
        self,
        full_text: str,
        segments: List[Dict]
    ) -> Dict:
        """Assess if next steps were clearly communicated"""

        next_step_phrases = [
            "next step", "what you need to do", "i'll send you",
            "please provide", "we'll need", "timeline",
            "by tomorrow", "within", "follow up", "i'll call",
            "you'll receive", "expect to hear", "let me send"
        ]

        clarity_score = 0
        next_steps_mentioned = []

        # Look at last 25% of segments (end of call)
        if segments:
            end_threshold = segments[-1].get("end_time", 0) * 0.75

            for segment in segments:
                start_time = segment.get("start_time", 0)
                if start_time > end_threshold:
                    text_lower = segment.get("text", "").lower()
                    for phrase in next_step_phrases:
                        if phrase in text_lower:
                            clarity_score += 1
                            if segment.get("text") not in next_steps_mentioned:
                                next_steps_mentioned.append(segment.get("text", ""))

        # Normalize score
        normalized_score = min(clarity_score / 3, 1.0)

        return {
            "clarity_score": round(normalized_score, 2),
            "next_steps_mentioned": len(next_steps_mentioned),
            "clear": clarity_score >= 2,
            "next_steps": next_steps_mentioned[:3],  # Top 3
            "recommendation": (
                "Great job setting clear expectations!"
                if clarity_score >= 2
                else "End calls with specific next steps and timelines."
            )
        }

    def _find_segment_by_position(
        self,
        char_position: int,
        full_text: str,
        segments: List[Dict]
    ) -> Optional[Dict]:
        """Find transcript segment containing a character position"""

        if not segments:
            return None

        current_pos = 0
        for segment in segments:
            text = segment.get("text", "")
            segment_length = len(text)
            if current_pos <= char_position < current_pos + segment_length:
                return segment
            current_pos += segment_length + 1  # +1 for space/newline

        # If not found, return the closest segment by proportion
        proportion = char_position / len(full_text) if full_text else 0
        segment_index = int(proportion * len(segments))
        segment_index = min(segment_index, len(segments) - 1)
        return segments[segment_index] if segments else None

    def _assess_concern_severity(self, concern_type: str) -> str:
        """Assess severity of borrower concern"""

        high_severity = ["rate_anxiety", "competing_offers", "trust_hesitation"]
        medium_severity = ["timeline_pressure", "confusion", "affordability_concern"]

        if concern_type in high_severity:
            return "high"
        elif concern_type in medium_severity:
            return "medium"
        return "low"

    def _deduplicate_concerns(self, concerns: List[Dict]) -> List[Dict]:
        """Remove duplicate/similar concerns"""

        unique_concerns = []
        seen_keys = set()

        for concern in concerns:
            # Group by type and minute
            timestamp = concern.get("timestamp", 0)
            key = f"{concern['concern_type']}_{int(timestamp // 60)}"
            if key not in seen_keys:
                unique_concerns.append(concern)
                seen_keys.add(key)

        return unique_concerns

    def _get_compliance_recommendation(self, risk_type: str) -> str:
        """Get recommendation for compliance risk"""

        recommendations = {
            "steering": "Present all loan options objectively. Let borrowers choose what's best for them based on their situation.",
            "discrimination": "CRITICAL: Never reference protected classes. Focus only on financial qualifications and loan requirements.",
            "pressure": "Avoid high-pressure tactics. Give borrowers time to make informed decisions. Rates change daily - that's normal.",
            "kickback_mention": "Never discuss compensation with borrowers. Focus on their best interests and loan suitability.",
            "missing_disclosure": "Always ensure all fees and costs are clearly disclosed. Transparency builds trust."
        }

        return recommendations.get(risk_type, "Review conversation for compliance best practices.")

    def _get_explanation_recommendation(self, effectiveness: str) -> str:
        """Get recommendation for improving explanations"""

        recommendations = {
            "excellent": "Great job! Borrower clearly understood your explanations.",
            "good": "Solid explanations. Consider checking understanding more frequently.",
            "needs_improvement": "Borrower showed confusion. Use simpler language and check understanding every 2-3 minutes.",
            "unclear": "Ask 'Does that make sense?' or 'What questions do you have?' after complex topics.",
            "unknown": "Check for understanding by asking 'Does that make sense?' after explanations."
        }

        return recommendations.get(effectiveness, "")

    def _get_objection_handling_tips(self, handled_well: bool) -> str:
        """Get tips for objection handling"""

        if handled_well:
            return "Good use of empathetic listening. Keep acknowledging concerns before addressing them."
        return "Try the 'Feel, Felt, Found' technique: 'I understand how you feel. Others felt that way too. Here's what they found...'"

    def _calculate_risk_score(self, intelligence: Dict) -> float:
        """Calculate overall risk score (0-1, higher = more risk)"""

        risk_score = 0.0

        # Compliance risks (highest weight)
        compliance_risks = intelligence.get("compliance_risks", [])
        high_compliance = sum(1 for r in compliance_risks if r.get("severity") == "high")
        medium_compliance = sum(1 for r in compliance_risks if r.get("severity") == "medium")
        risk_score += high_compliance * 0.3 + medium_compliance * 0.1

        # Unaddressed concerns
        concerns = intelligence.get("borrower_concerns", [])
        high_concerns = sum(1 for c in concerns if c.get("severity") == "high")
        risk_score += high_concerns * 0.1

        # Poor objection handling
        objections = intelligence.get("objections", [])
        poor_handling = sum(1 for o in objections if not o.get("handled_well"))
        risk_score += poor_handling * 0.05

        # Poor explanation effectiveness
        effectiveness = intelligence.get("explanation_effectiveness", {})
        if effectiveness.get("effectiveness") == "needs_improvement":
            risk_score += 0.15

        # Unclear next steps
        next_steps = intelligence.get("next_steps_clarity", {})
        if not next_steps.get("clear"):
            risk_score += 0.1

        return min(risk_score, 1.0)

    def _extract_priority_flags(self, intelligence: Dict) -> List[Dict]:
        """Extract high-priority items for review"""

        flags = []

        # Compliance risks always high priority
        for risk in intelligence.get("compliance_risks", []):
            if risk.get("severity") == "high":
                flags.append({
                    "type": "compliance",
                    "message": f"Potential {risk['risk_type']} issue detected",
                    "severity": "critical",
                    "action": risk.get("recommendation")
                })

        # Multiple competitor mentions
        competitor_data = intelligence.get("competitor_mentions", {})
        if competitor_data.get("total_mentions", 0) >= 2:
            flags.append({
                "type": "competitive",
                "message": "Borrower is actively shopping - competitive situation",
                "severity": "high",
                "action": "Focus on value proposition and relationship, not just rate"
            })

        # Poor explanation effectiveness
        effectiveness = intelligence.get("explanation_effectiveness", {})
        if effectiveness.get("effectiveness") == "needs_improvement":
            flags.append({
                "type": "communication",
                "message": "Borrower showed signs of confusion during call",
                "severity": "medium",
                "action": "Follow up to clarify any confusion and confirm understanding"
            })

        # Unclear next steps
        next_steps = intelligence.get("next_steps_clarity", {})
        if not next_steps.get("clear"):
            flags.append({
                "type": "follow_up",
                "message": "Next steps may not have been clearly communicated",
                "severity": "medium",
                "action": "Send follow-up email with specific action items and timeline"
            })

        return flags

    def _parse_amount(self, amount_str: str) -> float:
        """Parse dollar amount string to float for comparison"""

        try:
            clean = amount_str.replace("$", "").replace(",", "")
            if clean.lower().endswith("k"):
                return float(clean[:-1]) * 1000
            return float(clean)
        except ValueError:
            return 0.0


# Service singleton
_mortgage_intelligence_service: Optional[MortgageIntelligenceService] = None


def get_mortgage_intelligence_service() -> MortgageIntelligenceService:
    """Get or create the mortgage intelligence service singleton"""
    global _mortgage_intelligence_service
    if _mortgage_intelligence_service is None:
        _mortgage_intelligence_service = MortgageIntelligenceService()
    return _mortgage_intelligence_service
