"""
Perennia AI - Email Intelligence Tools
======================================
Tools for the Email Intelligence Agent handling email analysis and automation.
Includes advanced tone analysis for emotional state, communication style,
sentiment intensity, and thread-level tone trends.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
)


# =============================================================================
# TONE ANALYSIS CONFIGURATION
# =============================================================================

# Emotional state keywords with weights
EMOTIONAL_INDICATORS = {
    "frustrated": {
        "keywords": ["frustrated", "frustrating", "annoying", "annoyed", "irritated",
                    "fed up", "sick of", "tired of", "waste of time", "ridiculous",
                    "unacceptable", "disappointing", "let down"],
        "intensity": 0.8,
        "category": "negative"
    },
    "confused": {
        "keywords": ["confused", "confusing", "don't understand", "unclear", "lost",
                    "what do you mean", "not sure", "can you explain", "i thought",
                    "makes no sense", "contradicting", "mixed signals"],
        "intensity": 0.5,
        "category": "neutral"
    },
    "excited": {
        "keywords": ["excited", "thrilled", "can't wait", "looking forward", "amazing",
                    "wonderful", "fantastic", "great news", "so happy", "love this",
                    "perfect", "exactly what", "dream come true"],
        "intensity": 0.9,
        "category": "positive"
    },
    "satisfied": {
        "keywords": ["satisfied", "happy with", "pleased", "good job", "well done",
                    "thank you", "appreciate", "grateful", "helpful", "smooth",
                    "easy process", "great service", "recommend"],
        "intensity": 0.7,
        "category": "positive"
    },
    "angry": {
        "keywords": ["angry", "furious", "outraged", "unbelievable", "terrible",
                    "worst", "never again", "lawsuit", "attorney", "complain",
                    "supervisor", "manager", "escalate", "demand"],
        "intensity": 1.0,
        "category": "negative"
    },
    "anxious": {
        "keywords": ["worried", "concerned", "nervous", "anxious", "scared",
                    "uncertain", "what if", "afraid", "stressed", "overwhelming",
                    "too much", "deadline", "running out of time"],
        "intensity": 0.6,
        "category": "negative"
    },
    "grateful": {
        "keywords": ["thank you so much", "really appreciate", "grateful", "blessed",
                    "couldn't have done", "lifesaver", "above and beyond", "exceptional",
                    "outstanding", "made my day"],
        "intensity": 0.85,
        "category": "positive"
    },
    "hopeful": {
        "keywords": ["hope", "hopefully", "looking forward", "optimistic", "fingers crossed",
                    "excited about", "can't wait to", "eager", "anticipating"],
        "intensity": 0.6,
        "category": "positive"
    },
    "disappointed": {
        "keywords": ["disappointed", "let down", "expected more", "not what i wanted",
                    "underwhelming", "fell short", "promised", "was told", "supposed to"],
        "intensity": 0.7,
        "category": "negative"
    },
    "impatient": {
        "keywords": ["still waiting", "how long", "when will", "been waiting", "follow up",
                    "no response", "haven't heard", "again", "reminder", "asap", "urgent"],
        "intensity": 0.65,
        "category": "negative"
    }
}

# Communication style indicators
STYLE_INDICATORS = {
    "formal": {
        "keywords": ["dear", "sincerely", "regards", "respectfully", "hereby",
                    "pursuant", "kindly", "would you please", "i am writing to"],
        "patterns": [r"dear\s+(mr|mrs|ms|dr)\.", r"yours\s+(sincerely|truly|faithfully)"]
    },
    "casual": {
        "keywords": ["hey", "hi there", "thanks!", "cool", "awesome", "no worries",
                    "gonna", "wanna", "btw", "fyi", "asap", "lol", "haha"],
        "patterns": [r"!\s*$", r"\.{3,}", r"\?{2,}"]
    },
    "urgent": {
        "keywords": ["urgent", "asap", "immediately", "emergency", "critical",
                    "time sensitive", "deadline", "today", "right now", "rush"],
        "patterns": [r"!{2,}", r"URGENT", r"ASAP", r"\*\*[^*]+\*\*"]
    },
    "demanding": {
        "keywords": ["need", "must", "require", "expect", "demand", "insist",
                    "non-negotiable", "unacceptable", "will not", "have to"],
        "patterns": [r"i\s+(need|want|expect|require)", r"you\s+(must|need to|have to)"]
    },
    "friendly": {
        "keywords": ["hope you're well", "how are you", "nice to", "pleasure",
                    "wonderful", "lovely", "happy to help", "feel free", "anytime"],
        "patterns": [r":\)|:\-\)|<3", r"hope\s+(you're|your|this finds)"]
    },
    "professional": {
        "keywords": ["please advise", "at your earliest convenience", "following up",
                    "as discussed", "per our conversation", "attached please find",
                    "for your review", "kindly confirm"],
        "patterns": [r"please\s+(advise|confirm|let me know)", r"as\s+(per|discussed)"]
    }
}

# Intensity modifiers
INTENSITY_AMPLIFIERS = ["very", "extremely", "really", "absolutely", "totally",
                        "completely", "incredibly", "so", "super", "highly"]
INTENSITY_DIMINISHERS = ["somewhat", "slightly", "a bit", "kind of", "sort of",
                         "fairly", "rather", "maybe", "possibly", "perhaps"]


def _analyze_emotional_state(text: str) -> Dict[str, Any]:
    """Analyze text for emotional state indicators."""
    text_lower = text.lower()
    detected_emotions = {}

    for emotion, config in EMOTIONAL_INDICATORS.items():
        score = 0
        matches = []

        for keyword in config["keywords"]:
            if keyword in text_lower:
                # Check for intensity modifiers
                base_score = config["intensity"]

                # Look for amplifiers before the keyword
                for amp in INTENSITY_AMPLIFIERS:
                    if f"{amp} {keyword}" in text_lower or f"{amp} {keyword[0]}" in text_lower:
                        base_score = min(1.0, base_score * 1.3)
                        break

                # Look for diminishers
                for dim in INTENSITY_DIMINISHERS:
                    if f"{dim} {keyword}" in text_lower:
                        base_score = base_score * 0.7
                        break

                score += base_score
                matches.append(keyword)

        if score > 0:
            detected_emotions[emotion] = {
                "score": min(1.0, score),
                "matches": matches,
                "category": config["category"]
            }

    # Determine primary emotion (with priority ordering for ties)
    # Priority: angry > frustrated > disappointed > anxious > impatient > confused > grateful > excited > satisfied > hopeful
    emotion_priority = {
        "angry": 10, "frustrated": 9, "disappointed": 8, "anxious": 7,
        "impatient": 6, "confused": 5, "grateful": 4, "excited": 3,
        "satisfied": 2, "hopeful": 1
    }

    if detected_emotions:
        # Sort by score first, then by priority for ties
        primary = max(
            detected_emotions.items(),
            key=lambda x: (x[1]["score"], emotion_priority.get(x[0], 0))
        )
        return {
            "primary_emotion": primary[0],
            "primary_score": round(primary[1]["score"], 2),
            "primary_category": primary[1]["category"],
            "all_emotions": {k: round(v["score"], 2) for k, v in detected_emotions.items()},
            "emotion_matches": {k: v["matches"] for k, v in detected_emotions.items()}
        }

    return {
        "primary_emotion": "neutral",
        "primary_score": 0.5,
        "primary_category": "neutral",
        "all_emotions": {},
        "emotion_matches": {}
    }


def _analyze_communication_style(text: str) -> Dict[str, Any]:
    """Analyze text for communication style."""
    text_lower = text.lower()
    style_scores = {}

    for style, config in STYLE_INDICATORS.items():
        score = 0
        matches = []

        # Check keywords
        for keyword in config["keywords"]:
            if keyword in text_lower:
                score += 0.3
                matches.append(keyword)

        # Check patterns
        for pattern in config["patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                score += 0.4
                matches.append(f"pattern:{pattern[:20]}")

        if score > 0:
            style_scores[style] = {
                "score": min(1.0, score),
                "matches": matches
            }

    # Determine primary style
    if style_scores:
        primary = max(style_scores.items(), key=lambda x: x[1]["score"])
        secondary = None
        sorted_styles = sorted(style_scores.items(), key=lambda x: x[1]["score"], reverse=True)
        if len(sorted_styles) > 1 and sorted_styles[1][1]["score"] > 0.3:
            secondary = sorted_styles[1][0]

        return {
            "primary_style": primary[0],
            "primary_score": round(primary[1]["score"], 2),
            "secondary_style": secondary,
            "all_styles": {k: round(v["score"], 2) for k, v in style_scores.items()}
        }

    return {
        "primary_style": "neutral",
        "primary_score": 0.5,
        "secondary_style": None,
        "all_styles": {}
    }


def _calculate_sentiment_intensity(text: str) -> Dict[str, Any]:
    """Calculate detailed sentiment with intensity scoring."""
    text_lower = text.lower()

    # Extended sentiment lexicon with weights
    positive_lexicon = {
        "excellent": 0.9, "amazing": 0.9, "wonderful": 0.85, "fantastic": 0.85,
        "great": 0.7, "good": 0.5, "nice": 0.4, "fine": 0.3, "okay": 0.2,
        "thank": 0.6, "thanks": 0.6, "appreciate": 0.7, "grateful": 0.8,
        "helpful": 0.6, "perfect": 0.9, "love": 0.8, "happy": 0.7,
        "pleased": 0.6, "satisfied": 0.6, "impressed": 0.7, "delighted": 0.8,
        "smooth": 0.5, "easy": 0.4, "quick": 0.4, "efficient": 0.5
    }

    negative_lexicon = {
        "terrible": 0.9, "horrible": 0.9, "awful": 0.85, "worst": 0.9,
        "bad": 0.6, "poor": 0.6, "disappointing": 0.7, "frustrated": 0.8,
        "angry": 0.85, "upset": 0.7, "annoyed": 0.6, "irritated": 0.6,
        "problem": 0.5, "issue": 0.4, "error": 0.5, "mistake": 0.5,
        "wrong": 0.5, "failed": 0.6, "broken": 0.6, "unacceptable": 0.8,
        "ridiculous": 0.7, "incompetent": 0.8, "unprofessional": 0.7,
        "slow": 0.4, "confusing": 0.5, "difficult": 0.4, "complicated": 0.4
    }

    # Calculate scores
    pos_score = 0
    neg_score = 0
    pos_matches = []
    neg_matches = []

    words = re.findall(r'\b\w+\b', text_lower)

    for word in words:
        if word in positive_lexicon:
            weight = positive_lexicon[word]
            # Check for negation
            word_pos = text_lower.find(word)
            context = text_lower[max(0, word_pos-20):word_pos]
            if any(neg in context for neg in ["not", "don't", "doesn't", "didn't", "never", "no"]):
                neg_score += weight * 0.5
            else:
                pos_score += weight
                pos_matches.append(word)

        if word in negative_lexicon:
            weight = negative_lexicon[word]
            neg_score += weight
            neg_matches.append(word)

    # Check for amplifiers affecting overall sentiment
    for amp in INTENSITY_AMPLIFIERS:
        if amp in text_lower:
            pos_score *= 1.1
            neg_score *= 1.1

    # Normalize scores
    total = pos_score + neg_score
    if total > 0:
        pos_normalized = pos_score / total
        neg_normalized = neg_score / total
    else:
        pos_normalized = 0.5
        neg_normalized = 0.5

    # Calculate overall sentiment and intensity
    sentiment_score = pos_score - neg_score
    raw_intensity = abs(sentiment_score)

    # Map to intensity levels
    if raw_intensity < 0.3:
        intensity_level = "mild"
    elif raw_intensity < 0.8:
        intensity_level = "moderate"
    elif raw_intensity < 1.5:
        intensity_level = "strong"
    else:
        intensity_level = "very_strong"

    # Determine sentiment category (adjusted thresholds)
    if sentiment_score > 2.0:
        sentiment_category = "very_positive"
    elif sentiment_score > 0.8:
        sentiment_category = "positive"
    elif sentiment_score > 0.2:
        sentiment_category = "slightly_positive"
    elif sentiment_score > -0.2:
        sentiment_category = "neutral"
    elif sentiment_score > -0.8:
        sentiment_category = "slightly_negative"
    elif sentiment_score > -2.0:
        sentiment_category = "negative"
    else:
        sentiment_category = "very_negative"

    return {
        "sentiment_category": sentiment_category,
        "sentiment_score": round(sentiment_score, 2),
        "intensity_level": intensity_level,
        "intensity_score": round(min(1.0, raw_intensity / 2), 2),
        "positive_score": round(pos_score, 2),
        "negative_score": round(neg_score, 2),
        "positive_words": pos_matches[:10],
        "negative_words": neg_matches[:10],
        "confidence": round(min(1.0, total / 3), 2)
    }


def _detect_urgency_level(text: str) -> Dict[str, Any]:
    """Detect urgency level with more granularity."""
    text_lower = text.lower()

    urgency_indicators = {
        "critical": ["emergency", "urgent", "asap", "immediately", "right now",
                    "critical", "time sensitive", "expires today", "last chance"],
        "high": ["today", "tomorrow", "by end of day", "as soon as possible",
                "deadline", "time is running out", "don't delay", "quickly"],
        "medium": ["this week", "soon", "when you can", "at your earliest",
                  "follow up", "reminder", "checking in"],
        "low": ["whenever", "no rush", "when you have time", "at your convenience",
               "just wanted to", "fyi", "for your information"]
    }

    detected_level = "normal"
    matches = []

    for level in ["critical", "high", "medium", "low"]:
        for indicator in urgency_indicators[level]:
            if indicator in text_lower:
                matches.append(indicator)
                if detected_level == "normal" or (level == "critical") or \
                   (level == "high" and detected_level not in ["critical"]) or \
                   (level == "medium" and detected_level == "low"):
                    detected_level = level

    # Check for multiple exclamation marks (indicates urgency)
    if text.count("!") >= 3:
        if detected_level == "normal":
            detected_level = "medium"
        elif detected_level == "medium":
            detected_level = "high"

    # Check for ALL CAPS (indicates urgency/shouting)
    caps_ratio = sum(1 for c in text if c.isupper()) / max(1, len(text))
    if caps_ratio > 0.3:
        if detected_level in ["normal", "low"]:
            detected_level = "medium"
        elif detected_level == "medium":
            detected_level = "high"

    urgency_score = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2, "normal": 0.3}

    return {
        "urgency_level": detected_level,
        "urgency_score": urgency_score.get(detected_level, 0.3),
        "urgency_indicators": matches[:5],
        "has_caps_emphasis": caps_ratio > 0.3,
        "exclamation_count": text.count("!")
    }


# =============================================================================
# Email Intelligence Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="parse_email",
    description="Parse email content to extract intent, entities, sentiment, and detailed tone analysis including emotional state, communication style, and intensity",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "subject": "Email subject",
        "body": "Email body",
        "from_email": "Sender email",
        "attachments": "List of attachment names",
        "include_tone_analysis": "Include detailed tone analysis (default True)",
    },
)
def parse_email(
    subject: str,
    body: str,
    from_email: str,
    attachments: Optional[List[str]] = None,
    include_tone_analysis: bool = True,
) -> ToolResult:
    """Parse email for intent, entities, and comprehensive tone analysis."""
    full_text = f"{subject} {body}"
    text = full_text.lower()

    # Intent detection
    intents = []
    intent_patterns = {
        "rate_inquiry": ["rate", "interest rate", "apr", "points", "current rate"],
        "status_check": ["status", "update", "where are we", "how long", "when will"],
        "document_submission": ["attached", "sending", "here are", "documents", "upload"],
        "question": ["?", "question", "wondering", "curious", "can you explain"],
        "complaint": ["frustrated", "upset", "disappointed", "problem", "issue"],
        "schedule_request": ["schedule", "meet", "call me", "available", "appointment"],
        "urgent": ["urgent", "asap", "immediately", "rush", "time sensitive"],
        "thank_you": ["thank you", "thanks", "appreciate", "grateful"],
        "follow_up": ["following up", "checking in", "just wanted to", "any update"],
    }

    for intent, keywords in intent_patterns.items():
        if any(kw in text for kw in keywords):
            intents.append(intent)

    # Entity extraction
    entities = {
        "dates": re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}', text),
        "amounts": re.findall(r'\$[\d,]+(?:\.\d{2})?', text),
        "phone_numbers": re.findall(r'(?:\+1)?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', text),
        "loan_numbers": re.findall(r'(?:loan|file|case)[\s#:]*([A-Z0-9-]+)', text, re.IGNORECASE),
    }

    # Enhanced tone analysis
    if include_tone_analysis:
        emotional_state = _analyze_emotional_state(full_text)
        communication_style = _analyze_communication_style(full_text)
        sentiment_intensity = _calculate_sentiment_intensity(full_text)
        urgency_analysis = _detect_urgency_level(full_text)

        tone_analysis = {
            "emotional_state": {
                "primary": emotional_state["primary_emotion"],
                "score": emotional_state["primary_score"],
                "category": emotional_state["primary_category"],
                "all_detected": emotional_state["all_emotions"]
            },
            "communication_style": {
                "primary": communication_style["primary_style"],
                "secondary": communication_style["secondary_style"],
                "score": communication_style["primary_score"]
            },
            "sentiment": {
                "category": sentiment_intensity["sentiment_category"],
                "score": sentiment_intensity["sentiment_score"],
                "intensity": sentiment_intensity["intensity_level"],
                "confidence": sentiment_intensity["confidence"]
            },
            "urgency": {
                "level": urgency_analysis["urgency_level"],
                "score": urgency_analysis["urgency_score"],
                "indicators": urgency_analysis["urgency_indicators"]
            }
        }

        # Simple sentiment for backward compatibility
        sentiment = sentiment_intensity["sentiment_category"].replace("very_", "").replace("slightly_", "")
        urgency = urgency_analysis["urgency_level"]
    else:
        # Legacy simple analysis
        positive_words = ["thank", "great", "happy", "appreciate", "excellent"]
        negative_words = ["frustrated", "upset", "problem", "issue", "disappointed"]
        pos_count = sum(1 for w in positive_words if w in text)
        neg_count = sum(1 for w in negative_words if w in text)

        if neg_count > pos_count:
            sentiment = "negative"
        elif pos_count > neg_count:
            sentiment = "positive"
        else:
            sentiment = "neutral"

        urgency = "high" if "urgent" in intents or "complaint" in intents else "normal"
        tone_analysis = None

    # Determine response priority based on tone
    response_priority = "normal"
    if include_tone_analysis:
        if urgency_analysis["urgency_level"] in ["critical", "high"]:
            response_priority = "high"
        elif emotional_state["primary_emotion"] in ["angry", "frustrated"]:
            response_priority = "high"
        elif emotional_state["primary_category"] == "negative":
            response_priority = "elevated"

    # Suggested response tone based on incoming tone
    suggested_response_tone = "professional"
    if include_tone_analysis:
        if emotional_state["primary_emotion"] in ["angry", "frustrated"]:
            suggested_response_tone = "empathetic_professional"
        elif emotional_state["primary_emotion"] in ["anxious", "confused"]:
            suggested_response_tone = "reassuring"
        elif emotional_state["primary_emotion"] in ["excited", "grateful"]:
            suggested_response_tone = "warm_professional"
        elif communication_style["primary_style"] == "casual":
            suggested_response_tone = "friendly_professional"
        elif communication_style["primary_style"] == "formal":
            suggested_response_tone = "formal"

    parsed = {
        "from_email": from_email,
        "subject": subject,
        "intents": intents,
        "primary_intent": intents[0] if intents else "general",
        "entities": entities,
        "sentiment": sentiment,
        "urgency": urgency,
        "has_attachments": bool(attachments),
        "attachment_count": len(attachments) if attachments else 0,
        "attachment_names": attachments or [],
        "requires_response": len(intents) > 0 and "document_submission" not in intents,
        "auto_reply_eligible": "document_submission" in intents or sentiment == "positive",
        "response_priority": response_priority,
        "suggested_response_tone": suggested_response_tone,
    }

    # Add detailed tone analysis if enabled
    if tone_analysis:
        parsed["tone_analysis"] = tone_analysis

    message = f"Intent: {parsed['primary_intent']}, Sentiment: {sentiment}"
    if include_tone_analysis:
        message += f", Emotion: {emotional_state['primary_emotion']}, Style: {communication_style['primary_style']}"

    return ToolResult.success(
        data=parsed,
        message=message,
    )


@mortgage_tool(
    name="get_email_thread",
    description="Get email thread history with a contact",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "contact_id": "Contact ID",
        "contact_type": "Type: lead, borrower",
        "limit": "Max emails to retrieve",
    },
)
def get_email_thread(
    contact_id: str,
    contact_type: str = "lead",
    limit: int = 20,
) -> ToolResult:
    """Get email thread with contact."""
    emails = execute_query("""
        SELECT
            id, direction, subject, body_preview,
            sent_at, read_at, replied_at, attachments
        FROM email_history
        WHERE contact_id = :contact_id AND contact_type = :contact_type
        ORDER BY sent_at DESC
        LIMIT :limit
    """, {"contact_id": contact_id, "contact_type": contact_type, "limit": limit})

    if not emails:
        emails = []

    # Get contact info
    if contact_type == "lead":
        contact = execute_single(
            "SELECT first_name, last_name, email FROM leads WHERE id = :id",
            {"id": contact_id}
        )
    else:
        contact = execute_single(
            "SELECT borrower_name as name, borrower_email as email FROM loans WHERE id = :id",
            {"id": contact_id}
        )

    thread = {
        "contact_id": contact_id,
        "contact_type": contact_type,
        "contact_name": f"{contact.get('first_name', '')} {contact.get('last_name', contact.get('name', ''))}".strip() if contact else "Unknown",
        "contact_email": contact.get("email") if contact else None,
        "total_emails": len(emails),
        "emails": [
            {
                "id": e.get("id"),
                "direction": e.get("direction", "outbound"),
                "subject": e.get("subject"),
                "preview": e.get("body_preview", "")[:200],
                "sent_at": format_date(e.get("sent_at")),
                "read": e.get("read_at") is not None,
                "replied": e.get("replied_at") is not None,
                "has_attachments": bool(e.get("attachments")),
            }
            for e in emails
        ],
        "summary": {
            "inbound": len([e for e in emails if e.get("direction") == "inbound"]),
            "outbound": len([e for e in emails if e.get("direction") == "outbound"]),
            "unread": len([e for e in emails if not e.get("read_at")]),
        },
    }

    return ToolResult.success(
        data=thread,
        message=f"Thread: {len(emails)} emails",
    )


@mortgage_tool(
    name="draft_email_response",
    description="Draft email response based on context and templates",
    agent_roles=["email_intelligence"],
    risk_level="MEDIUM",
    parameters={
        "contact_id": "Contact ID",
        "contact_type": "Type: lead, borrower",
        "response_type": "Type: acknowledgment, status_update, document_request, follow_up",
        "original_subject": "Subject of original email",
        "context": "Additional context for response",
        "template_id": "Optional template ID to use",
    },
)
def draft_email_response(
    contact_id: str,
    contact_type: str = "lead",
    response_type: str = "acknowledgment",
    original_subject: Optional[str] = None,
    context: Optional[str] = None,
    template_id: Optional[str] = None,
) -> ToolResult:
    """Draft email response."""
    # Get contact info
    if contact_type == "lead":
        contact = execute_single(
            "SELECT first_name, last_name, email, stage FROM leads WHERE id = :id",
            {"id": contact_id}
        )
    else:
        contact = execute_single(
            "SELECT borrower_name as first_name, borrower_email as email, stage FROM loans WHERE id = :id",
            {"id": contact_id}
        )

    first_name = contact.get("first_name", "there") if contact else "there"
    stage = contact.get("stage", "processing") if contact else "processing"

    # Response templates
    templates = {
        "acknowledgment": {
            "subject": f"Re: {original_subject}" if original_subject else "Re: Your inquiry",
            "body": f"""Hi {first_name},

