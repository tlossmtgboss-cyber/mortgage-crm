"""
Unified Conversation Intelligence Service

Provides shared AI-powered conversation logic for both Email and SMS channels.
Includes tone analysis, qualification tracking, and context-aware response generation.

Features:
- Multi-channel support (email, SMS, chat)
- Tone analysis (emotional state, communication style, sentiment, urgency)
- Progressive qualification data collection
- Conversation state management
- Context-aware response generation
- Lead scoring integration
"""

import re
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    CHAT = "chat"
    VOICE = "voice"


class ConversationStage(str, Enum):
    INITIAL_CONTACT = "initial_contact"
    QUALIFICATION = "qualification"
    OBJECTION_HANDLING = "objection_handling"
    BOOKING = "booking"
    NURTURE = "nurture"
    ESCALATED = "escalated"
    COMPLETED = "completed"


class QualificationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    DISQUALIFIED = "disqualified"


# =============================================================================
# TONE ANALYSIS CONFIGURATION
# =============================================================================

EMOTIONAL_INDICATORS = {
    "frustrated": {
        "keywords": ["frustrated", "frustrating", "annoying", "annoyed", "irritated",
                    "fed up", "sick of", "tired of", "waste of time", "ridiculous",
                    "unacceptable", "disappointing", "let down"],
        "intensity": 0.8,
        "category": "negative"
    },
    "angry": {
        "keywords": ["angry", "furious", "outraged", "unbelievable", "terrible",
                    "worst", "never again", "lawsuit", "attorney", "complain",
                    "supervisor", "manager", "escalate", "demand", "unacceptable",
                    "resolved immediately", "this is unacceptable"],
        "intensity": 1.0,
        "category": "negative"
    },
    "confused": {
        "keywords": ["confused", "don't understand", "unclear", "what do you mean",
                    "can you explain", "lost", "makes no sense", "why", "how does",
                    "not sure", "help me understand"],
        "intensity": 0.5,
        "category": "neutral"
    },
    "anxious": {
        "keywords": ["worried", "anxious", "nervous", "concerned", "scared",
                    "afraid", "what if", "stress", "overwhelming", "panic",
                    "uncertain", "risky"],
        "intensity": 0.7,
        "category": "negative"
    },
    "excited": {
        "keywords": ["excited", "thrilled", "can't wait", "amazing", "fantastic",
                    "wonderful", "perfect", "love it", "great news", "awesome",
                    "dream", "finally"],
        "intensity": 0.9,
        "category": "positive"
    },
    "grateful": {
        "keywords": ["thank you", "thanks so much", "appreciate", "grateful", "thankful",
                    "helped", "great job", "wonderful service", "above and beyond",
                    "exceptional", "outstanding", "you've been wonderful", "so helpful",
                    "all your help", "thank you so much"],
        "intensity": 0.9,
        "category": "positive"
    },
    "hopeful": {
        "keywords": ["hope", "hoping", "looking forward", "optimistic", "fingers crossed",
                    "wish", "maybe", "possibility", "potential", "opportunity"],
        "intensity": 0.6,
        "category": "positive"
    },
    "disappointed": {
        "keywords": ["disappointed", "letdown", "expected more", "not what I wanted",
                    "underwhelming", "fell short", "missed", "failed"],
        "intensity": 0.7,
        "category": "negative"
    },
    "impatient": {
        "keywords": ["waiting", "how long", "when will", "still waiting", "delay",
                    "taking too long", "hurry", "asap", "immediately", "urgent"],
        "intensity": 0.6,
        "category": "negative"
    },
    "satisfied": {
        "keywords": ["satisfied", "happy with", "pleased", "good experience",
                    "met expectations", "works well", "no complaints", "fine"],
        "intensity": 0.6,
        "category": "positive"
    }
}

# Priority for tie-breaking (higher = selected first when scores equal)
EMOTION_PRIORITY = {
    "angry": 10,
    "frustrated": 9,
    "disappointed": 8,
    "anxious": 7,
    "impatient": 6,
    "confused": 5,
    "grateful": 4,
    "excited": 3,
    "satisfied": 2,
    "hopeful": 1
}

