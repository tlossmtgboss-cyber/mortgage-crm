"""
Voice Biometrics Service
Caller authentication and recognition using voice patterns
Supports repeat caller identification and secure verification
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import base64

logger = logging.getLogger(__name__)


class VoiceprintStatus(str, Enum):
    """Status of a voiceprint"""
    ENROLLED = "enrolled"
    PENDING = "pending"
    EXPIRED = "expired"
    LOCKED = "locked"
    DELETED = "deleted"


class VerificationResult(str, Enum):
    """Result of voice verification"""
    MATCH = "match"
    NO_MATCH = "no_match"
    INSUFFICIENT_AUDIO = "insufficient_audio"
    QUALITY_TOO_LOW = "quality_too_low"
    SPOOF_DETECTED = "spoof_detected"
    NOT_ENROLLED = "not_enrolled"
    ERROR = "error"


class CallerRecognitionResult(str, Enum):
    """Result of caller recognition"""
    RECOGNIZED = "recognized"
    NEW_CALLER = "new_caller"
    UNCERTAIN = "uncertain"
    POSSIBLE_MATCH = "possible_match"


@dataclass
class Voiceprint:
    """Voice biometric template for a caller"""
    id: str
    caller_id: str
    phone_number: str
    status: VoiceprintStatus = VoiceprintStatus.PENDING
    enrollment_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_verified: Optional[datetime] = None
    verification_count: int = 0
    failed_attempts: int = 0
    quality_score: float = 0.0  # 0-1 confidence in voiceprint quality
    audio_samples_count: int = 0
    feature_vector: Optional[str] = None  # Encoded feature vector
    metadata: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[datetime] = None


@dataclass
class VerificationAttempt:
    """Record of a verification attempt"""
    id: str
    voiceprint_id: str
    caller_phone: str
    timestamp: datetime
    result: VerificationResult
    confidence_score: float
    audio_quality: float
    audio_duration_seconds: float
    ip_address: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CallerProfile:
    """Profile for a recognized caller"""
    id: str
    phone_number: str
    name: Optional[str] = None
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_calls: int = 0
    voiceprint_id: Optional[str] = None
    is_verified: bool = False
    is_vip: bool = False
    preferred_language: str = "en"
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    linked_lead_id: Optional[int] = None
    linked_loan_id: Optional[int] = None


class VoiceBiometricsService:
    """
    Service for voice biometric authentication and caller recognition

    Features:
    - Voiceprint enrollment and management
    - Voice-based authentication
    - Repeat caller recognition
    - Fraud/spoof detection
    - VIP caller identification
    - Caller profile management
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self._voiceprints: Dict[str, Voiceprint] = {}
        self._caller_profiles: Dict[str, CallerProfile] = {}
        self._verification_attempts: List[VerificationAttempt] = []

        # Configuration
        self._config = {
            "min_enrollment_duration_seconds": 10,
            "min_verification_duration_seconds": 3,
            "min_audio_quality": 0.6,
            "match_threshold": 0.85,
            "possible_match_threshold": 0.70,
            "max_failed_attempts": 5,
            "voiceprint_expiry_days": 365,
            "spoof_detection_enabled": True
        }

    def enroll_voiceprint(
        self,
        caller_id: str,
        phone_number: str,
        audio_data: bytes,
        audio_format: str = "wav",
        sample_rate: int = 16000,
        metadata: Optional[Dict] = None
    ) -> Tuple[bool, Voiceprint]:
        """
        Enroll a new voiceprint for a caller

        Args:
            caller_id: Unique caller identifier
            phone_number: Caller's phone number
            audio_data: Audio sample for enrollment
            audio_format: Audio format (wav, mp3, etc.)
            sample_rate: Audio sample rate
            metadata: Additional metadata

        Returns:
            Tuple of (success, Voiceprint)
        """
        import uuid
        voiceprint_id = f"VP-{str(uuid.uuid4())[:8].upper()}"

        # Check audio quality and duration
        audio_quality, audio_duration = self._analyze_audio(audio_data, audio_format)

        if audio_duration < self._config["min_enrollment_duration_seconds"]:
            logger.warning(f"Enrollment failed: audio too short ({audio_duration}s)")
            voiceprint = Voiceprint(
                id=voiceprint_id,
                caller_id=caller_id,
                phone_number=phone_number,
                status=VoiceprintStatus.PENDING,
                quality_score=0,
                metadata={"error": "Audio too short for enrollment"}
            )
            return False, voiceprint

        if audio_quality < self._config["min_audio_quality"]:
            logger.warning(f"Enrollment failed: audio quality too low ({audio_quality})")
            voiceprint = Voiceprint(
                id=voiceprint_id,
                caller_id=caller_id,
                phone_number=phone_number,
                status=VoiceprintStatus.PENDING,
                quality_score=audio_quality,
                metadata={"error": "Audio quality insufficient"}
            )
            return False, voiceprint

        # Extract voice features
        feature_vector = self._extract_features(audio_data, audio_format)

        voiceprint = Voiceprint(
            id=voiceprint_id,
            caller_id=caller_id,
            phone_number=phone_number,
            status=VoiceprintStatus.ENROLLED,
            quality_score=audio_quality,
            audio_samples_count=1,
            feature_vector=feature_vector,
            metadata=metadata or {},
            expires_at=datetime.now(timezone.utc) + timedelta(days=self._config["voiceprint_expiry_days"])
        )

        self._voiceprints[voiceprint_id] = voiceprint

        # Update or create caller profile
        self._update_caller_profile(phone_number, voiceprint_id=voiceprint_id)

        logger.info(f"Enrolled voiceprint: {voiceprint_id} for caller {caller_id}")
        return True, voiceprint

    def verify_caller(
        self,
        voiceprint_id: str,
        audio_data: bytes,
        audio_format: str = "wav",
        ip_address: Optional[str] = None
    ) -> Tuple[VerificationResult, float]:
        """
        Verify a caller against their enrolled voiceprint

        Args:
            voiceprint_id: ID of enrolled voiceprint
            audio_data: Audio sample for verification
            audio_format: Audio format
            ip_address: Client IP address

        Returns:
            Tuple of (VerificationResult, confidence_score)
        """
        import uuid

        if voiceprint_id not in self._voiceprints:
            return VerificationResult.NOT_ENROLLED, 0.0

        voiceprint = self._voiceprints[voiceprint_id]

        # Check voiceprint status
        if voiceprint.status == VoiceprintStatus.LOCKED:
            return VerificationResult.ERROR, 0.0

        if voiceprint.status == VoiceprintStatus.EXPIRED:
            return VerificationResult.NOT_ENROLLED, 0.0

        # Analyze audio
        audio_quality, audio_duration = self._analyze_audio(audio_data, audio_format)

        if audio_duration < self._config["min_verification_duration_seconds"]:
            self._record_verification_attempt(
                voiceprint_id, voiceprint.phone_number,
                VerificationResult.INSUFFICIENT_AUDIO, 0, audio_quality, audio_duration, ip_address
            )
            return VerificationResult.INSUFFICIENT_AUDIO, 0.0

        if audio_quality < self._config["min_audio_quality"]:
            self._record_verification_attempt(
                voiceprint_id, voiceprint.phone_number,
                VerificationResult.QUALITY_TOO_LOW, 0, audio_quality, audio_duration, ip_address
            )
            return VerificationResult.QUALITY_TOO_LOW, 0.0

        # Spoof detection
        if self._config["spoof_detection_enabled"]:
            is_spoof = self._detect_spoof(audio_data)
            if is_spoof:
                voiceprint.failed_attempts += 1
                self._check_lockout(voiceprint)
                self._record_verification_attempt(
                    voiceprint_id, voiceprint.phone_number,
                    VerificationResult.SPOOF_DETECTED, 0, audio_quality, audio_duration, ip_address
                )
                logger.warning(f"Spoof detected for voiceprint: {voiceprint_id}")
                return VerificationResult.SPOOF_DETECTED, 0.0

        # Compare features
        test_features = self._extract_features(audio_data, audio_format)
        confidence_score = self._compare_features(voiceprint.feature_vector, test_features)

        # Determine result
        if confidence_score >= self._config["match_threshold"]:
            result = VerificationResult.MATCH
            voiceprint.last_verified = datetime.now(timezone.utc)
            voiceprint.verification_count += 1
            voiceprint.failed_attempts = 0  # Reset on success
        else:
            result = VerificationResult.NO_MATCH
            voiceprint.failed_attempts += 1
            self._check_lockout(voiceprint)

        self._record_verification_attempt(
            voiceprint_id, voiceprint.phone_number,
            result, confidence_score, audio_quality, audio_duration, ip_address
        )

        logger.info(f"Verification: {voiceprint_id} - {result.value} ({confidence_score:.2f})")
        return result, confidence_score

    def recognize_caller(
        self,
        phone_number: str,
        audio_data: Optional[bytes] = None,
        audio_format: str = "wav"
    ) -> Tuple[CallerRecognitionResult, Optional[CallerProfile], float]:
        """
        Recognize a caller by phone number and optionally voice

        Args:
            phone_number: Caller's phone number
            audio_data: Optional audio for voice-based recognition
            audio_format: Audio format

        Returns:
            Tuple of (recognition_result, caller_profile, confidence)
        """
        # Normalize phone number
        normalized_phone = self._normalize_phone(phone_number)

        # Check for existing profile by phone
        profile = self._get_profile_by_phone(normalized_phone)

        if profile:
            # Update last seen
            profile.last_seen = datetime.now(timezone.utc)
            profile.total_calls += 1

            if audio_data and profile.voiceprint_id:
                # Verify voice for additional confidence
                result, confidence = self.verify_caller(
                    profile.voiceprint_id, audio_data, audio_format
                )

                if result == VerificationResult.MATCH:
                    return CallerRecognitionResult.RECOGNIZED, profile, confidence
                elif confidence >= self._config["possible_match_threshold"]:
                    return CallerRecognitionResult.POSSIBLE_MATCH, profile, confidence
                else:
                    return CallerRecognitionResult.UNCERTAIN, profile, confidence
            else:
                # Phone-only recognition
                return CallerRecognitionResult.RECOGNIZED, profile, 0.8

        else:
            # New caller
            profile = self._create_caller_profile(normalized_phone)
            return CallerRecognitionResult.NEW_CALLER, profile, 0.0

    def get_caller_profile(self, phone_number: str) -> Optional[CallerProfile]:
        """Get caller profile by phone number"""
        normalized_phone = self._normalize_phone(phone_number)
        return self._get_profile_by_phone(normalized_phone)

    def update_caller_profile(
        self,
        phone_number: str,
        name: Optional[str] = None,
        is_vip: Optional[bool] = None,
        preferred_language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        linked_lead_id: Optional[int] = None,
        linked_loan_id: Optional[int] = None
    ) -> Optional[CallerProfile]:
        """Update a caller profile"""
        normalized_phone = self._normalize_phone(phone_number)
        profile = self._get_profile_by_phone(normalized_phone)

        if not profile:
            return None

        if name is not None:
            profile.name = name
        if is_vip is not None:
            profile.is_vip = is_vip
        if preferred_language is not None:
            profile.preferred_language = preferred_language
        if tags is not None:
            profile.tags = tags
        if notes is not None:
            profile.notes = notes
        if linked_lead_id is not None:
            profile.linked_lead_id = linked_lead_id
        if linked_loan_id is not None:
            profile.linked_loan_id = linked_loan_id

        logger.info(f"Updated caller profile: {phone_number}")
        return profile

    def get_vip_callers(self) -> List[CallerProfile]:
        """Get all VIP callers"""
        return [p for p in self._caller_profiles.values() if p.is_vip]

    def get_repeat_callers(self, min_calls: int = 2) -> List[CallerProfile]:
        """Get repeat callers with minimum call count"""
        return [
            p for p in self._caller_profiles.values()
            if p.total_calls >= min_calls
        ]

    def get_voiceprint_stats(self) -> Dict[str, Any]:
        """Get voiceprint enrollment statistics"""
        voiceprints = list(self._voiceprints.values())

        by_status = {}
        for status in VoiceprintStatus:
            by_status[status.value] = len([v for v in voiceprints if v.status == status])

        quality_scores = [v.quality_score for v in voiceprints if v.quality_score > 0]

        return {
            "total_voiceprints": len(voiceprints),
            "by_status": by_status,
            "avg_quality_score": sum(quality_scores) / len(quality_scores) if quality_scores else 0,
            "total_verifications": sum(v.verification_count for v in voiceprints),
            "locked_accounts": by_status.get(VoiceprintStatus.LOCKED.value, 0)
        }

    def get_verification_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get verification attempt statistics"""
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        attempts = [
            a for a in self._verification_attempts
            if start_date <= a.timestamp <= end_date
        ]

        if not attempts:
            return {
                "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "total_attempts": 0
            }

        by_result = {}
        for result in VerificationResult:
            by_result[result.value] = len([a for a in attempts if a.result == result])

        match_attempts = [a for a in attempts if a.result == VerificationResult.MATCH]
        avg_confidence = (
            sum(a.confidence_score for a in match_attempts) / len(match_attempts)
            if match_attempts else 0
        )

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_attempts": len(attempts),
            "by_result": by_result,
            "success_rate": by_result.get(VerificationResult.MATCH.value, 0) / len(attempts) * 100,
            "avg_confidence_on_match": round(avg_confidence, 3),
            "spoof_attempts": by_result.get(VerificationResult.SPOOF_DETECTED.value, 0),
            "avg_audio_quality": round(
                sum(a.audio_quality for a in attempts) / len(attempts), 3
            )
        }

    def delete_voiceprint(self, voiceprint_id: str) -> bool:
        """Delete a voiceprint (GDPR compliance)"""
        if voiceprint_id not in self._voiceprints:
            return False

        voiceprint = self._voiceprints[voiceprint_id]
        voiceprint.status = VoiceprintStatus.DELETED
        voiceprint.feature_vector = None  # Clear biometric data

        # Update caller profile
        for profile in self._caller_profiles.values():
            if profile.voiceprint_id == voiceprint_id:
                profile.voiceprint_id = None
                profile.is_verified = False

        logger.info(f"Deleted voiceprint: {voiceprint_id}")
        return True

    def unlock_voiceprint(self, voiceprint_id: str) -> bool:
        """Unlock a locked voiceprint (admin action)"""
        if voiceprint_id not in self._voiceprints:
            return False

        voiceprint = self._voiceprints[voiceprint_id]
        if voiceprint.status == VoiceprintStatus.LOCKED:
            voiceprint.status = VoiceprintStatus.ENROLLED
            voiceprint.failed_attempts = 0
            logger.info(f"Unlocked voiceprint: {voiceprint_id}")
            return True

        return False

    def configure(self, **kwargs) -> Dict[str, Any]:
        """Update service configuration"""
        for key, value in kwargs.items():
            if key in self._config:
                self._config[key] = value
                logger.info(f"Updated config: {key} = {value}")

        return self._config.copy()

    # Private methods

    def _analyze_audio(self, audio_data: bytes, audio_format: str) -> Tuple[float, float]:
        """
        Analyze audio quality and duration

        Returns: (quality_score 0-1, duration_seconds)
        """
        # In production, this would use actual audio analysis
        # For now, return simulated values based on data size
        duration = len(audio_data) / 32000  # Rough estimate
        quality = min(1.0, 0.7 + (len(audio_data) / 1000000) * 0.3)

        return quality, duration

    def _extract_features(self, audio_data: bytes, audio_format: str) -> str:
        """
        Extract voice biometric features from audio

        In production, this would use a voice biometrics library
        (e.g., SpeechBrain, pyannote-audio, or commercial API)

        Returns: Encoded feature vector
        """
        # Simulated feature extraction
        # In production: Use MFCC, d-vector, x-vector, or similar
        feature_hash = hashlib.sha256(audio_data).digest()
        return base64.b64encode(feature_hash).decode('utf-8')

    def _compare_features(self, enrolled_features: str, test_features: str) -> float:
        """
        Compare two feature vectors and return similarity score

        In production, this would use cosine similarity or
        specialized comparison algorithms

        Returns: Similarity score (0-1)
        """
        if enrolled_features == test_features:
            return 1.0

        # Simulated comparison
        # In production: cosine similarity, PLDA, etc.
        enrolled_bytes = base64.b64decode(enrolled_features)
        test_bytes = base64.b64decode(test_features)

        # Simple byte comparison for simulation
        matching = sum(1 for a, b in zip(enrolled_bytes, test_bytes) if a == b)
        similarity = matching / max(len(enrolled_bytes), len(test_bytes))

        # Add some randomness for realistic simulation
        import random
        similarity = max(0.3, min(0.95, similarity + random.uniform(-0.2, 0.2)))

        return similarity

    def _detect_spoof(self, audio_data: bytes) -> bool:
        """
        Detect if audio is a spoof attempt (replay, synthetic, etc.)

        In production, this would use:
        - Replay detection
        - Synthetic speech detection
        - Liveness detection

        Returns: True if spoof detected
        """
        # Simulated spoof detection
        # Very low false positive rate in simulation
        return False

    def _check_lockout(self, voiceprint: Voiceprint):
        """Check if voiceprint should be locked due to failed attempts"""
        if voiceprint.failed_attempts >= self._config["max_failed_attempts"]:
            voiceprint.status = VoiceprintStatus.LOCKED
            logger.warning(f"Voiceprint locked due to failed attempts: {voiceprint.id}")

    def _record_verification_attempt(
        self,
        voiceprint_id: str,
        caller_phone: str,
        result: VerificationResult,
        confidence: float,
        audio_quality: float,
        audio_duration: float,
        ip_address: Optional[str]
    ):
        """Record a verification attempt"""
        import uuid
        attempt = VerificationAttempt(
            id=f"VA-{str(uuid.uuid4())[:8].upper()}",
            voiceprint_id=voiceprint_id,
            caller_phone=caller_phone,
            timestamp=datetime.now(timezone.utc),
            result=result,
            confidence_score=confidence,
            audio_quality=audio_quality,
            audio_duration_seconds=audio_duration,
            ip_address=ip_address
        )
        self._verification_attempts.append(attempt)

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number format"""
        # Remove non-numeric characters
        normalized = ''.join(c for c in phone if c.isdigit())

        # Ensure 10 digits for US numbers
        if len(normalized) == 11 and normalized.startswith('1'):
            normalized = normalized[1:]

        return normalized

    def _get_profile_by_phone(self, phone: str) -> Optional[CallerProfile]:
        """Get caller profile by normalized phone"""
        for profile in self._caller_profiles.values():
            if profile.phone_number == phone:
                return profile
        return None

    def _create_caller_profile(self, phone_number: str) -> CallerProfile:
        """Create a new caller profile"""
        import uuid
        profile_id = f"CP-{str(uuid.uuid4())[:8].upper()}"

        profile = CallerProfile(
            id=profile_id,
            phone_number=phone_number,
            total_calls=1
        )

        self._caller_profiles[profile_id] = profile
        return profile

    def _update_caller_profile(
        self,
        phone_number: str,
        voiceprint_id: Optional[str] = None
    ):
        """Update or create caller profile with voiceprint link"""
        normalized_phone = self._normalize_phone(phone_number)
        profile = self._get_profile_by_phone(normalized_phone)

        if profile:
            if voiceprint_id:
                profile.voiceprint_id = voiceprint_id
                profile.is_verified = True
        else:
            profile = self._create_caller_profile(normalized_phone)
            if voiceprint_id:
                profile.voiceprint_id = voiceprint_id
                profile.is_verified = True


# Create singleton instance
voice_biometrics_service = VoiceBiometricsService()