Thank you for your email. I've received your message and wanted to let you know I'm looking into this right away.

I'll get back to you with a detailed response within 24 hours.

Best regards""",
        },
        "status_update": {
            "subject": f"Re: {original_subject}" if original_subject else "Loan Status Update",
            "body": f"""Hi {first_name},

Thank you for checking in! I wanted to give you a quick update on your loan.

Your loan is currently in the {stage} stage. Everything is progressing well and on track.

If you have any questions, please don't hesitate to reach out.

Best regards""",
        },
        "document_request": {
            "subject": "Documents Needed for Your Loan",
            "body": f"""Hi {first_name},

I hope this email finds you well. To continue processing your loan, we need the following documents:

[List of documents needed]

Please upload these at your earliest convenience. Let me know if you have any questions.

Best regards""",
        },
        "follow_up": {
            "subject": f"Re: {original_subject}" if original_subject else "Following Up",
            "body": f"""Hi {first_name},

I wanted to follow up on our previous conversation. Have you had a chance to review the information I sent?

I'm here to help if you have any questions.

Best regards""",
        },
    }

    template = templates.get(response_type, templates["acknowledgment"])

    draft = {
        "contact_id": contact_id,
        "contact_type": contact_type,
        "to": contact.get("email") if contact else None,
        "subject": template["subject"],
        "body": template["body"],
        "response_type": response_type,
        "template_id": template_id,
        "context_used": context,
        "status": "draft",
        "created_at": datetime.now().isoformat(),
        "requires_review": True,
    }

    return ToolResult.success(
        data=draft,
        message=f"Draft created for {first_name}",
    )


@mortgage_tool(
    name="send_email",
    description="Send email to contact via Microsoft Graph (if connected) or queue for approval",
    agent_roles=["email_intelligence"],
    risk_level="HIGH",
    parameters={
        "to_email": "Recipient email",
        "subject": "Email subject",
        "body": "Email body",
        "contact_id": "Associated contact ID",
        "contact_type": "Type: lead, borrower",
        "cc": "CC recipients",
        "attachments": "Attachment file IDs",
        "user_id": "User ID sending the email",
    },
)
def send_email(
    to_email: str,
    subject: str,
    body: str,
    contact_id: Optional[str] = None,
    contact_type: str = "lead",
    cc: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
    user_id: Optional[int] = None,
) -> ToolResult:
    """Send email via Microsoft Graph if user has integration, otherwise queue for approval."""
    import uuid
    import asyncio
    import httpx
    import os

    email_id = str(uuid.uuid4())[:8].upper()
    send_status = "queued"
    send_error = None

    # Try to send via Microsoft Graph if user_id provided
    if user_id:
        try:
            from database import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Check for Microsoft OAuth token
                oauth = db.execute(text("""
                    SELECT access_token, refresh_token, token_expires_at
                    FROM microsoft_oauth_tokens
                    WHERE user_id = :user_id
                    AND access_token IS NOT NULL
                    AND sync_enabled = true
                    LIMIT 1
                """), {"user_id": user_id}).fetchone()

                if oauth and oauth.access_token:
                    # Decrypt token
                    from services.calendly_service import decrypt_token
                    access_token = decrypt_token(oauth.access_token)

                    # Check if token expired and needs refresh
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    if oauth.token_expires_at and oauth.token_expires_at.replace(tzinfo=timezone.utc) < now:
                        # Token expired - try to refresh
                        refresh_token = decrypt_token(oauth.refresh_token) if oauth.refresh_token else None
                        if refresh_token:
                            client_id = os.getenv("MICROSOFT_CLIENT_ID")
                            client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
                            tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

                            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

                            import requests
                            refresh_response = requests.post(token_url, data={
                                "client_id": client_id,
                                "client_secret": client_secret,
                                "refresh_token": refresh_token,
                                "grant_type": "refresh_token",
                                "scope": "https://graph.microsoft.com/Mail.Send offline_access",
                            }, timeout=30)

                            if refresh_response.status_code == 200:
                                tokens = refresh_response.json()
                                access_token = tokens["access_token"]

                                # Update stored tokens
                                from services.calendly_service import encrypt_token
                                from datetime import timedelta
                                new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

                                db.execute(text("""
                                    UPDATE microsoft_oauth_tokens
                                    SET access_token = :access_token,
                                        refresh_token = :refresh_token,
                                        token_expires_at = :expires_at,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE user_id = :user_id
                                """), {
                                    "access_token": encrypt_token(access_token),
                                    "refresh_token": encrypt_token(tokens.get("refresh_token", refresh_token)),
                                    "expires_at": new_expires_at,
                                    "user_id": user_id,
                                })
                                db.commit()

                    # Prepare email payload for Microsoft Graph
                    message = {
                        "subject": subject,
                        "body": {
                            "contentType": "HTML",
                            "content": body,
                        },
                        "toRecipients": [
                            {"emailAddress": {"address": to_email}}
                        ],
                    }

                    if cc:
                        message["ccRecipients"] = [
                            {"emailAddress": {"address": email}} for email in cc
                        ]

                    payload = {
                        "message": message,
                        "saveToSentItems": True,
                    }

                    # Send via Graph API
                    import requests
                    response = requests.post(
                        "https://graph.microsoft.com/v1.0/me/sendMail",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        timeout=30,
                    )

                    if response.status_code == 202:  # Accepted
                        send_status = "sent"
                    else:
                        error_data = response.json() if response.content else {}
                        send_error = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                        send_status = "failed"
                else:
                    # No Microsoft integration
                    send_status = "queued"

            finally:
                db.close()

        except Exception as e:
            send_error = str(e)
            send_status = "failed"

    email_data = {
        "email_id": f"EMAIL-{email_id}",
        "to": to_email,
        "cc": cc or [],
        "subject": subject,
        "body": body,
        "contact_id": contact_id,
        "contact_type": contact_type,
        "attachments": attachments or [],
        "status": send_status,
        "sent_at": datetime.now().isoformat() if send_status == "sent" else None,
        "error": send_error,
    }

    if send_status == "sent":
        return ToolResult.success(
            data=email_data,
            message=f"Email sent successfully to {to_email}",
            requires_approval=False,
        )
    elif send_status == "failed":
        return ToolResult.error(
            error=send_error or "Failed to send email",
            message=f"Email failed to send to {to_email}: {send_error}",
        )
    else:
        return ToolResult.success(
            data=email_data,
            message=f"Email queued to {to_email} (connect Microsoft 365 to send directly)",
            requires_approval=True,
        )


@mortgage_tool(
    name="get_email_templates",
    description="Get available email templates",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "category": "Optional category filter",
        "search": "Optional search term",
    },
)
def get_email_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> ToolResult:
    """Get email templates."""
    templates = [
        {
            "id": "tpl_welcome",
            "name": "Welcome Email",
            "category": "onboarding",
            "subject": "Welcome to {company_name}!",
            "preview": "Thank you for choosing us for your home financing...",
            "variables": ["first_name", "company_name", "lo_name"],
        },
        {
            "id": "tpl_status_update",
            "name": "Loan Status Update",
            "category": "status",
            "subject": "Update on Your Loan Application",
            "preview": "I wanted to give you a quick update on your loan...",
            "variables": ["first_name", "stage", "next_steps"],
        },
        {
            "id": "tpl_doc_request",
            "name": "Document Request",
            "category": "documents",
            "subject": "Documents Needed for Your Loan",
            "preview": "To continue processing your loan, we need...",
            "variables": ["first_name", "document_list"],
        },
        {
            "id": "tpl_rate_update",
            "name": "Rate Update",
            "category": "rates",
            "subject": "Great News About Rates!",
            "preview": "I wanted to share some exciting news about rates...",
            "variables": ["first_name", "rate", "savings"],
        },
        {
            "id": "tpl_closing_prep",
            "name": "Closing Preparation",
            "category": "closing",
            "subject": "Preparing for Your Closing",
            "preview": "Congratulations! Your closing is coming up...",
            "variables": ["first_name", "closing_date", "amount_due"],
        },
    ]

    if category:
        templates = [t for t in templates if t["category"] == category]

    if search:
        search_lower = search.lower()
        templates = [t for t in templates if search_lower in t["name"].lower() or search_lower in t["preview"].lower()]

    return ToolResult.success(
        data={
            "templates": templates,
            "count": len(templates),
            "categories": ["onboarding", "status", "documents", "rates", "closing"],
        },
        message=f"Found {len(templates)} templates",
    )


@mortgage_tool(
    name="analyze_email_engagement",
    description="Analyze email engagement metrics",
    agent_roles=["email_intelligence", "team_coach"],
    risk_level="LOW",
    parameters={
        "lo_id": "Optional LO ID filter",
        "period": "Period: week, month, quarter",
        "campaign_id": "Optional campaign filter",
    },
)
def analyze_email_engagement(
    lo_id: Optional[str] = None,
    period: str = "month",
    campaign_id: Optional[str] = None,
) -> ToolResult:
    """Analyze email engagement."""
    # Calculate date range
    today = datetime.now().date()
    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    elif period == "quarter":
        start_date = today - timedelta(days=90)
    else:
        start_date = today - timedelta(days=30)

    engagement = {
        "period": period,
        "date_range": {
            "start": start_date.isoformat(),
            "end": today.isoformat(),
        },
        "summary": {
            "emails_sent": 0,
            "delivered": 0,
            "opened": 0,
            "clicked": 0,
            "replied": 0,
            "bounced": 0,
        },
        "rates": {
            "delivery_rate": 0,
            "open_rate": 0,
            "click_rate": 0,
            "reply_rate": 0,
            "bounce_rate": 0,
        },
        "by_template": [],
        "by_day": [],
        "top_performing_subjects": [],
        "lo_id": lo_id,
        "campaign_id": campaign_id,
    }

    return ToolResult.success(
        data=engagement,
        message=f"Email engagement for {period}",
    )


@mortgage_tool(
    name="match_email_to_loan",
    description="Match incoming email to existing loan/lead record",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "from_email": "Sender email address",
        "subject": "Email subject",
        "body": "Email body for context matching",
    },
)
def match_email_to_loan(
    from_email: str,
    subject: str,
    body: str,
) -> ToolResult:
    """Match email to loan/lead record."""
    # Try to find by email
    lead = execute_single(
        "SELECT id, first_name, last_name, email, stage FROM leads WHERE email = :email",
        {"email": from_email}
    )

    loan = execute_single(
        "SELECT id, loan_number, borrower_name, borrower_email, stage FROM loans WHERE borrower_email = :email OR co_borrower_email = :email",
        {"email": from_email}
    )

    # Try to extract loan number from subject/body
    text = f"{subject} {body}"
    loan_numbers = re.findall(r'(?:loan|file|case)[\s#:]*([A-Z0-9-]+)', text, re.IGNORECASE)

    if loan_numbers and not loan:
        loan = execute_single(
            "SELECT id, loan_number, borrower_name, borrower_email, stage FROM loans WHERE loan_number = :ln",
            {"ln": loan_numbers[0]}
        )

    match_result = {
        "from_email": from_email,
        "matched": lead is not None or loan is not None,
        "match_type": None,
        "lead": None,
        "loan": None,
        "confidence": "none",
    }

    if loan:
        match_result["match_type"] = "loan"
        match_result["loan"] = {
            "id": loan.get("id"),
            "loan_number": loan.get("loan_number"),
            "borrower_name": loan.get("borrower_name"),
            "stage": loan.get("stage"),
        }
        match_result["confidence"] = "high"
    elif lead:
        match_result["match_type"] = "lead"
        match_result["lead"] = {
            "id": lead.get("id"),
            "name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
            "stage": lead.get("stage"),
        }
        match_result["confidence"] = "high"

    return ToolResult.success(
        data=match_result,
        message=f"Match: {match_result['match_type'] or 'none'} ({match_result['confidence']})",
    )


@mortgage_tool(
    name="categorize_email_attachments",
    description="Categorize email attachments for document processing",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "attachments": "List of attachment info (name, size, mime_type)",
    },
)
def categorize_email_attachments(
    attachments: List[Dict[str, Any]],
) -> ToolResult:
    """Categorize email attachments."""
    # Document type patterns
    doc_patterns = {
        "income": ["paystub", "w2", "w-2", "tax return", "1099", "profit", "loss", "income"],
        "assets": ["bank statement", "investment", "401k", "ira", "brokerage"],
        "identity": ["driver", "license", "passport", "ssn", "social security"],
        "property": ["purchase", "contract", "appraisal", "title", "insurance", "hoa"],
        "credit": ["credit report", "explanation", "bankruptcy"],
    }

    categorized = []
    for attachment in attachments:
        name = attachment.get("name", "").lower()
        category = "other"
        confidence = "low"

        for doc_type, patterns in doc_patterns.items():
            if any(p in name for p in patterns):
                category = doc_type
                confidence = "high"
                break

        # Check file extension
        if name.endswith(".pdf"):
            if confidence == "low":
                confidence = "medium"
        elif name.endswith((".jpg", ".jpeg", ".png")):
            if "id" in name or "license" in name:
                category = "identity"
                confidence = "medium"

        categorized.append({
            "name": attachment.get("name"),
            "size": attachment.get("size"),
            "mime_type": attachment.get("mime_type"),
            "category": category,
            "confidence": confidence,
            "suggested_doc_type": f"{category}_document",
        })

    summary = {}
    for item in categorized:
        cat = item["category"]
        summary[cat] = summary.get(cat, 0) + 1

    return ToolResult.success(
        data={
            "attachments": categorized,
            "total": len(categorized),
            "by_category": summary,
            "auto_process_eligible": all(c["confidence"] == "high" for c in categorized),
        },
        message=f"Categorized {len(categorized)} attachments",
    )


@mortgage_tool(
    name="search_email_inbox",
    description="Search user's Microsoft 365 email inbox for messages. Use this when user wants to find specific emails "
                "by sender name, subject, or content. Returns matching emails from Microsoft Graph.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "search_query": "Search term (name, email, subject keywords)",
        "user_id": "User ID to search inbox for",
        "limit": "Maximum results (default 10)",
        "folder": "Folder to search: inbox, sentitems, all (default: all)",
    },
)
def search_email_inbox(
    search_query: str,
    user_id: Optional[int] = None,
    limit: int = 10,
    folder: str = "all",
) -> ToolResult:
    """
    Search user's Microsoft 365 inbox for emails matching the query.
    Uses Microsoft Graph API to search across inbox and sent items.
    """
    import os
    import requests

    if not user_id:
        return ToolResult.error(
            "Unable to search emails: user_id is required. Please ensure you're logged in.",
            ["No user context available for email search"]
        )

    if not search_query or len(search_query.strip()) < 2:
        return ToolResult.error(
            "Search query is too short. Please provide at least 2 characters.",
            ["Invalid search query"]
        )

    try:
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Check for Microsoft OAuth token
            oauth = db.execute(text("""
                SELECT access_token, refresh_token, token_expires_at
                FROM microsoft_oauth_tokens
                WHERE user_id = :user_id
                AND access_token IS NOT NULL
                AND sync_enabled = true
                LIMIT 1
            """), {"user_id": user_id}).fetchone()

            if not oauth or not oauth.access_token:
                return ToolResult.error(
                    "Microsoft 365 not connected. Please connect your email to search your inbox.",
                    ["No Microsoft OAuth token found for user"]
                )

            # Decrypt and possibly refresh token
            from services.calendly_service import decrypt_token, encrypt_token
            from datetime import timezone
            access_token = decrypt_token(oauth.access_token)

            now = datetime.now(timezone.utc)
            if oauth.token_expires_at and oauth.token_expires_at.replace(tzinfo=timezone.utc) < now:
                # Token expired - try to refresh
                refresh_token = decrypt_token(oauth.refresh_token) if oauth.refresh_token else None
                if refresh_token:
                    client_id = os.getenv("MICROSOFT_CLIENT_ID")
                    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
                    tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

                    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                    refresh_response = requests.post(token_url, data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                        "scope": "https://graph.microsoft.com/Mail.Read offline_access",
                    }, timeout=30)

                    if refresh_response.status_code == 200:
                        tokens = refresh_response.json()
                        access_token = tokens["access_token"]

                        # Update stored tokens
                        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
                        db.execute(text("""
                            UPDATE microsoft_oauth_tokens
                            SET access_token = :access_token,
                                refresh_token = :refresh_token,
                                token_expires_at = :expires_at,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = :user_id
                        """), {
                            "access_token": encrypt_token(access_token),
                            "refresh_token": encrypt_token(tokens.get("refresh_token", refresh_token)),
                            "expires_at": new_expires_at,
                            "user_id": user_id,
                        })
                        db.commit()
                    else:
                        return ToolResult.error(
                            "Microsoft 365 token expired. Please reconnect your email.",
                            ["Token refresh failed"]
                        )
                else:
                    return ToolResult.error(
                        "Microsoft 365 token expired. Please reconnect your email.",
                        ["No refresh token available"]
                    )

            # Build Microsoft Graph search query
            # Search in subject, from, body using $search
            search_filter = f'"{search_query}"'

            # Determine which folders to search
            if folder == "inbox":
                endpoint = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
            elif folder == "sentitems":
                endpoint = "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages"
            else:
                # Search all mail
                endpoint = "https://graph.microsoft.com/v1.0/me/messages"

            params = {
                "$search": search_filter,
                "$top": limit,
                "$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,hasAttachments,isRead",
                "$orderby": "receivedDateTime desc",
            }

            response = requests.get(
                endpoint,
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return ToolResult.error(
                    f"Failed to search emails: {error_msg}",
                    [error_msg]
                )

            data = response.json()
            messages = data.get("value", [])

            # Format results
            emails = []
            for msg in messages:
                from_info = msg.get("from", {}).get("emailAddress", {})
                to_info = msg.get("toRecipients", [])

                emails.append({
                    "id": msg.get("id"),
                    "subject": msg.get("subject"),
                    "from_name": from_info.get("name"),
                    "from_email": from_info.get("address"),
                    "to": [r.get("emailAddress", {}).get("address") for r in to_info[:3]],
                    "received": msg.get("receivedDateTime"),
                    "preview": (msg.get("bodyPreview") or "")[:200],
                    "has_attachments": msg.get("hasAttachments", False),
                    "is_read": msg.get("isRead", False),
                })

            if not emails:
                return ToolResult.success(
                    data={
                        "emails": [],
                        "count": 0,
                        "search_query": search_query,
                        "message": f"No emails found matching '{search_query}'",
                    },
                    message=f"No emails found for '{search_query}'"
                )

            return ToolResult.success(
                data={
                    "emails": emails,
                    "count": len(emails),
                    "search_query": search_query,
                    "folder": folder,
                },
                message=f"Found {len(emails)} emails matching '{search_query}'"
            )

        finally:
            db.close()

    except Exception as e:
        return ToolResult.error(
            f"Failed to search emails: {str(e)}",
            [str(e)]
        )


@mortgage_tool(
    name="find_contact_email",
    description="Find a person's email address by searching CRM contacts, leads, team members, and users. "
                "Use this when user wants to email someone and you need their email address. "
                "Searches across: team members/users, leads, loan borrowers, and partners.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "name": "Name to search for (first name, last name, or full name)",
        "user_id": "Current user ID for context",
    },
)
def find_contact_email(
    name: str,
    user_id: Optional[int] = None,
) -> ToolResult:
    """
    Find a contact's email address by searching across all CRM data sources.
    Searches: users/team members, leads, loan borrowers, partners.
    """
    if not name or len(name.strip()) < 2:
        return ToolResult.error(
            "Please provide a name to search for (at least 2 characters).",
            ["Name too short"]
        )

    search_name = name.strip().lower()
    search_parts = search_name.split()

    results = []

    # Search users/team members (names are encrypted — join email_signatures for searchable full_name)
    try:
        users = execute_query("""
            SELECT u.id, COALESCE(es.full_name, u.email) AS name, u.email, u.role
            FROM users u
            LEFT JOIN email_signatures es ON es.user_id = u.id
            WHERE LOWER(COALESCE(es.full_name, '')) LIKE :search
            OR LOWER(u.email) LIKE :search
            OR LOWER(COALESCE(u.team_name, '')) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for u in users:
            if u.get("email"):
                results.append({
                    "type": "team_member",
                    "id": u.get("id"),
                    "name": u.get("name"),
                    "email": u.get("email"),
                    "role": u.get("role"),
                    "match_score": 100 if search_name in (u.get("name") or "").lower() else 80,
                })
    except Exception as e:
        pass

    # Search leads
    try:
        leads = execute_query("""
            SELECT id, name, email, phone, stage
            FROM leads
            WHERE LOWER(name) LIKE :search
            OR LOWER(email) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for l in leads:
            if l.get("email"):
                results.append({
                    "type": "lead",
                    "id": l.get("id"),
                    "name": l.get("name"),
                    "email": l.get("email"),
                    "phone": l.get("phone"),
                    "stage": l.get("stage"),
                    "match_score": 90 if search_name in (l.get("name") or "").lower() else 70,
                })
    except Exception as e:
        pass

    # Search loan borrowers
    try:
        loans = execute_query("""
            SELECT id, loan_number, borrower_name, borrower_email, borrower_phone, stage
            FROM loans
            WHERE LOWER(borrower_name) LIKE :search
            OR LOWER(borrower_email) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for loan in loans:
            if loan.get("borrower_email"):
                results.append({
                    "type": "borrower",
                    "id": loan.get("id"),
                    "loan_number": loan.get("loan_number"),
                    "name": loan.get("borrower_name"),
                    "email": loan.get("borrower_email"),
                    "phone": loan.get("borrower_phone"),
                    "stage": loan.get("stage"),
                    "match_score": 85 if search_name in (loan.get("borrower_name") or "").lower() else 65,
                })
    except Exception as e:
        pass

    # Search referral partners
    try:
        partners = execute_query("""
            SELECT id, name, email, phone, company, type AS partner_type
            FROM referral_partners
            WHERE LOWER(name) LIKE :search
            OR LOWER(email) LIKE :search
            OR LOWER(COALESCE(company, '')) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for p in partners:
            if p.get("email"):
                results.append({
                    "type": "partner",
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "email": p.get("email"),
                    "phone": p.get("phone"),
                    "company": p.get("company"),
                    "partner_type": p.get("partner_type"),
                    "match_score": 75,
                })
    except Exception as e:
        pass

    # Sort by match score
    results.sort(key=lambda x: x.get("match_score", 0), reverse=True)

    # If no CRM results, search user's email inbox
    if not results and user_id:
        inbox_results = _search_inbox_for_contact(name, user_id)
        if inbox_results:
            results.extend(inbox_results)

    if not results:
        return ToolResult.success(
            data={
                "contacts": [],
                "count": 0,
                "search_name": name,
                "message": f"No contacts found matching '{name}' in CRM or email inbox. Try a different spelling.",
            },
            message=f"No contacts found for '{name}'"
        )

    # Return best match prominently
    best_match = results[0]

    return ToolResult.success(
        data={
            "contacts": results[:5],  # Top 5 matches
            "count": len(results),
            "search_name": name,
            "best_match": best_match,
        },
        message=f"Found {best_match['name']} ({best_match['email']}) - {best_match['type']}"
    )


@mortgage_tool(
    name="find_contact_phone",
    description="Find a person's phone number by searching CRM contacts, leads, team members, and users. "
                "Use this when user wants to text/SMS someone and you need their phone number. "
                "Searches across: team members/users, leads, loan borrowers, and partners.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "name": "Name to search for (first name, last name, or full name)",
        "user_id": "Current user ID for context",
    },
)
def find_contact_phone(
    name: str,
    user_id: Optional[int] = None,
) -> ToolResult:
    """
    Find a contact's phone number by searching across all CRM data sources.
    Searches: users/team members, leads, loan borrowers, partners.
    """
    if not name or len(name.strip()) < 2:
        return ToolResult.error(
            "Please provide a name to search for (at least 2 characters).",
            ["Name too short"]
        )

    search_name = name.strip().lower()
    results = []

    # Search users/team members (names are encrypted — join email_signatures for searchable full_name)
    try:
        users = execute_query("""
            SELECT u.id, COALESCE(es.full_name, u.email) AS name, u.email, u.role
            FROM users u
            LEFT JOIN email_signatures es ON es.user_id = u.id
            WHERE LOWER(COALESCE(es.full_name, '')) LIKE :search
            OR LOWER(u.email) LIKE :search
            OR LOWER(COALESCE(u.team_name, '')) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for u in users:
            results.append({
                "type": "team_member",
                "id": u.get("id"),
                "name": u.get("name"),
                "email": u.get("email"),
                "role": u.get("role"),
                "match_score": 100 if search_name in (u.get("name") or "").lower() else 80,
            })
    except Exception as e:
        logger.error(f"Error searching team members in find_contact_phone: {e}")

    # Search leads
    try:
        leads = execute_query("""
            SELECT id, name, email, phone, stage
            FROM leads
            WHERE LOWER(name) LIKE :search
            OR LOWER(email) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for l in leads:
            if l.get("phone"):
                results.append({
                    "type": "lead",
                    "id": l.get("id"),
                    "name": l.get("name"),
                    "phone": l.get("phone"),
                    "email": l.get("email"),
                    "stage": l.get("stage"),
                    "match_score": 90 if search_name in (l.get("name") or "").lower() else 70,
                })
    except Exception as e:
        logger.error(f"Error searching leads in find_contact_phone: {e}")

    # Search loan borrowers
    try:
        loans = execute_query("""
            SELECT id, loan_number, borrower_name, borrower_email, borrower_phone, stage
            FROM loans
            WHERE LOWER(borrower_name) LIKE :search
            OR LOWER(borrower_email) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for loan in loans:
            if loan.get("borrower_phone"):
                results.append({
                    "type": "borrower",
                    "id": loan.get("id"),
                    "loan_number": loan.get("loan_number"),
                    "name": loan.get("borrower_name"),
                    "phone": loan.get("borrower_phone"),
                    "email": loan.get("borrower_email"),
                    "stage": loan.get("stage"),
                    "match_score": 85 if search_name in (loan.get("borrower_name") or "").lower() else 65,
                })
    except Exception as e:
        logger.error(f"Error searching loan borrowers in find_contact_phone: {e}")

    # Search referral partners
    try:
        partners = execute_query("""
            SELECT id, name, email, phone, company, type AS partner_type
            FROM referral_partners
            WHERE LOWER(name) LIKE :search
            OR LOWER(email) LIKE :search
            OR LOWER(COALESCE(company, '')) LIKE :search
            LIMIT 10
        """, {"search": f"%{search_name}%"})

        for p in partners:
            if p.get("phone"):
                results.append({
                    "type": "partner",
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "phone": p.get("phone"),
                    "email": p.get("email"),
                    "company": p.get("company"),
                    "partner_type": p.get("partner_type"),
                    "match_score": 75,
                })
    except Exception as e:
        logger.error(f"Error searching partners in find_contact_phone: {e}")

    # Sort by match score
    results.sort(key=lambda x: x.get("match_score", 0), reverse=True)

    if not results:
        return ToolResult.success(
            data={
                "contacts": [],
                "count": 0,
                "search_name": name,
                "message": f"No contacts with phone numbers found matching '{name}'. Try a different spelling or check the CRM.",
            },
            message=f"No phone numbers found for '{name}'"
        )

    # Return best match prominently
    best_match = results[0]

    return ToolResult.success(
        data={
            "contacts": results[:5],  # Top 5 matches
            "count": len(results),
            "search_name": name,
            "best_match": best_match,
        },
        message=f"Found {best_match['name']} ({best_match['phone']}) - {best_match['type']}"
    )


def _search_inbox_for_contact(name: str, user_id: int) -> List[Dict[str, Any]]:
    """
    Search user's Microsoft 365 inbox for emails from someone matching the name.
    Returns email addresses found in inbox that match the search name.
    """
    import os
    import requests
    from datetime import timezone

    results = []
    search_name = name.strip().lower()

    try:
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Check for Microsoft OAuth token
            oauth = db.execute(text("""
                SELECT access_token, refresh_token, token_expires_at
                FROM microsoft_oauth_tokens
                WHERE user_id = :user_id
                AND access_token IS NOT NULL
                AND sync_enabled = true
                LIMIT 1
            """), {"user_id": user_id}).fetchone()

            if not oauth or not oauth.access_token:
                return []

            # Decrypt and possibly refresh token
            from services.calendly_service import decrypt_token, encrypt_token
            access_token = decrypt_token(oauth.access_token)

            now = datetime.now(timezone.utc)
            if oauth.token_expires_at and oauth.token_expires_at.replace(tzinfo=timezone.utc) < now:
                # Token expired - try to refresh
                refresh_token = decrypt_token(oauth.refresh_token) if oauth.refresh_token else None
                if refresh_token:
                    client_id = os.getenv("MICROSOFT_CLIENT_ID")
                    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
                    tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

                    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                    refresh_response = requests.post(token_url, data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                        "scope": "https://graph.microsoft.com/Mail.Read offline_access",
                    }, timeout=30)

                    if refresh_response.status_code == 200:
                        tokens = refresh_response.json()
                        access_token = tokens["access_token"]

                        # Update stored tokens
                        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
                        db.execute(text("""
                            UPDATE microsoft_oauth_tokens
                            SET access_token = :access_token,
                                refresh_token = :refresh_token,
                                token_expires_at = :expires_at,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = :user_id
                        """), {
                            "access_token": encrypt_token(access_token),
                            "refresh_token": encrypt_token(tokens.get("refresh_token", refresh_token)),
                            "expires_at": new_expires_at,
                            "user_id": user_id,
                        })
                        db.commit()
                    else:
                        return []
                else:
                    return []

            # Search inbox for emails from this person
            # Use $search to find by name in from field
            search_filter = f'"{name}"'

            response = requests.get(
                "https://graph.microsoft.com/v1.0/me/messages",
                params={
                    "$search": search_filter,
                    "$top": 50,
                    "$select": "from,receivedDateTime",
                    "$orderby": "receivedDateTime desc",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if response.status_code != 200:
                return []

            messages = response.json().get("value", [])

            # Extract unique email addresses that match the name
            seen_emails = set()
            for msg in messages:
                from_info = msg.get("from", {}).get("emailAddress", {})
                from_name = from_info.get("name", "")
                from_email = from_info.get("address", "")

                if not from_email or from_email in seen_emails:
                    continue

                # Check if name matches
                if search_name in from_name.lower() or any(part in from_name.lower() for part in search_name.split()):
                    seen_emails.add(from_email)
                    results.append({
                        "type": "email_contact",
                        "name": from_name,
                        "email": from_email,
                        "source": "inbox",
                        "match_score": 70 if search_name in from_name.lower() else 50,
                    })

            # Also search sent items to find people user has emailed
            sent_response = requests.get(
                "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages",
                params={
                    "$search": search_filter,
                    "$top": 50,
                    "$select": "toRecipients,receivedDateTime",
                    "$orderby": "receivedDateTime desc",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if sent_response.status_code == 200:
                sent_messages = sent_response.json().get("value", [])

                for msg in sent_messages:
                    for recipient in msg.get("toRecipients", []):
                        to_info = recipient.get("emailAddress", {})
                        to_name = to_info.get("name", "")
                        to_email = to_info.get("address", "")

                        if not to_email or to_email in seen_emails:
                            continue

                        # Check if name matches
                        if search_name in to_name.lower() or any(part in to_name.lower() for part in search_name.split()):
                            seen_emails.add(to_email)
                            results.append({
                                "type": "email_contact",
                                "name": to_name,
                                "email": to_email,
                                "source": "sent_items",
                                "match_score": 70 if search_name in to_name.lower() else 50,
                            })

        finally:
            db.close()

    except Exception as e:
        # Log but don't fail - just return empty results
        pass

    return results


@mortgage_tool(
    name="get_emails_needing_response",
    description="Get emails from your inbox that need a response. Shows unread/pending emails requiring attention, "
                "prioritized by urgency. Use this when user asks about emails to respond to, urgent emails, or inbox status.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "days": "Number of days to look back (default 7)",
        "unread_only": "Only show unread/pending emails (default True)",
        "limit": "Maximum number of emails to return (default 20)",
        "user_id": "User ID to check inbox for",
    },
)
def get_emails_needing_response(
    user_id: Optional[int] = None,
    days: int = 7,
    unread_only: bool = True,
    limit: int = 20,
) -> ToolResult:
    """
    Get emails that need a response from the user's inbox.

    Checks the email_reconciliation_queue for pending emails that:
    - Are unread/pending status
    - Require action (not just informational)
    - Are prioritized by urgency and recency
    """
    from datetime import timezone

    if not user_id:
        return ToolResult.error(
            "Unable to check emails: user_id is required. Please ensure you're logged in.",
            ["No user context available for email lookup"]
        )

    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Build query for emails needing response
        status_filter = "AND e.status = 'pending'" if unread_only else ""

        query = f"""
            SELECT
                e.id,
                e.from_email,
                e.from_name,
                e.subject,
                e.body_preview,
                COALESCE(e.received_date, e.sent_date, e.created_at) as received_date,
                e.match_client_name,
                e.matched_loan_id,
                e.matched_lead_id,
                e.is_priority,
                e.status,
                e.disposition,
                e.has_attachments,
                e.match_confidence
            FROM email_reconciliation_queue e
            WHERE e.user_id = :user_id
            AND e.created_at >= :start_date
            {status_filter}
            ORDER BY
                e.is_priority DESC,
                COALESCE(e.received_date, e.sent_date, e.created_at) DESC
            LIMIT :limit
        """

        results = execute_query(query, {
            "user_id": user_id,
            "start_date": start_date,
            "limit": limit
        })

        if not results:
            return ToolResult.success(
                data={
                    "emails": [],
                    "total_count": 0,
                    "priority_count": 0,
                    "message": "No emails requiring response found. Your inbox is clear!",
                    "checked_days": days,
                },
                message="No emails need response - inbox is clear!"
            )

        # Format results
        emails = []
        priority_count = 0

        for row in results:
            is_priority = row.get("is_priority", False)
            if is_priority:
                priority_count += 1

            received_date = row.get("received_date")
            if received_date and hasattr(received_date, 'isoformat'):
                received_str = received_date.isoformat()
            else:
                received_str = str(received_date) if received_date else None

            emails.append({
                "email_id": row.get("id"),
                "from_email": row.get("from_email"),
                "from_name": row.get("from_name"),
                "subject": row.get("subject"),
                "preview": (row.get("body_preview") or "")[:200],
                "received_date": received_str,
                "client_name": row.get("match_client_name"),
                "loan_id": row.get("matched_loan_id"),
                "lead_id": row.get("matched_lead_id"),
                "is_priority": is_priority,
                "status": row.get("status"),
                "disposition": row.get("disposition"),
                "has_attachments": row.get("has_attachments", False),
            })

        # Build summary message
        if priority_count > 0:
            summary = f"{len(emails)} emails need response ({priority_count} priority)"
        else:
            summary = f"{len(emails)} emails need response"

        return ToolResult.success(
            data={
                "emails": emails,
                "total_count": len(emails),
                "priority_count": priority_count,
                "checked_days": days,
                "unread_only": unread_only,
            },
            message=summary
        )

    except Exception as e:
        return ToolResult.error(
            f"Failed to retrieve emails: {str(e)}",
            [str(e)]
        )


# =============================================================================
# Advanced Tone Analysis Tools
# =============================================================================

@mortgage_tool(
    name="analyze_tone",
    description="Perform deep tone analysis on email or text content. Returns detailed emotional state, "
                "communication style, sentiment intensity, and urgency analysis. Use this for understanding "
                "customer mood and determining appropriate response approach.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "text": "The text content to analyze (email body, message, etc.)",
        "context": "Optional context: 'email', 'sms', 'chat' (affects analysis)",
    },
)
def analyze_tone(
    text: str,
    context: str = "email",
) -> ToolResult:
    """
    Perform comprehensive tone analysis on text content.

    Returns:
    - Emotional state (frustrated, confused, excited, satisfied, angry, anxious, grateful, hopeful)
    - Communication style (formal, casual, urgent, demanding, friendly, professional)
    - Sentiment intensity (very_negative to very_positive with confidence score)
    - Urgency level (critical, high, medium, low, normal)
    - Recommended response approach
    """
    if not text or len(text.strip()) < 10:
        return ToolResult.error(
            "Text too short for meaningful tone analysis. Provide at least 10 characters.",
            ["Insufficient text"]
        )

    # Run all analysis components
    emotional_state = _analyze_emotional_state(text)
    communication_style = _analyze_communication_style(text)
    sentiment = _calculate_sentiment_intensity(text)
    urgency = _detect_urgency_level(text)

    # Calculate overall tone score (-1 to 1)
    overall_score = sentiment["sentiment_score"] / 2  # Normalize
    if emotional_state["primary_category"] == "negative":
        overall_score -= 0.2
    elif emotional_state["primary_category"] == "positive":
        overall_score += 0.2

    # Determine response recommendations
    recommendations = []

    if emotional_state["primary_emotion"] == "angry":
        recommendations.append("Use empathetic language and acknowledge frustration")
        recommendations.append("Avoid defensive language")
        recommendations.append("Offer concrete solutions or escalation path")
    elif emotional_state["primary_emotion"] == "frustrated":
        recommendations.append("Acknowledge the difficulty they're experiencing")
        recommendations.append("Provide clear next steps")
        recommendations.append("Set realistic expectations")
    elif emotional_state["primary_emotion"] == "confused":
        recommendations.append("Provide clear, step-by-step explanations")
        recommendations.append("Avoid jargon")
        recommendations.append("Offer to clarify or have a call")
    elif emotional_state["primary_emotion"] == "anxious":
        recommendations.append("Use reassuring language")
        recommendations.append("Provide timeline and status updates")
        recommendations.append("Emphasize your availability to help")
    elif emotional_state["primary_emotion"] in ["excited", "grateful"]:
        recommendations.append("Match their positive energy")
        recommendations.append("Reinforce the good news or progress")
        recommendations.append("Maintain momentum")

    if urgency["urgency_level"] in ["critical", "high"]:
        recommendations.append("Respond promptly - high urgency detected")
    if communication_style["primary_style"] == "formal":
        recommendations.append("Maintain formal tone in response")
    elif communication_style["primary_style"] == "casual":
        recommendations.append("A friendly, conversational tone is appropriate")

    # Determine suggested response tone
    if emotional_state["primary_emotion"] in ["angry", "frustrated"]:
        suggested_tone = "empathetic_professional"
    elif emotional_state["primary_emotion"] in ["anxious", "confused"]:
        suggested_tone = "reassuring_clear"
    elif emotional_state["primary_emotion"] in ["excited", "grateful"]:
        suggested_tone = "warm_enthusiastic"
    elif communication_style["primary_style"] == "formal":
        suggested_tone = "formal_professional"
    elif communication_style["primary_style"] == "casual":
        suggested_tone = "friendly_professional"
    else:
        suggested_tone = "neutral_professional"

    # Risk indicators
    risk_level = "low"
    risk_factors = []
    if emotional_state["primary_emotion"] == "angry":
        risk_level = "high"
        risk_factors.append("Customer anger detected - escalation risk")
    elif emotional_state["primary_emotion"] == "frustrated":
        risk_level = "medium"
        risk_factors.append("Customer frustration - attention needed")
    if "attorney" in text.lower() or "lawsuit" in text.lower() or "complain" in text.lower():
        risk_level = "high"
        risk_factors.append("Legal/complaint language detected")
    if urgency["urgency_level"] == "critical":
        if risk_level != "high":
            risk_level = "medium"
        risk_factors.append("Critical urgency indicated")

    result = {
        "emotional_state": {
            "primary_emotion": emotional_state["primary_emotion"],
            "emotion_score": emotional_state["primary_score"],
            "emotion_category": emotional_state["primary_category"],
            "all_emotions_detected": emotional_state["all_emotions"],
            "emotion_evidence": emotional_state["emotion_matches"]
        },
        "communication_style": {
            "primary_style": communication_style["primary_style"],
            "style_score": communication_style["primary_score"],
            "secondary_style": communication_style["secondary_style"],
            "all_styles": communication_style["all_styles"]
        },
        "sentiment": {
            "category": sentiment["sentiment_category"],
            "score": sentiment["sentiment_score"],
            "intensity": sentiment["intensity_level"],
            "intensity_score": sentiment["intensity_score"],
            "positive_indicators": sentiment["positive_words"],
            "negative_indicators": sentiment["negative_words"],
            "confidence": sentiment["confidence"]
        },
        "urgency": {
            "level": urgency["urgency_level"],
            "score": urgency["urgency_score"],
            "indicators": urgency["urgency_indicators"],
            "has_caps_emphasis": urgency["has_caps_emphasis"]
        },
        "overall_tone_score": round(overall_score, 2),
        "risk_assessment": {
            "level": risk_level,
            "factors": risk_factors
        },
        "response_guidance": {
            "suggested_tone": suggested_tone,
            "recommendations": recommendations,
            "priority": "high" if urgency["urgency_level"] in ["critical", "high"] or risk_level == "high" else "normal"
        },
        "context": context
    }

    # Build summary message
    summary = f"Emotion: {emotional_state['primary_emotion']} | Style: {communication_style['primary_style']} | "
    summary += f"Sentiment: {sentiment['sentiment_category']} | Urgency: {urgency['urgency_level']}"
    if risk_level != "low":
        summary += f" | Risk: {risk_level.upper()}"

    return ToolResult.success(
        data=result,
        message=summary
    )


@mortgage_tool(
    name="get_thread_tone_trends",
    description="Analyze tone trends across an email thread or conversation history. "
                "Shows how sentiment and emotional state have evolved over time. "
                "Useful for understanding conversation trajectory and identifying escalation patterns.",
    agent_roles=["email_intelligence", "all"],
    risk_level="LOW",
    parameters={
        "contact_id": "Contact ID to analyze thread for",
        "contact_type": "Type: lead, borrower",
        "limit": "Number of messages to analyze (default 10)",
    },
)
def get_thread_tone_trends(
    contact_id: str,
    contact_type: str = "lead",
    limit: int = 10,
) -> ToolResult:
    """
    Analyze tone trends across an email thread.

    Returns:
    - Per-message tone analysis
    - Trend direction (improving, stable, declining)
    - Escalation risk assessment
    - Recommended intervention if needed
    """
    # Get email thread
    emails = execute_query("""
        SELECT
            id, direction, subject, body_preview,
            sent_at, read_at, replied_at
        FROM email_history
        WHERE contact_id = :contact_id AND contact_type = :contact_type
        ORDER BY sent_at ASC
        LIMIT :limit
    """, {"contact_id": contact_id, "contact_type": contact_type, "limit": limit})

    if not emails:
        # Try from email_interactions table
        emails = execute_query("""
            SELECT
                id, 'inbound' as direction, subject, body as body_preview,
                received_at as sent_at, NULL as read_at, NULL as replied_at
            FROM email_interactions
            WHERE (lead_id = :contact_id OR loan_id = :contact_id)
            ORDER BY received_at ASC
            LIMIT :limit
        """, {"contact_id": contact_id, "limit": limit})

    if not emails:
        return ToolResult.no_data(f"No email history found for {contact_type} {contact_id}")

    # Analyze tone for each message
    message_analyses = []
    sentiment_scores = []
    emotion_sequence = []

    for i, email in enumerate(emails):
        text = f"{email.get('subject', '')} {email.get('body_preview', '')}"

        if len(text.strip()) < 10:
            continue

        emotional_state = _analyze_emotional_state(text)
        sentiment = _calculate_sentiment_intensity(text)
        urgency = _detect_urgency_level(text)

        analysis = {
            "message_index": i + 1,
            "direction": email.get("direction", "unknown"),
            "subject": email.get("subject"),
            "date": format_date(email.get("sent_at")),
            "emotion": emotional_state["primary_emotion"],
            "emotion_category": emotional_state["primary_category"],
            "sentiment": sentiment["sentiment_category"],
            "sentiment_score": sentiment["sentiment_score"],
            "urgency": urgency["urgency_level"]
        }
        message_analyses.append(analysis)
        sentiment_scores.append(sentiment["sentiment_score"])
        emotion_sequence.append(emotional_state["primary_emotion"])

    if len(sentiment_scores) < 2:
        return ToolResult.success(
            data={
                "contact_id": contact_id,
                "contact_type": contact_type,
                "message_count": len(message_analyses),
                "messages": message_analyses,
                "trend": "insufficient_data",
                "trend_direction": 0,
            },
            message="Insufficient messages for trend analysis"
        )

    # Calculate trend
    first_half_avg = sum(sentiment_scores[:len(sentiment_scores)//2]) / max(1, len(sentiment_scores)//2)
    second_half_avg = sum(sentiment_scores[len(sentiment_scores)//2:]) / max(1, len(sentiment_scores) - len(sentiment_scores)//2)
    trend_direction = second_half_avg - first_half_avg

    if trend_direction > 0.3:
        trend = "improving"
        trend_description = "Customer sentiment is improving over the conversation"
    elif trend_direction < -0.3:
        trend = "declining"
        trend_description = "Customer sentiment is declining - attention needed"
    else:
        trend = "stable"
        trend_description = "Customer sentiment has remained relatively stable"

    # Check for escalation patterns
    escalation_risk = "low"
    escalation_indicators = []

    # Check if recent emotions are negative
    recent_emotions = emotion_sequence[-3:] if len(emotion_sequence) >= 3 else emotion_sequence
    negative_emotions = ["angry", "frustrated", "disappointed", "impatient"]

    negative_count = sum(1 for e in recent_emotions if e in negative_emotions)
    if negative_count >= 2:
        escalation_risk = "high"
        escalation_indicators.append(f"{negative_count} of last {len(recent_emotions)} messages show negative emotions")
    elif negative_count >= 1:
        escalation_risk = "medium"
        escalation_indicators.append("Recent negative emotion detected")

    # Check sentiment trajectory
    if trend == "declining" and sentiment_scores[-1] < -0.5:
        escalation_risk = "high"
        escalation_indicators.append("Declining sentiment with recent strongly negative message")

    # Recommendations based on trend
    recommendations = []
    if escalation_risk == "high":
        recommendations.append("Consider proactive outreach to address concerns")
        recommendations.append("Review recent communications for missed issues")
        recommendations.append("Consider manager involvement if pattern continues")
    elif escalation_risk == "medium":
        recommendations.append("Monitor closely for further decline")
        recommendations.append("Ensure prompt and thorough responses")
    if trend == "improving":
        recommendations.append("Maintain current approach - relationship is strengthening")

    # Find emotion transitions
    emotion_transitions = []
    for i in range(1, len(emotion_sequence)):
        if emotion_sequence[i] != emotion_sequence[i-1]:
            emotion_transitions.append({
                "from": emotion_sequence[i-1],
                "to": emotion_sequence[i],
                "message_index": i + 1
            })

    result = {
        "contact_id": contact_id,
        "contact_type": contact_type,
        "message_count": len(message_analyses),
        "messages": message_analyses,
        "trend_analysis": {
            "trend": trend,
            "trend_direction": round(trend_direction, 2),
            "description": trend_description,
            "first_half_sentiment": round(first_half_avg, 2),
            "second_half_sentiment": round(second_half_avg, 2),
        },
        "escalation_assessment": {
            "risk_level": escalation_risk,
            "indicators": escalation_indicators,
        },
        "emotion_flow": {
            "sequence": emotion_sequence,
            "transitions": emotion_transitions,
            "dominant_emotion": max(set(emotion_sequence), key=emotion_sequence.count) if emotion_sequence else "neutral"
        },
        "recommendations": recommendations
    }

    summary = f"Thread: {len(message_analyses)} messages | Trend: {trend} | "
    summary += f"Escalation risk: {escalation_risk}"

    return ToolResult.success(
        data=result,
        message=summary
    )


@mortgage_tool(
    name="compare_tone_to_baseline",
    description="Compare the tone of a specific email/message to the sender's historical baseline. "
                "Identifies if current message is unusually positive, negative, or urgent compared to typical communication.",
    agent_roles=["email_intelligence"],
    risk_level="LOW",
    parameters={
        "text": "Current message text to analyze",
        "contact_id": "Contact ID for baseline comparison",
        "contact_type": "Type: lead, borrower",
    },
)
def compare_tone_to_baseline(
    text: str,
    contact_id: str,
    contact_type: str = "lead",
) -> ToolResult:
    """
    Compare current message tone to sender's historical baseline.
    Useful for detecting unusual emotional states or escalation.
    """
    if not text or len(text.strip()) < 10:
        return ToolResult.error(
            "Text too short for analysis",
            ["Insufficient text"]
        )

    # Analyze current message
    current_emotional = _analyze_emotional_state(text)
    current_sentiment = _calculate_sentiment_intensity(text)
    current_urgency = _detect_urgency_level(text)

    # Get historical messages for baseline
    historical = execute_query("""
        SELECT body_preview
        FROM email_history
        WHERE contact_id = :contact_id
        AND contact_type = :contact_type
        AND direction = 'inbound'
        ORDER BY sent_at DESC
        LIMIT 20
    """, {"contact_id": contact_id, "contact_type": contact_type})

    if not historical or len(historical) < 3:
        # Not enough history for baseline
        return ToolResult.success(
            data={
                "current_analysis": {
                    "emotion": current_emotional["primary_emotion"],
                    "sentiment": current_sentiment["sentiment_category"],
                    "sentiment_score": current_sentiment["sentiment_score"],
                    "urgency": current_urgency["urgency_level"]
                },
                "baseline_available": False,
                "comparison": None,
                "deviation_detected": False,
                "message": "Insufficient history for baseline comparison"
            },
            message=f"Current: {current_emotional['primary_emotion']} | No baseline available"
        )

    # Calculate baseline from historical messages
    baseline_sentiments = []
    baseline_emotions = []

    for msg in historical:
        msg_text = msg.get("body_preview", "")
        if len(msg_text.strip()) < 10:
            continue

        hist_emotional = _analyze_emotional_state(msg_text)
        hist_sentiment = _calculate_sentiment_intensity(msg_text)

        baseline_sentiments.append(hist_sentiment["sentiment_score"])
        baseline_emotions.append(hist_emotional["primary_emotion"])

    if len(baseline_sentiments) < 3:
        return ToolResult.success(
            data={
                "current_analysis": {
                    "emotion": current_emotional["primary_emotion"],
                    "sentiment": current_sentiment["sentiment_category"],
                    "sentiment_score": current_sentiment["sentiment_score"],
                    "urgency": current_urgency["urgency_level"]
                },
                "baseline_available": False,
                "comparison": None,
                "deviation_detected": False,
            },
            message=f"Current: {current_emotional['primary_emotion']} | Insufficient baseline data"
        )

    # Calculate baseline statistics
    baseline_avg = sum(baseline_sentiments) / len(baseline_sentiments)
    baseline_std = (sum((x - baseline_avg) ** 2 for x in baseline_sentiments) / len(baseline_sentiments)) ** 0.5

    # Calculate deviation
    deviation = current_sentiment["sentiment_score"] - baseline_avg
    std_deviation = deviation / max(baseline_std, 0.1)  # Avoid division by zero

    # Determine if significant deviation
    deviation_detected = abs(std_deviation) > 1.5
    deviation_direction = "more_negative" if deviation < 0 else "more_positive" if deviation > 0 else "similar"

    # Check emotion shift
    dominant_baseline_emotion = max(set(baseline_emotions), key=baseline_emotions.count)
    emotion_shift = current_emotional["primary_emotion"] != dominant_baseline_emotion

    # Build alerts
    alerts = []
    if deviation_detected and deviation < 0:
        alerts.append("Significant negative deviation from baseline - customer may be unhappy")
    if current_emotional["primary_emotion"] in ["angry", "frustrated"] and dominant_baseline_emotion not in ["angry", "frustrated"]:
        alerts.append("Emotional state shift to negative - attention recommended")
    if current_urgency["urgency_level"] in ["critical", "high"]:
        alerts.append("High urgency detected in current message")

    result = {
        "current_analysis": {
            "emotion": current_emotional["primary_emotion"],
            "emotion_category": current_emotional["primary_category"],
            "sentiment": current_sentiment["sentiment_category"],
            "sentiment_score": current_sentiment["sentiment_score"],
            "urgency": current_urgency["urgency_level"]
        },
        "baseline_available": True,
        "baseline": {
            "message_count": len(baseline_sentiments),
            "average_sentiment": round(baseline_avg, 2),
            "sentiment_std_dev": round(baseline_std, 2),
            "dominant_emotion": dominant_baseline_emotion
        },
        "comparison": {
            "deviation": round(deviation, 2),
            "std_deviation": round(std_deviation, 2),
            "deviation_direction": deviation_direction,
            "deviation_detected": deviation_detected,
            "emotion_shift": emotion_shift
        },
        "alerts": alerts
    }

    # Build summary
    if alerts:
        summary = f"ALERT: {alerts[0]}"
    elif deviation_detected:
        summary = f"Deviation detected: {deviation_direction} than baseline"
    else:
        summary = f"Within normal range (deviation: {round(std_deviation, 1)} std)"

    return ToolResult.success(
        data=result,
        message=summary
    )