STYLE_INDICATORS = {
    "formal": {
        "keywords": ["dear", "sincerely", "regards", "respectfully", "pursuant to",
                    "hereby", "enclosed", "attached please find", "inquire", "request"],
        "patterns": [r"Dear\s+(Mr\.|Mrs\.|Ms\.|Dr\.)", r"Best regards", r"Yours (truly|sincerely)"]
    },
    "casual": {
        "keywords": ["hey", "hi", "thanks", "cool", "awesome", "yeah", "gonna",
                    "wanna", "kinda", "sorta", "btw", "fyi", "lol", "haha", "no worries"],
        "patterns": [r"^(Hey|Hi|Yo)\s*[!,]?", r"!{2,}", r"\.\.\.", r":\)", r":\("]
    },
    "urgent": {
        "keywords": ["urgent", "asap", "immediately", "emergency", "critical",
                    "time sensitive", "deadline", "now", "right away", "rush"],
        "patterns": [r"URGENT", r"ASAP", r"!!+", r"NEED.*(NOW|TODAY|IMMEDIATELY)"]
    },
    "demanding": {
        "keywords": ["demand", "require", "must", "expect", "insist", "need",
                    "should have", "better be", "you will", "i want"],
        "patterns": [r"I (demand|insist|require)", r"You (must|need to|better)"]
    },
    "friendly": {
        "keywords": ["hope you're well", "how are you", "nice to", "pleasure",
                    "happy to help", "feel free", "let me know", "anytime"],
        "patterns": [r"Hope (you're|this finds you)", r"Happy to", r"Feel free"]
    },
    "professional": {
        "keywords": ["please advise", "as discussed", "per our conversation",
                    "following up", "as mentioned", "kindly", "at your convenience",
                    "for your review", "your earliest convenience"],
        "patterns": [r"Please (advise|confirm|let me know)", r"As (discussed|mentioned|per)"]
    }
}

INTENSITY_AMPLIFIERS = [
    "very", "extremely", "incredibly", "absolutely", "completely", "totally",
    "utterly", "highly", "deeply", "seriously", "really", "so", "super"
]

INTENSITY_DIMINISHERS = [
    "slightly", "somewhat", "a bit", "a little", "kind of", "sort of",
    "fairly", "rather", "quite", "maybe", "perhaps", "possibly"
]

POSITIVE_WORDS = [
    "good", "great", "excellent", "amazing", "wonderful", "fantastic",
    "perfect", "happy", "pleased", "satisfied", "love", "best", "helpful",
    "easy", "smooth", "quick", "efficient", "professional", "friendly",
    "awesome", "brilliant", "outstanding", "superb", "terrific", "delightful",
    "dream", "thrilled", "excited", "wait", "news", "grateful", "thankful"
]

NEGATIVE_WORDS = [
    "bad", "terrible", "awful", "horrible", "worst", "poor", "disappointed",
    "frustrated", "angry", "upset", "confused", "difficult", "slow",
    "unprofessional", "rude", "unhelpful", "problem", "issue", "wrong",
    "mistake", "error", "fail", "failure", "never", "hate", "annoying"
]

URGENCY_INDICATORS = {
    "critical": {
        "keywords": ["emergency", "urgent", "critical", "immediately", "asap",
                    "right now", "today", "time sensitive", "deadline today"],
        "weight": 1.0
    },
    "high": {
        "keywords": ["soon", "quickly", "fast", "hurry", "rush", "priority",
                    "important", "need by", "deadline", "time running out",
                    "waiting for weeks", "been waiting", "nobody has", "no one has"],
        "weight": 0.75
    },
    "medium": {
        "keywords": ["this week", "following up", "checking in", "when possible",
                    "at your earliest", "please advise", "waiting for"],
        "weight": 0.5
    },
    "low": {
        "keywords": ["no rush", "whenever", "at your convenience", "no hurry",
                    "take your time", "when you can", "fyi", "just wanted to"],
        "weight": 0.25
    }
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ToneAnalysis:
    """Complete tone analysis result."""
    emotional_state: Dict[str, Any]
    communication_style: Dict[str, Any]
    sentiment: Dict[str, Any]
    urgency: Dict[str, Any]
    risk_level: str
    response_guidance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QualificationData:
    """Tracks qualification progress."""
    loan_purpose: Optional[str] = None  # purchase, refinance
    property_value: Optional[float] = None
    loan_amount: Optional[float] = None
    closing_timeline: Optional[str] = None
    pre_approved_elsewhere: Optional[bool] = None
    credit_score_range: Optional[str] = None
    employment_status: Optional[str] = None
    annual_income: Optional[float] = None
    down_payment: Optional[float] = None
    property_type: Optional[str] = None
    first_time_buyer: Optional[bool] = None

    # Contact info
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    # Metadata
    collected_at: Dict[str, str] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)

    def get_completion_percentage(self) -> float:
        """Calculate qualification completion percentage."""
        required_fields = ['loan_purpose', 'property_value', 'closing_timeline',
                         'first_name', 'email', 'phone']
        filled = sum(1 for f in required_fields if getattr(self, f) is not None)
        return (filled / len(required_fields)) * 100

    def get_missing_required(self) -> List[str]:
        """Get list of missing required fields."""
        required_fields = ['loan_purpose', 'property_value', 'closing_timeline',
                         'first_name', 'email', 'phone']
        return [f for f in required_fields if getattr(self, f) is None]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationState:
    """Tracks the state of a conversation across messages."""
    conversation_id: str
    channel: Channel
    stage: ConversationStage = ConversationStage.INITIAL_CONTACT
    qualification_status: QualificationStatus = QualificationStatus.NOT_STARTED
    qualification_data: QualificationData = field(default_factory=QualificationData)

    # History tracking
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    last_tone: Optional[ToneAnalysis] = None
    tone_history: List[Dict] = field(default_factory=list)
    message_history: List[Dict] = field(default_factory=list)  # Stores conversation messages

    # Objection tracking
    objection_count: int = 0
    objections_handled: List[str] = field(default_factory=list)

    # Context
    lead_id: Optional[str] = None
    user_id: Optional[str] = None
    loan_id: Optional[str] = None
    assigned_lo_id: Optional[str] = None

    # AI control
    ai_enabled: bool = True
    escalation_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['channel'] = self.channel.value
        data['stage'] = self.stage.value
        data['qualification_status'] = self.qualification_status.value
        if self.last_message_at:
            data['last_message_at'] = self.last_message_at.isoformat()
        return data


