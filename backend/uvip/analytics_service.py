"""
UVIP - Conversation Analytics Service
Calculates detailed analytics for meeting participants based on transcripts.
"""

from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)


class ConversationAnalyticsService:
    """Calculate detailed analytics for meeting participants"""

    def __init__(self):
        self.filler_words = [
            "um", "uh", "like", "you know", "sort of",
            "kind of", "basically", "actually", "literally",
            "right", "okay", "so", "well", "I mean"
        ]

    async def analyze_participant(
        self,
        recording_id: int,
        participant_id: int,
        db: Session,
        models: Dict
    ) -> Optional[Dict]:
        """Calculate analytics for a single participant"""

        MeetingRecording = models.get('MeetingRecording')
        RecordingTranscript = models.get('RecordingTranscript')
        ParticipantAnalytics = models.get('ParticipantAnalytics')

        if not all([MeetingRecording, RecordingTranscript, ParticipantAnalytics]):
            logger.error("Required models not available")
            return None

        # Get transcript for this recording
        transcript = db.query(RecordingTranscript).filter(
            RecordingTranscript.recording_id == recording_id
        ).first()

        if not transcript or not transcript.transcript_json:
            logger.warning(f"No transcript found for recording {recording_id}")
            return None

        segments = transcript.transcript_json
        if not isinstance(segments, list):
            segments = []

        # Filter segments for this participant
        participant_segments = [
            seg for seg in segments
            if seg.get('participant_id') == participant_id or
               seg.get('speaker_id') == str(participant_id)
        ]

        if not participant_segments:
            # Try matching by speaker label if participant_id not in segments
            logger.info(f"No segments found for participant {participant_id}, using all segments")
            participant_segments = segments

        # Get recording duration
        recording = db.query(MeetingRecording).filter(
            MeetingRecording.id == recording_id
        ).first()

        if not recording:
            return None

        meeting_duration = recording.duration_seconds or 0
        if meeting_duration == 0:
            logger.warning(f"Recording {recording_id} has no duration")
            return None

        # Calculate talk time
        talk_time = sum(
            (seg.get('end_time', 0) - seg.get('start_time', 0))
            for seg in participant_segments
        )

        listen_time = max(0, meeting_duration - talk_time)
        talk_listen_ratio = talk_time / meeting_duration if meeting_duration > 0 else 0

        # Find longest monologue
        longest_monologue = self._find_longest_monologue(participant_segments)

        # Count interruptions
        interruption_count = self._count_interruptions(
            participant_id,
            segments
        )

        # Count questions
        question_count = sum(
            1 for seg in participant_segments
            if self._is_question(seg.get('text', ''))
        )

        # Count filler words
        filler_count = self._count_filler_words(participant_segments)

        # Calculate speaking pace (words per minute)
        total_words = sum(
            len(seg.get('text', '').split())
            for seg in participant_segments
        )
        speaking_pace_wpm = int(
            (total_words / (talk_time / 60))
            if talk_time > 0 else 0
        )

        # Sentiment analysis
        sentiment_scores = self._analyze_sentiment(participant_segments)

        # Calculate engagement score
        engagement_score = self._calculate_engagement(
            talk_listen_ratio,
            question_count,
            interruption_count,
            longest_monologue
        )

        analytics_data = {
            "recording_id": recording_id,
            "participant_id": participant_id,
            "talk_time_seconds": int(talk_time),
            "listen_time_seconds": int(listen_time),
            "talk_listen_ratio": round(talk_listen_ratio, 2),
            "longest_monologue_seconds": int(longest_monologue),
            "interruption_count": interruption_count,
            "question_count": question_count,
            "filler_word_count": filler_count,
            "speaking_pace_wpm": speaking_pace_wpm,
            "sentiment_positive_pct": sentiment_scores["positive"],
            "sentiment_negative_pct": sentiment_scores["negative"],
            "sentiment_neutral_pct": sentiment_scores["neutral"],
            "engagement_score": round(engagement_score, 2)
        }

        # Save to database
        analytics_record = ParticipantAnalytics(**analytics_data)
        db.add(analytics_record)
        db.commit()
        db.refresh(analytics_record)

        analytics_data["id"] = analytics_record.id
        return analytics_data

    async def analyze_all_participants(
        self,
        recording_id: int,
        db: Session,
        models: Dict
    ) -> List[Dict]:
        """Analyze all participants in a recording"""

        MeetingRecording = models.get('MeetingRecording')
        MeetingParticipant = models.get('MeetingParticipant')

        if not all([MeetingRecording, MeetingParticipant]):
            return []

        recording = db.query(MeetingRecording).filter(
            MeetingRecording.id == recording_id
        ).first()

        if not recording:
            return []

        # Get all participants for this meeting
        participants = db.query(MeetingParticipant).filter(
            MeetingParticipant.meeting_id == recording.meeting_id
        ).all()

        results = []
        for participant in participants:
            try:
                analytics = await self.analyze_participant(
                    recording_id,
                    participant.id,
                    db,
                    models
                )
                if analytics:
                    results.append(analytics)
            except Exception as e:
                logger.error(f"Error analyzing participant {participant.id}: {e}")

        return results

    def _find_longest_monologue(self, segments: List[Dict]) -> float:
        """Find the longest continuous speaking segment"""
        if not segments:
            return 0

        # Sort by time
        sorted_segs = sorted(segments, key=lambda s: s.get('start_time', 0))

        max_monologue = 0
        current_monologue = 0

        for i, seg in enumerate(sorted_segs):
            start = seg.get('start_time', 0)
            end = seg.get('end_time', 0)
            duration = end - start

            if i > 0:
                prev_end = sorted_segs[i - 1].get('end_time', 0)
                gap = start - prev_end
                if gap > 2:  # More than 2 second gap = new monologue
                    current_monologue = 0

            current_monologue += duration
            max_monologue = max(max_monologue, current_monologue)

        return max_monologue

    def _count_interruptions(
        self,
        participant_id: int,
        all_segments: List[Dict]
    ) -> int:
        """Count times participant interrupted others"""
        interruptions = 0

        sorted_segs = sorted(all_segments, key=lambda s: s.get('start_time', 0))

        for i in range(1, len(sorted_segs)):
            current = sorted_segs[i]
            previous = sorted_segs[i - 1]

            current_participant = current.get('participant_id') or current.get('speaker_id')
            prev_participant = previous.get('participant_id') or previous.get('speaker_id')

            # Check if this participant interrupted
            if (str(current_participant) == str(participant_id) and
                    str(prev_participant) != str(participant_id)):

                current_start = current.get('start_time', 0)
                prev_end = previous.get('end_time', 0)
                gap = current_start - prev_end

                # If gap is less than 0.5 seconds, it's an interruption
                if gap < 0.5:
                    interruptions += 1

        return interruptions

    def _is_question(self, text: str) -> bool:
        """Check if text is a question"""
        if not text:
            return False

        text_lower = text.lower().strip()

        # Check for question mark
        if '?' in text:
            return True

        # Check for question words at start
        question_words = [
            'what', 'why', 'how', 'when', 'where', 'who',
            'which', 'whose', 'can you', 'could you', 'would you',
            'do you', 'does', 'did', 'are you', 'is there', 'have you',
            'will you', 'shall we', 'is that', 'are there'
        ]

        return any(text_lower.startswith(qw) for qw in question_words)

    def _count_filler_words(self, segments: List[Dict]) -> int:
        """Count filler words across all segments"""
        total = 0

        for seg in segments:
            text = seg.get('text', '').lower()
            words = text.split()

            # Count single-word fillers
            for word in words:
                clean_word = re.sub(r'[^\w]', '', word)
                if clean_word in ['um', 'uh', 'like', 'so', 'well', 'okay', 'right']:
                    total += 1

            # Count multi-word fillers
            for filler in self.filler_words:
                if ' ' in filler:
                    total += text.count(filler)

        return total

    def _analyze_sentiment(self, segments: List[Dict]) -> Dict[str, float]:
        """Simple sentiment analysis based on word lists"""
        positive_words = [
            'great', 'excellent', 'good', 'perfect', 'wonderful',
            'amazing', 'fantastic', 'love', 'happy', 'pleased',
            'excited', 'appreciate', 'thank', 'thanks', 'sounds good',
            'absolutely', 'definitely', 'sure', 'yes', 'helpful',
            'easy', 'smooth', 'comfortable', 'confident', 'ready'
        ]

        negative_words = [
            'bad', 'problem', 'issue', 'concern', 'worried',
            'difficult', 'hard', 'confused', 'frustrated',
            'disappointed', 'unfortunately', 'sorry', 'no',
            'cant', "can't", 'wont', "won't", 'nervous',
            'complicated', 'expensive', 'stress', 'stressful'
        ]

        positive_count = 0
        negative_count = 0
        total_words = 0

        for seg in segments:
            text = seg.get('text', '').lower()
            words = text.split()
            total_words += len(words)

            for word in words:
                clean_word = re.sub(r'[^\w]', '', word)
                if clean_word in positive_words:
                    positive_count += 1
                elif clean_word in negative_words:
                    negative_count += 1

            # Check multi-word phrases
            for phrase in positive_words:
                if ' ' in phrase and phrase in text:
                    positive_count += 1

        sentiment_total = positive_count + negative_count

        if sentiment_total == 0:
            return {"positive": 50.0, "negative": 0.0, "neutral": 50.0}

        positive_pct = (positive_count / sentiment_total) * 100
        negative_pct = (negative_count / sentiment_total) * 100
        neutral_pct = 100 - positive_pct - negative_pct

        return {
            "positive": round(positive_pct, 2),
            "negative": round(negative_pct, 2),
            "neutral": round(max(0, neutral_pct), 2)
        }

    def _calculate_engagement(
        self,
        talk_listen_ratio: float,
        question_count: int,
        interruption_count: int,
        longest_monologue: float
    ) -> float:
        """Calculate overall engagement score (0-1)"""
        score = 0.5  # Start neutral

        # Ideal talk-listen ratio is 0.4-0.6 (40-60%)
        ratio_deviation = abs(talk_listen_ratio - 0.5)
        score += (0.5 - ratio_deviation) * 0.4  # Max +0.2 or -0.2

        # More questions is better (up to 10)
        question_score = min(question_count / 10, 1.0) * 0.3
        score += question_score

        # Penalize interruptions
        interruption_penalty = min(interruption_count / 10, 0.3)
        score -= interruption_penalty

        # Penalize very long monologues (>3 minutes)
        if longest_monologue > 180:
            monologue_penalty = min((longest_monologue - 180) / 300, 0.2)
            score -= monologue_penalty

        return max(0.0, min(1.0, score))


# Service singleton
_analytics_service: Optional[ConversationAnalyticsService] = None


def get_analytics_service() -> ConversationAnalyticsService:
    """Get or create the analytics service singleton"""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = ConversationAnalyticsService()
    return _analytics_service
