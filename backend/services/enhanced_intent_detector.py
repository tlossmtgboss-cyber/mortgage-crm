"""
Enhanced Intent Detector - Production-Ready

Context-aware intent detection with:
- Fuzzy matching for phrase variations
- Weighted scoring based on signal importance
- Context amplification for urgency signals
- Sentiment-aware weighting
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Try to import rapidfuzz, fall back to simple matching if not available
try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    logger.warning("rapidfuzz not installed, using fallback matching")


@dataclass
class IntentSignal:
    """Detected intent signal with metadata"""
    signal_type: str
    weight: int
    evidence: str
    confidence: float
    detected_at: str


class EnhancedIntentDetector:
    """Context-aware intent detection with fuzzy matching"""

    INTENT_PATTERNS = {
        'property': {
            'keywords': ['property', 'house', 'home', 'address', 'location', 'condo',
                        'townhouse', 'townhome', 'duplex', 'multi-family', 'single family'],
            'phrases': [
                'looking at a house',
                'found a property',
                'put an offer',
                'under contract',
                'closing on',
                'buying a home',
                'purchase a house',
                'investment property',
                'rental property',
                'vacation home',
                'second home',
                'first home',
                'starter home'
            ],
            'base_weight': 25,
            'description': 'Property interest'
        },
        'price': {
            'keywords': ['budget', 'price', 'cost', 'afford', 'range', 'spending'],
            'patterns': [
                r'\$\s*[\d,]+\s*k?',           # $500k, $500,000, $ 500k
                r'\d{3,}\s*k\b',                # 500k
                r'[\d,]{5,}',                   # 500000 (at least 5 digits)
                r'around\s+\$?\s*[\d,]+',      # around $500k
                r'up\s+to\s+\$?\s*[\d,]+',     # up to $500k
                r'between\s+\$?\s*[\d,]+\s*(?:and|to|-)\s*\$?\s*[\d,]+',  # between $400k and $500k
            ],
            'base_weight': 25,
            'description': 'Price/budget mentioned'
        },
        'timeline': {
            'keywords': ['soon', 'asap', 'quickly', 'deadline', 'closing', 'when', 'timeline'],
            'phrases': [
                'next month',
                'next week',
                'next year',
                'this month',
                'this week',
                'within 30 days',
                'within 60 days',
                'within 90 days',
                'need to close',
                'time sensitive',
                'closing date',
                'move by',
                'move in by',
                'ready to buy',
                'ready to close',
                'as soon as possible'
            ],
            'context_amplifiers': ['urgent', 'hurry', 'rush', 'immediately', 'right away'],
            'base_weight': 25,
            'description': 'Timeline mentioned'
        },
        'down_payment': {
            'keywords': ['down payment', 'downpayment', 'down', 'deposit', 'upfront',
                        'cash to close', 'money down', 'percent down'],
            'phrases': [
                'putting down',
                'have saved',
                'can put',
                'percent down',
                '20 percent',
                '10 percent',
                '5 percent',
                '3.5 percent',
                'zero down',
                'no money down',
                'gift funds',
                'gift money'
            ],
            'patterns': [
                r'\d+\s*%\s*down',              # 20% down
                r'\$\s*[\d,]+\s*down',          # $50,000 down
            ],
            'base_weight': 25,
            'description': 'Down payment discussed'
        },
        'loan_type': {
            'keywords': ['va', 'fha', 'conventional', 'usda', 'jumbo', 'conforming',
                        'arm', 'fixed', 'adjustable'],
            'phrases': [
                'va loan',
                'fha loan',
                'usda loan',
                'conventional loan',
                'jumbo loan',
                'first time buyer',
                'first-time homebuyer',
                'veteran',
                'military',
                'rural development',
                '30 year fixed',
                '15 year fixed',
                'adjustable rate'
            ],
            'base_weight': 15,
            'description': 'Loan type interest'
        },
        'credit_concern': {
            'keywords': ['credit', 'score', 'fico', 'bankruptcy', 'foreclosure',
                        'collections', 'late payments'],
            'phrases': [
                'credit score',
                'bad credit',
                'poor credit',
                'low credit',
                'credit issues',
                'rebuilding credit',
                'credit repair',
                'my score is',
                'score around',
                'worried about credit',
                'credit history'
            ],
            'sentiment_weight': True,  # Higher weight if negative sentiment
            'base_weight': 15,
            'description': 'Credit concerns'
        },
        'goal': {
            'keywords': ['buy', 'purchase', 'refinance', 'refi', 'invest', 'rental',
                        'cash out', 'equity'],
            'phrases': [
                'want to buy',
                'looking to purchase',
                'thinking about refinancing',
                'looking to refinance',
                'investment property',
                'rental property',
                'cash out refinance',
                'pull equity',
                'lower my rate',
                'lower my payment',
                'reduce payment',
                'consolidate debt'
            ],
            'base_weight': 15,
            'description': 'Primary goal'
        },
        'urgency': {
            'keywords': ['urgent', 'asap', 'quickly', 'now', 'help', 'stuck',
                        'confused', 'overwhelmed', 'stressed'],
            'phrases': [
                'need help',
                'not sure what',
                'confused about',
                'stuck on',
                'running out of time',
                'losing the house',
                'rate lock expiring',
                'contract deadline',
                'seller waiting',
                'need to act fast'
            ],
            'base_weight': 10,
            'description': 'Urgency indicator'
        },
        'recommendation_request': {
            'keywords': ['recommend', 'suggest', 'should', 'best', 'advice',
                        'opinion', 'think'],
            'phrases': [
                'what do you recommend',
                'what should i',
                'what would you',
                'best option',
                'your opinion',
                'your advice',
                'what do you think',
                'which is better',
                'pros and cons'
            ],
            'base_weight': 10,
            'description': 'Seeking recommendation'
        }
    }

    # Negative sentiment words for credit_concern weighting
    NEGATIVE_SENTIMENT = ['bad', 'poor', 'low', 'worried', 'concerned', 'scared',
                          'afraid', 'nervous', 'anxious', 'terrible']

    def __init__(self, fuzzy_threshold: int = 75):
        """
        Initialize detector.

        Args:
            fuzzy_threshold: Minimum fuzzy match score (0-100), default 75
        """
        self.fuzzy_threshold = fuzzy_threshold

    def detect_signals(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[IntentSignal]:
        """
        Detect intent signals with context awareness.

        Args:
            message: Current user message
            conversation_history: Previous messages for context

        Returns:
            List of detected IntentSignal objects
        """
        message_lower = message.lower()
        detected = []
        detected_types = set()  # Track to avoid duplicates

        for signal_type, config in self.INTENT_PATTERNS.items():
            matches = []
            weight = config['base_weight']

            # Keyword matching
            if 'keywords' in config:
                for keyword in config['keywords']:
                    if keyword in message_lower:
                        matches.append(keyword)

            # Pattern matching (regex for prices, etc.)
            if 'patterns' in config:
                for pattern in config['patterns']:
                    found = re.findall(pattern, message, re.IGNORECASE)
                    if found:
                        matches.extend(found)

            # Phrase matching with fuzzy logic
            if 'phrases' in config:
                for phrase in config['phrases']:
                    if self._fuzzy_match(phrase, message_lower):
                        matches.append(phrase)

            # Context amplification
            if matches and 'context_amplifiers' in config:
                for amplifier in config['context_amplifiers']:
                    if amplifier in message_lower:
                        weight = int(weight * 1.5)
                        break

            # Sentiment-based weighting for credit concerns
            if matches and config.get('sentiment_weight'):
                if any(word in message_lower for word in self.NEGATIVE_SENTIMENT):
                    weight += 5

            # Record if matches found and not already detected
            if matches and signal_type not in detected_types:
                detected_types.add(signal_type)

                # Calculate confidence based on match quality
                confidence = self._calculate_confidence(matches, message)

                signal = IntentSignal(
                    signal_type=signal_type,
                    weight=weight,
                    evidence=', '.join(matches[:3]),  # Store top 3 matches
                    confidence=confidence,
                    detected_at=datetime.now(timezone.utc).isoformat()
                )
                detected.append(signal)

        return detected

    def _fuzzy_match(self, phrase: str, message: str) -> bool:
        """Check if phrase matches message using fuzzy matching"""
        if FUZZY_AVAILABLE:
            ratio = fuzz.partial_ratio(phrase.lower(), message)
            return ratio >= self.fuzzy_threshold
        else:
            # Fallback: simple substring check
            return phrase.lower() in message

    def _calculate_confidence(self, matches: List[str], full_message: str) -> float:
        """Calculate confidence score for detected intent (0-1)"""
        base_confidence = 0.7

        # More matches = higher confidence
        if len(matches) >= 3:
            base_confidence = 0.9
        elif len(matches) >= 2:
            base_confidence = 0.85

        # Shorter, focused messages = higher confidence
        if len(full_message) < 100:
            base_confidence += 0.05

        return min(1.0, base_confidence)

    def calculate_intent_score(self, signals: List[IntentSignal]) -> int:
        """
        Calculate total intent score from detected signals.

        Returns:
            Score 0-100
        """
        if not signals:
            return 0

        total_weight = sum(s.weight for s in signals)
        return min(100, total_weight)

    def determine_urgency(
        self,
        signals: List[IntentSignal],
        intent_score: int
    ) -> str:
        """
        Determine urgency level based on signals and score.

        Returns:
            'low', 'medium', or 'high'
        """
        signal_types = {s.signal_type for s in signals}

        # High urgency indicators
        if 'urgency' in signal_types or intent_score >= 70:
            return 'high'

        # High urgency if timeline + property + price
        if {'timeline', 'property', 'price'}.issubset(signal_types):
            return 'high'

        # Medium urgency
        if intent_score >= 40 or len(signals) >= 2:
            return 'medium'

        return 'low'

    def get_missing_critical_signals(
        self,
        signals: List[IntentSignal]
    ) -> List[str]:
        """
        Identify which critical signals are missing.

        Returns:
            List of missing signal types
        """
        critical_signals = {'timeline', 'price', 'goal', 'down_payment'}
        detected_types = {s.signal_type for s in signals}

        return list(critical_signals - detected_types)

    def suggest_next_question(
        self,
        signals: List[IntentSignal]
    ) -> Optional[str]:
        """
        Suggest the next question to ask based on missing signals.

        Returns:
            Question string or None
        """
        missing = self.get_missing_critical_signals(signals)

        question_map = {
            'timeline': "What's your timeline for buying or refinancing?",
            'price': "What price range are you considering?",
            'goal': "Are you looking to purchase or refinance?",
            'down_payment': "Do you have a sense of your down payment situation?",
            'credit_concern': "Is your credit in good shape, or is that a concern?",
            'loan_type': "Have you looked into any specific loan programs like FHA or VA?"
        }

        # Priority order for questions
        priority = ['timeline', 'goal', 'price', 'down_payment']

        for signal_type in priority:
            if signal_type in missing:
                return question_map.get(signal_type)

        return None

    def signals_to_dict(self, signals: List[IntentSignal]) -> List[Dict[str, Any]]:
        """Convert signals to dictionary format for storage"""
        return [
            {
                'signal': s.signal_type,
                'value': s.evidence,
                'weight': s.weight,
                'confidence': s.confidence,
                'detected_at': s.detected_at
            }
            for s in signals
        ]


# Singleton instance for easy import
intent_detector = EnhancedIntentDetector()