# =============================================================================
# TONE ANALYSIS FUNCTIONS
# =============================================================================

def analyze_emotional_state(text: str) -> Dict[str, Any]:
    """Detect emotional state from text with intensity scoring."""
    text_lower = text.lower()
    detected_emotions = {}

    for emotion, config in EMOTIONAL_INDICATORS.items():
        score = 0
        matched_keywords = []

        for keyword in config["keywords"]:
            if keyword in text_lower:
                score += config["intensity"]
                matched_keywords.append(keyword)

        if score > 0:
            # Check for intensity amplifiers/diminishers
            for amp in INTENSITY_AMPLIFIERS:
                if amp in text_lower:
                    score *= 1.3
                    break
            for dim in INTENSITY_DIMINISHERS:
                if dim in text_lower:
                    score *= 0.7
                    break

            detected_emotions[emotion] = {
                "score": round(score, 2),
                "keywords": matched_keywords,
                "category": config["category"]
            }

    if not detected_emotions:
        return {
            "primary_emotion": "neutral",
            "primary_score": 0,
            "emotion_category": "neutral",
            "all_emotions": {}
        }

    # Select primary emotion (highest score, with priority tie-breaking)
    primary = max(
        detected_emotions.items(),
        key=lambda x: (x[1]["score"], EMOTION_PRIORITY.get(x[0], 0))
    )

    return {
        "primary_emotion": primary[0],
        "primary_score": primary[1]["score"],
        "emotion_category": primary[1]["category"],
        "all_emotions": detected_emotions
    }


def analyze_communication_style(text: str) -> Dict[str, Any]:
    """Detect communication style from text."""
    text_lower = text.lower()
    style_scores = {}

    for style, config in STYLE_INDICATORS.items():
        score = 0

        # Keyword matching
        for keyword in config["keywords"]:
            if keyword in text_lower:
                score += 1

        # Pattern matching
        for pattern in config.get("patterns", []):
            if re.search(pattern, text, re.IGNORECASE):
                score += 2

        if score > 0:
            style_scores[style] = score

    if not style_scores:
        return {
            "primary_style": "neutral",
            "primary_score": 0,
            "secondary_style": None,
            "all_styles": {}
        }

    sorted_styles = sorted(style_scores.items(), key=lambda x: x[1], reverse=True)

    return {
        "primary_style": sorted_styles[0][0],
        "primary_score": sorted_styles[0][1],
        "secondary_style": sorted_styles[1][0] if len(sorted_styles) > 1 else None,
        "all_styles": style_scores
    }


def calculate_sentiment_intensity(text: str) -> Dict[str, Any]:
    """Calculate sentiment with intensity level."""
    text_lower = text.lower()
    words = text_lower.split()

    positive_count = 0
    negative_count = 0
    positive_found = []
    negative_found = []

    for word in words:
        clean_word = re.sub(r'[^\w]', '', word)
        if clean_word in POSITIVE_WORDS:
            positive_count += 1
            positive_found.append(clean_word)
        if clean_word in NEGATIVE_WORDS:
            negative_count += 1
            negative_found.append(clean_word)

    # Check for amplifiers
    amplifier_boost = 0
    for amp in INTENSITY_AMPLIFIERS:
        if amp in text_lower:
            amplifier_boost += 0.3

    # Calculate sentiment score (-5 to +5 scale)
    total_words = len(words) if words else 1
    sentiment_score = ((positive_count - negative_count) / total_words) * 10
    sentiment_score += amplifier_boost if positive_count > negative_count else -amplifier_boost

    # Determine category with adjusted thresholds
    if sentiment_score > 2.0:
        sentiment_category = "very_positive"
    elif sentiment_score > 0.8:
        sentiment_category = "positive"
    elif sentiment_score > 0.2:
        sentiment_category = "slightly_positive"
    elif sentiment_score >= -0.2:
        sentiment_category = "neutral"
    elif sentiment_score >= -0.8:
        sentiment_category = "slightly_negative"
    elif sentiment_score >= -2.0:
        sentiment_category = "negative"
    else:
        sentiment_category = "very_negative"

    # Determine intensity level
    abs_score = abs(sentiment_score)
    if abs_score > 2.0:
        intensity_level = "high"
    elif abs_score > 0.8:
        intensity_level = "medium"
    else:
        intensity_level = "low"

    return {
        "sentiment_score": round(sentiment_score, 2),
        "sentiment_category": sentiment_category,
        "intensity_level": intensity_level,
        "positive_words": positive_found,
        "negative_words": negative_found,
        "word_count": len(words)
    }


def detect_urgency_level(text: str) -> Dict[str, Any]:
    """Detect urgency level from text."""
    text_lower = text.lower()
    urgency_scores = {}
    matched_indicators = []

    for level, config in URGENCY_INDICATORS.items():
        for keyword in config["keywords"]:
            if keyword in text_lower:
                current_score = urgency_scores.get(level, 0)
                urgency_scores[level] = current_score + config["weight"]
                matched_indicators.append(keyword)

    # Check for caps and exclamation marks (urgency signals)
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    exclamation_count = text.count('!')

    if caps_ratio > 0.3 or exclamation_count >= 3:
        urgency_scores["high"] = urgency_scores.get("high", 0) + 0.5

    if not urgency_scores:
        return {
            "urgency_level": "normal",
            "urgency_score": 0,
            "urgency_indicators": []
        }

    # Select highest urgency level
    max_level = max(urgency_scores.items(), key=lambda x: x[1])

    return {
        "urgency_level": max_level[0],
        "urgency_score": round(max_level[1], 2),
        "urgency_indicators": matched_indicators
    }


def analyze_tone(text: str) -> ToneAnalysis:
    """Perform complete tone analysis on text."""
    emotional = analyze_emotional_state(text)
    style = analyze_communication_style(text)
    sentiment = calculate_sentiment_intensity(text)
    urgency = detect_urgency_level(text)

    # Determine risk level
    risk_factors = []
    if emotional["emotion_category"] == "negative":
        risk_factors.append("negative_emotion")
    if urgency["urgency_level"] in ["critical", "high"]:
        risk_factors.append("high_urgency")
    if style["primary_style"] in ["demanding", "urgent"]:
        risk_factors.append("demanding_style")
    if sentiment["sentiment_category"] in ["very_negative", "negative"]:
        risk_factors.append("negative_sentiment")

    risk_level = "high" if len(risk_factors) >= 2 else "medium" if risk_factors else "low"

    # Generate response guidance
    response_guidance = generate_response_guidance(emotional, style, sentiment, urgency, risk_level)

    return ToneAnalysis(
        emotional_state=emotional,
        communication_style=style,
        sentiment=sentiment,
        urgency=urgency,
        risk_level=risk_level,
        response_guidance=response_guidance
    )


def generate_response_guidance(
    emotional: Dict,
    style: Dict,
    sentiment: Dict,
    urgency: Dict,
    risk_level: str
) -> Dict[str, Any]:
    """Generate guidance for responding based on tone analysis."""

    recommendations = []
    suggested_tone = "professional"

    # Emotional state recommendations
    emotion = emotional.get("primary_emotion", "neutral")
    if emotion == "angry":
        recommendations.append("Acknowledge frustration without being defensive")
        recommendations.append("Offer concrete solutions or escalation path")
        suggested_tone = "empathetic_professional"
    elif emotion == "frustrated":
        recommendations.append("Validate their experience")
        recommendations.append("Provide clear next steps")
        suggested_tone = "empathetic_professional"
    elif emotion == "confused":
        recommendations.append("Explain clearly and simply")
        recommendations.append("Offer to clarify any specific points")
        suggested_tone = "helpful_patient"
    elif emotion == "anxious":
        recommendations.append("Provide reassurance")
        recommendations.append("Be specific about timelines and expectations")
        suggested_tone = "calm_reassuring"
    elif emotion == "excited":
        recommendations.append("Match their enthusiasm appropriately")
        recommendations.append("Maintain momentum")
        suggested_tone = "warm_professional"
    elif emotion == "grateful":
        recommendations.append("Accept thanks graciously")
        recommendations.append("Reinforce positive relationship")
        suggested_tone = "warm_professional"

    # Style matching recommendations
    if style.get("primary_style") == "formal":
        recommendations.append("Match formal tone in response")
    elif style.get("primary_style") == "casual":
        recommendations.append("Can use slightly casual but professional tone")
    elif style.get("primary_style") == "urgent":
        recommendations.append("Prioritize this response")
        recommendations.append("Be concise and action-oriented")

    # Urgency recommendations
    if urgency.get("urgency_level") == "critical":
        recommendations.insert(0, "PRIORITY: Respond immediately")
    elif urgency.get("urgency_level") == "high":
        recommendations.insert(0, "Respond within 1 hour")

    return {
        "suggested_tone": suggested_tone,
        "recommendations": recommendations,
        "priority": "high" if risk_level == "high" or urgency.get("urgency_level") == "critical" else "normal",
        "escalate_if_unresolved": risk_level == "high"
    }


# =============================================================================
# QUALIFICATION FUNCTIONS
# =============================================================================

def extract_qualification_data(text: str, existing: Optional[QualificationData] = None) -> QualificationData:
    """Extract qualification data from conversation text."""
    data = existing or QualificationData()
    text_lower = text.lower()

    # Loan purpose detection
    if data.loan_purpose is None:
        # Purchase intent keywords - check longer phrases first to avoid false positives
        purchase_phrases = [
            "buy a home", "buy a house", "buying a home", "buying a house",
            "purchase a home", "purchase a house", "looking to buy", "want to buy",
            "first home", "new home", "home purchase", "house purchase",
            "purchasing", "purchase", "buying", "to buy"
        ]
        if any(phrase in text_lower for phrase in purchase_phrases):
            data.loan_purpose = "purchase"
            data.collected_at["loan_purpose"] = datetime.now().isoformat()
        elif any(word in text_lower for word in ["refinance", "refi", "refinancing", "lower rate", "cash out", "cash-out"]):
            data.loan_purpose = "refinance"
            data.collected_at["loan_purpose"] = datetime.now().isoformat()

    # Property value extraction
    if data.property_value is None:
        value_patterns = [
            r'\$?([\d,]+)\s*(?:k|thousand)',
            r'\$?([\d,]+)\s*(?:property|home|house|value)',
            r'(?:worth|value|price|around|about)[^\d]*\$?([\d,]+)',
            r'\$([\d,]+)',  # Match $450,000 format
            r'\$?([\d]{3,}(?:,\d{3})*)',
        ]
        for pattern in value_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                value = float(value_str)
                if 'k' in text_lower or 'thousand' in text_lower:
                    value *= 1000
                if 50000 <= value <= 10000000:  # Reasonable property value range
                    data.property_value = value
                    data.collected_at["property_value"] = datetime.now().isoformat()
                    break

    # Timeline extraction
    if data.closing_timeline is None:
        if any(phrase in text_lower for phrase in ["asap", "immediately", "right away", "as soon as"]):
            data.closing_timeline = "asap"
            data.collected_at["closing_timeline"] = datetime.now().isoformat()
        elif any(phrase in text_lower for phrase in ["30 days", "month", "30-60"]):
            data.closing_timeline = "30_days"
            data.collected_at["closing_timeline"] = datetime.now().isoformat()
        elif any(phrase in text_lower for phrase in ["60 days", "2 months", "60-90"]):
            data.closing_timeline = "60_days"
            data.collected_at["closing_timeline"] = datetime.now().isoformat()
        elif any(phrase in text_lower for phrase in ["90 days", "3 months"]):
            data.closing_timeline = "90_days"
            data.collected_at["closing_timeline"] = datetime.now().isoformat()
        elif any(phrase in text_lower for phrase in ["6 months", "half year"]):
            data.closing_timeline = "6_months"
            data.collected_at["closing_timeline"] = datetime.now().isoformat()
        elif any(phrase in text_lower for phrase in ["just looking", "browsing", "not sure", "year"]):
            data.closing_timeline = "not_sure"
            data.collected_at["closing_timeline"] = datetime.now().isoformat()

    # Pre-approval detection
    if data.pre_approved_elsewhere is None:
        if any(phrase in text_lower for phrase in ["pre-approved", "preapproved", "already approved", "have approval"]):
            data.pre_approved_elsewhere = True
            data.collected_at["pre_approved_elsewhere"] = datetime.now().isoformat()
        elif any(phrase in text_lower for phrase in ["not pre-approved", "no pre-approval", "haven't been approved", "not yet"]):
            data.pre_approved_elsewhere = False
            data.collected_at["pre_approved_elsewhere"] = datetime.now().isoformat()

    # First time buyer detection
    if data.first_time_buyer is None:
        if any(phrase in text_lower for phrase in ["first time", "first home", "never owned", "first-time"]):
            data.first_time_buyer = True
            data.collected_at["first_time_buyer"] = datetime.now().isoformat()

    # Email extraction
    if data.email is None:
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        match = re.search(email_pattern, text)
        if match:
            data.email = match.group(0).lower()
            data.collected_at["email"] = datetime.now().isoformat()

    # Phone extraction
    if data.phone is None:
        phone_patterns = [
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            r'\d{10}'
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                phone = re.sub(r'[^\d]', '', match.group(0))
                if len(phone) == 10:
                    data.phone = phone
                    data.collected_at["phone"] = datetime.now().isoformat()
                    break

    # Name extraction (basic)
    if data.first_name is None:
        name_patterns = [
            r"(?:my name is|i'm|i am|this is)\s+([A-Z][a-z]+)",
            r"^([A-Z][a-z]+)\s+here",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data.first_name = match.group(1).title()
                data.collected_at["first_name"] = datetime.now().isoformat()
                break

    return data


def get_next_qualification_question(data: QualificationData, channel: Channel) -> Optional[str]:
    """Get the next qualification question to ask based on what's missing."""

    # Questions in priority order (adjusted for channel)
    questions = []

    if data.loan_purpose is None:
        questions.append({
            "field": "loan_purpose",
            "email": "Are you looking to purchase a new home or refinance an existing mortgage?",
            "sms": "Are you looking to purchase or refinance?"
        })

    if data.property_value is None:
        questions.append({
            "field": "property_value",
            "email": "What's the estimated value of the property you're interested in?",
            "sms": "What's the estimated property value?"
        })

    if data.closing_timeline is None:
        questions.append({
            "field": "closing_timeline",
            "email": "When are you hoping to close? Are you looking to move quickly or just exploring options?",
            "sms": "When are you looking to close?"
        })

    if data.pre_approved_elsewhere is None and data.loan_purpose == "purchase":
        questions.append({
            "field": "pre_approved_elsewhere",
            "email": "Have you been pre-approved by another lender, or would this be your first pre-approval?",
            "sms": "Have you been pre-approved elsewhere?"
        })

    if data.first_name is None:
        questions.append({
            "field": "first_name",
            "email": "By the way, I don't think I caught your name. What should I call you?",
            "sms": "What's your name?"
        })

    if data.email is None and channel == Channel.SMS:
        questions.append({
            "field": "email",
            "email": "What's the best email to reach you at?",
            "sms": "What's your email address?"
        })

    if data.phone is None and channel == Channel.EMAIL:
        questions.append({
            "field": "phone",
            "email": "What's the best phone number to reach you at if we need to discuss details?",
            "sms": "What's your phone number?"
        })

    if questions:
        q = questions[0]
        return q.get(channel.value, q.get("email"))

    return None


def check_for_objections(text: str) -> Tuple[bool, Optional[str]]:
    """Check if text contains an objection and identify the type."""
    text_lower = text.lower()

    objection_patterns = {
        "not_interested": ["not interested", "no thanks", "don't contact", "stop", "unsubscribe", "remove me"],
        "bad_timing": ["bad time", "not right now", "maybe later", "call back", "busy"],
        "using_another": ["already have", "working with", "another lender", "my bank", "already got"],
        "rate_concern": ["rates too high", "rate too high", "too high", "better rate", "waiting for rates", "rate drop", "high rate", "rates are high"],
        "cost_concern": ["too expensive", "can't afford", "costs too much", "fees"],
        "not_ready": ["not ready", "just looking", "not sure", "thinking about it"],
        "trust_concern": ["don't trust", "scam", "spam", "who are you", "how did you get"]
    }

    for objection_type, phrases in objection_patterns.items():
        if any(phrase in text_lower for phrase in phrases):
            return True, objection_type

    return False, None


# =============================================================================
# CONVERSATION INTELLIGENCE SERVICE
# =============================================================================

class ConversationIntelligenceService:
    """
    Unified service for managing AI-powered conversations across channels.
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self._conversation_cache: Dict[str, ConversationState] = {}

    def get_or_create_conversation(
        self,
        conversation_id: str,
        channel: Channel,
        lead_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> ConversationState:
        """Get existing conversation state or create new one."""
        if conversation_id in self._conversation_cache:
            return self._conversation_cache[conversation_id]

        # Load from database if not in cache
        if self.db:
            try:
                from sqlalchemy import text
                result = self.db.execute(text("""
                    SELECT conversation_id, channel, lead_id, user_id, stage,
                           qualification_data, message_count, last_message_at
                    FROM conversation_states WHERE conversation_id = :conv_id
                """), {"conv_id": conversation_id}).fetchone()

                if result:
                    state = ConversationState(
                        conversation_id=result[0],
                        channel=Channel(result[1]) if result[1] else channel,
                        lead_id=result[2],
                        user_id=result[3]
                    )
                    state.stage = ConversationStage(result[4]) if result[4] else ConversationStage.GREETING
                    state.qualification_data = result[5] or {}
                    state.message_count = result[6] or 0
                    state.last_message_at = result[7]
                    self._conversation_cache[conversation_id] = state
                    return state
            except Exception as e:
                logger.warning(f"Could not load conversation from database: {e}")

        state = ConversationState(
            conversation_id=conversation_id,
            channel=channel,
            lead_id=lead_id,
            user_id=user_id
        )
        self._conversation_cache[conversation_id] = state
        return state

    def process_message(
        self,
        conversation_id: str,
        message: str,
        channel: Channel,
        direction: str = "inbound",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process an incoming or outgoing message.
        Returns analysis and suggested response.
        """
        state = self.get_or_create_conversation(conversation_id, channel)
        state.message_count += 1
        state.last_message_at = datetime.now()

        # Analyze tone
        tone = analyze_tone(message)
        state.last_tone = tone
        state.tone_history.append({
            "timestamp": datetime.now().isoformat(),
            "direction": direction,
            "tone_summary": {
                "emotion": tone.emotional_state["primary_emotion"],
                "sentiment": tone.sentiment["sentiment_category"],
                "urgency": tone.urgency["urgency_level"]
            }
        })

        # Check for objections
        has_objection, objection_type = check_for_objections(message)
        if has_objection:
            state.objection_count += 1
            if objection_type:
                state.objections_handled.append(objection_type)

        # Extract qualification data
        state.qualification_data = extract_qualification_data(
            message,
            state.qualification_data
        )

        # Update qualification status
        completion = state.qualification_data.get_completion_percentage()
        if completion == 0:
            state.qualification_status = QualificationStatus.NOT_STARTED
        elif completion < 100:
            state.qualification_status = QualificationStatus.IN_PROGRESS
        else:
            state.qualification_status = QualificationStatus.COMPLETE

        # Determine conversation stage
        state.stage = self._determine_stage(state, has_objection)

        # Check for escalation triggers
        should_escalate, escalation_reason = self._check_escalation(state, tone)
        if should_escalate:
            state.stage = ConversationStage.ESCALATED
            state.escalation_reason = escalation_reason
            state.ai_enabled = False

        # Generate response suggestion
        response_suggestion = self._generate_response_suggestion(state, message, has_objection, objection_type)

        return {
            "conversation_id": conversation_id,
            "channel": channel.value,
            "original_message": message,  # Include original message for question detection
            "tone_analysis": tone.to_dict(),
            "qualification": {
                "status": state.qualification_status.value,
                "completion_percentage": completion,
                "data": state.qualification_data.to_dict(),
                "missing_fields": state.qualification_data.get_missing_required()
            },
            "conversation_state": {
                "stage": state.stage.value,
                "message_count": state.message_count,
                "objection_count": state.objection_count,
                "ai_enabled": state.ai_enabled
            },
            "objection_detected": has_objection,
            "objection_type": objection_type,
            "should_escalate": should_escalate,
            "escalation_reason": escalation_reason,
            "response_suggestion": response_suggestion,
            "next_question": get_next_qualification_question(state.qualification_data, channel)
        }

    def _determine_stage(self, state: ConversationState, has_objection: bool) -> ConversationStage:
        """Determine the current conversation stage."""
        if state.stage == ConversationStage.ESCALATED:
            return ConversationStage.ESCALATED

        if state.qualification_status == QualificationStatus.COMPLETE:
            return ConversationStage.BOOKING

        if has_objection and state.objection_count <= 3:
            return ConversationStage.OBJECTION_HANDLING

        if has_objection and state.objection_count > 3:
            return ConversationStage.NURTURE

        if state.qualification_status == QualificationStatus.IN_PROGRESS:
            return ConversationStage.QUALIFICATION

        if state.message_count <= 2:
            return ConversationStage.INITIAL_CONTACT

        return ConversationStage.QUALIFICATION

    def _check_escalation(self, state: ConversationState, tone: ToneAnalysis) -> Tuple[bool, Optional[str]]:
        """Check if conversation should be escalated to human."""
        reasons = []

        # High-risk tone
        if tone.risk_level == "high":
            reasons.append("high_risk_tone")

        # Critical urgency
        if tone.urgency["urgency_level"] == "critical":
            reasons.append("critical_urgency")

        # Angry emotion
        if tone.emotional_state["primary_emotion"] == "angry":
            reasons.append("angry_customer")

        # Too many objections
        if state.objection_count > 3:
            reasons.append("excessive_objections")

        # Legal/escalation keywords
        legal_keywords = ["attorney", "lawyer", "sue", "legal", "supervisor", "manager", "complaint"]
        if any(kw in str(state.last_tone) for kw in legal_keywords):
            reasons.append("legal_escalation_requested")

        if reasons:
            return True, ", ".join(reasons)
        return False, None

    def _generate_response_suggestion(
        self,
        state: ConversationState,
        message: str,
        has_objection: bool,
        objection_type: Optional[str]
    ) -> Dict[str, Any]:
        """Generate a suggested response based on conversation state."""

        suggestion = {
            "type": "qualification",
            "tone": "professional",
            "key_points": [],
            "sample_response": None
        }

        # Handle objections
        if has_objection and objection_type:
            suggestion["type"] = "objection_handling"
            objection_responses = {
                "not_interested": {
                    "tone": "respectful_persistent",
                    "points": ["Acknowledge their response", "Ask one clarifying question", "Offer value"],
                    "sample": "I understand - just curious, is it the timing that's not right, or are you already working with someone?"
                },
                "bad_timing": {
                    "tone": "understanding",
                    "points": ["Acknowledge timing", "Offer to follow up later", "Leave door open"],
                    "sample": "No problem at all. When would be a better time for me to reach back out?"
                },
                "using_another": {
                    "tone": "confident_helpful",
                    "points": ["Don't criticize competitor", "Offer comparison", "Highlight unique value"],
                    "sample": "That's great you're already working on this. Have they locked your rate yet? I'd be happy to provide a second opinion to make sure you're getting the best deal."
                },
                "rate_concern": {
                    "tone": "informative",
                    "points": ["Address rate concerns", "Explain rate factors", "Offer rate watch"],
                    "sample": "Rates have been moving - would you like me to set you up with rate alerts so you know the moment rates hit your target?"
                },
                "not_ready": {
                    "tone": "patient_helpful",
                    "points": ["No pressure", "Offer resources", "Stay connected"],
                    "sample": "Totally understand - it's a big decision. Would it help if I sent you some info on the process so you're prepared when the time is right?"
                }
            }

            if objection_type in objection_responses:
                resp = objection_responses[objection_type]
                suggestion["tone"] = resp["tone"]
                suggestion["key_points"] = resp["points"]
                suggestion["sample_response"] = resp["sample"]

        # Generate qualification response
        elif state.stage in [ConversationStage.INITIAL_CONTACT, ConversationStage.QUALIFICATION]:
            next_q = get_next_qualification_question(state.qualification_data, state.channel)
            if next_q:
                suggestion["type"] = "qualification"
                suggestion["key_points"] = ["Ask ONE question at a time", "Keep it conversational", "Under 60 words"]
                suggestion["sample_response"] = next_q

        # Booking stage
        elif state.stage == ConversationStage.BOOKING:
            suggestion["type"] = "booking"
            suggestion["key_points"] = ["Offer specific times", "Make it easy to schedule", "Confirm next steps"]
            if state.channel == Channel.SMS:
                suggestion["sample_response"] = "Great! I'd love to get you connected with a loan officer. Are you free for a quick 10-min call tomorrow at 10am or 2pm?"
            else:
                suggestion["sample_response"] = "Excellent! Based on what you've shared, I think we can definitely help. Would you have time for a quick 15-minute call with one of our loan officers? They can give you exact numbers and answer any questions. What times work best for you this week?"

        return suggestion

    def get_conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        """Get a summary of the conversation state."""
        if conversation_id not in self._conversation_cache:
            return {"error": "Conversation not found"}

        state = self._conversation_cache[conversation_id]

        # Calculate tone trends
        tone_trend = "stable"
        if len(state.tone_history) >= 3:
            recent_sentiments = [t["tone_summary"]["sentiment"] for t in state.tone_history[-3:]]
            if all("negative" in s for s in recent_sentiments):
                tone_trend = "declining"
            elif all("positive" in s for s in recent_sentiments):
                tone_trend = "improving"

        return {
            "conversation_id": conversation_id,
            "channel": state.channel.value,
            "stage": state.stage.value,
            "message_count": state.message_count,
            "qualification": {
                "status": state.qualification_status.value,
                "completion": state.qualification_data.get_completion_percentage(),
                "collected_fields": list(state.qualification_data.collected_at.keys())
            },
            "tone": {
                "current": state.last_tone.to_dict() if state.last_tone else None,
                "trend": tone_trend,
                "history_length": len(state.tone_history)
            },
            "objections": {
                "count": state.objection_count,
                "types": state.objections_handled
            },
            "ai_enabled": state.ai_enabled,
            "escalation_reason": state.escalation_reason,
            "lead_id": state.lead_id
        }


# =============================================================================
# MODULE-LEVEL FUNCTIONS FOR EASY ACCESS
# =============================================================================

# Singleton instance
_service_instance: Optional[ConversationIntelligenceService] = None


def get_conversation_service() -> ConversationIntelligenceService:
    """Get or create the singleton conversation intelligence service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ConversationIntelligenceService()
    return _service_instance


def process_inbound_message(
    conversation_id: str,
    message: str,
    channel: str,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """Process an inbound message from any channel."""
    service = get_conversation_service()
    return service.process_message(
        conversation_id=conversation_id,
        message=message,
        channel=Channel(channel),
        direction="inbound",
        metadata=metadata
    )


def get_tone_analysis(text: str) -> Dict[str, Any]:
    """Quick tone analysis without conversation context."""
    return analyze_tone(text).to_dict()


def extract_lead_data(text: str) -> Dict[str, Any]:
    """Extract qualification/lead data from text."""
    data = extract_qualification_data(text)
    return data.to_dict()
