"""
Voice Profile Routes
Perennia AI — Voice enrollment and verification via resemblyzer d-vectors.

Handles voice sample ingestion, speaker embedding generation (resemblyzer),
enrollment finalization, and live voice verification.

Endpoints:
  POST   /api/v1/voice-profile/samples  — Upload one voice recording
  POST   /api/v1/voice-profile/enroll   — Compile samples → embedding (finalize)
  GET    /api/v1/voice-profile/status   — Check enrollment status
  POST   /api/v1/voice-profile/verify   — Verify live audio against stored profile
  DELETE /api/v1/voice-profile          — Delete profile + all samples (GDPR)

Dependencies (add to requirements.txt):
    resemblyzer>=0.1.1.dev0
    numpy>=1.24
    soundfile>=0.12
    librosa>=0.10
    python-multipart>=0.0.6
    boto3>=1.28
"""

import io
import os
import uuid
import logging
import tempfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from db import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice-profile", tags=["Voice Profile"])

# ─── Config ──────────────────────────────────────────────────────────────────
S3_BUCKET = os.environ.get("VOICE_SAMPLES_S3_BUCKET", "perennia-voice-samples")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL")
ENCODER_DEVICE = os.environ.get("VOICE_ENCODER_DEVICE", "cpu")

MIN_SAMPLES_FOR_ENROLLMENT = 5
VERIFICATION_THRESHOLD = 0.82

# ─── Lazy-loaded encoder (singleton) ─────────────────────────────────────────
_encoder = None


def get_encoder():
    global _encoder
    if _encoder is None:
        try:
            from resemblyzer import VoiceEncoder
            logger.info("Loading VoiceEncoder (resemblyzer) — first call only")
            _encoder = VoiceEncoder(device=ENCODER_DEVICE)
        except ImportError:
            logger.error("resemblyzer not installed — voice profile features unavailable")
            raise HTTPException(503, "Voice encoder not available on this server")
    return _encoder


# ─── S3/R2 client ────────────────────────────────────────────────────────────
def get_s3():
    import boto3
    from botocore.client import Config as BotoConfig

    kwargs = dict(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
        kwargs["config"] = BotoConfig(signature_version="s3v4")
    return boto3.client("s3", **kwargs)


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _upload_audio_to_s3(data: bytes, user_id: str, prompt_id: str) -> str:
    """Upload raw audio bytes to S3/R2 and return the object key."""
    key = f"voice-profiles/{user_id}/{prompt_id}_{uuid.uuid4().hex[:8]}.m4a"
    get_s3().put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=data,
        ContentType="audio/m4a",
    )
    return key


def _compute_embedding(audio_bytes: bytes):
    """
    Decode audio, resample to 16 kHz mono, and compute a 256-dim d-vector
    using resemblyzer's VoiceEncoder.
    """
    import numpy as np
    import librosa
    from resemblyzer import preprocess_wav

    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        y, sr = librosa.load(tmp_path, sr=16000, mono=True)
    finally:
        os.unlink(tmp_path)

    wav = preprocess_wav(y, source_sr=16000)
    encoder = get_encoder()
    embedding = encoder.embed_utterance(wav)  # shape: (256,)
    return embedding.astype(np.float32)


def _cosine_similarity(a, b) -> float:
    import numpy as np
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# ─── Response models ──────────────────────────────────────────────────────────
class SampleUploadResponse(BaseModel):
    sample_id: str
    prompt_id: str
    samples_total: int


class EnrollmentStatusResponse(BaseModel):
    status: str  # pending | processing | enrolled | failed
    samples_received: int
    samples_required: int
    embedding_ready: bool
    enrolled_at: Optional[str] = None


class VerifyResponse(BaseModel):
    match: bool
    confidence: float


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/samples", response_model=SampleUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_voice_sample(
    audio: UploadFile = File(...),
    prompt_id: str = Form(...),
    category: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Accept a single voice sample recording from the onboarding flow.
    Stores the raw audio in S3/R2 and persists metadata to voice_samples.
    """
    # Validate MIME type before processing
    from utils.validators import validate_upload_mime_type, ALLOWED_AUDIO_MIME_TYPES
    claimed_type = audio.content_type or "application/octet-stream"
    is_valid, mime_error = validate_upload_mime_type(
        audio.filename or "recording.wav", claimed_type, ALLOWED_AUDIO_MIME_TYPES
    )
    if not is_valid:
        raise HTTPException(400, mime_error)

    audio_data = audio.file.read()
    if len(audio_data) < 1024:
        raise HTTPException(400, "Audio file too small — likely empty recording")

    user_id = str(current_user.id)

    # Upload to object storage
    s3_key = _upload_audio_to_s3(audio_data, user_id, prompt_id)

    # Estimate duration
    duration_s = None
    try:
        import librosa
        with io.BytesIO(audio_data) as buf:
            y, sr = librosa.load(buf, sr=None, mono=True)
        duration_s = len(y) / sr
    except Exception as _exc:  # noqa: BLE001
        pass

    # Insert sample record
    result = db.execute(text("""
        INSERT INTO voice_samples (user_id, prompt_id, category, s3_key, duration_s)
        VALUES (:user_id, :prompt_id, :category, :s3_key, :duration_s)
        RETURNING id
    """), {
        "user_id": user_id,
        "prompt_id": prompt_id,
        "category": category,
        "s3_key": s3_key,
        "duration_s": duration_s,
    })
    sample_id = str(result.scalar())
    db.commit()

    # Count total samples
    row = db.execute(text(
        "SELECT COUNT(*) FROM voice_samples WHERE user_id = :uid"
    ), {"uid": user_id})
    total = row.scalar()

    logger.info(f"Voice sample uploaded: user={user_id} prompt={prompt_id} samples_total={total}")

    return SampleUploadResponse(
        sample_id=sample_id,
        prompt_id=prompt_id,
        samples_total=total,
    )


@router.post("/enroll", response_model=EnrollmentStatusResponse)
def finalize_enrollment(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Compile all uploaded voice samples into a single speaker embedding
    and mark the user as voice-enrolled.
    """
    import numpy as np

    user_id = str(current_user.id)

    rows = db.execute(text("""
        SELECT id, s3_key, duration_s FROM voice_samples
        WHERE user_id = :uid AND processed = FALSE
        ORDER BY created_at ASC
    """), {"uid": user_id})
    samples = rows.fetchall()

    if len(samples) < MIN_SAMPLES_FOR_ENROLLMENT:
        raise HTTPException(
            422,
            f"Need at least {MIN_SAMPLES_FOR_ENROLLMENT} samples, got {len(samples)}"
        )

    s3 = get_s3()
    embeddings = []

    for sample_id, s3_key, duration_s in samples:
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)["Body"].read()
            embedding = _compute_embedding(obj)
            embeddings.append(embedding)

            db.execute(text(
                "UPDATE voice_samples SET processed = TRUE WHERE id = :id"
            ), {"id": sample_id})
        except Exception as e:
            logger.warning(f"Failed to process sample {sample_id}: {e}")
            continue

    if not embeddings:
        raise HTTPException(500, "No samples could be processed")

    # Average all embeddings into one profile vector
    profile_embedding = np.mean(embeddings, axis=0)
    profile_embedding /= np.linalg.norm(profile_embedding)  # L2 normalize

    # Upsert into voice_profiles (pgvector stores as list literal)
    embedding_literal = "[" + ",".join(f"{x:.6f}" for x in profile_embedding.tolist()) + "]"
    enrolled_at = datetime.now(timezone.utc)

    db.execute(text("""
        INSERT INTO voice_profiles (user_id, embedding, samples_count, enrolled_at)
        VALUES (:uid, :emb::vector, :cnt, :enrolled_at)
        ON CONFLICT (user_id) DO UPDATE SET
            embedding     = EXCLUDED.embedding,
            samples_count = EXCLUDED.samples_count,
            enrolled_at   = EXCLUDED.enrolled_at,
            updated_at    = NOW()
    """), {
        "uid": user_id,
        "emb": embedding_literal,
        "cnt": len(embeddings),
        "enrolled_at": enrolled_at,
    })
    db.commit()

    logger.info(f"Voice enrollment complete: user={user_id} samples={len(embeddings)}")

    return EnrollmentStatusResponse(
        status="enrolled",
        samples_received=len(embeddings),
        samples_required=MIN_SAMPLES_FOR_ENROLLMENT,
        embedding_ready=True,
        enrolled_at=enrolled_at.isoformat(),
    )


@router.get("/status", response_model=EnrollmentStatusResponse)
def get_enrollment_status(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = str(current_user.id)

    profile_row = db.execute(text("""
        SELECT samples_count, enrolled_at FROM voice_profiles WHERE user_id = :uid
    """), {"uid": user_id})
    profile = profile_row.fetchone()

    sample_count_row = db.execute(text(
        "SELECT COUNT(*) FROM voice_samples WHERE user_id = :uid"
    ), {"uid": user_id})
    sample_count = sample_count_row.scalar()

    if profile:
        return EnrollmentStatusResponse(
            status="enrolled",
            samples_received=profile.samples_count,
            samples_required=MIN_SAMPLES_FOR_ENROLLMENT,
            embedding_ready=True,
            enrolled_at=profile.enrolled_at.isoformat() if profile.enrolled_at else None,
        )

    return EnrollmentStatusResponse(
        status="pending",
        samples_received=sample_count,
        samples_required=MIN_SAMPLES_FOR_ENROLLMENT,
        embedding_ready=False,
        enrolled_at=None,
    )


@router.post("/verify", response_model=VerifyResponse)
def verify_voice(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Compare an incoming audio clip against the user's stored voice profile.
    Returns confidence score and match boolean.
    """
    import numpy as np

    user_id = str(current_user.id)

    row = db.execute(text("""
        SELECT embedding::text FROM voice_profiles WHERE user_id = :uid
    """), {"uid": user_id})
    result = row.fetchone()

    if not result:
        raise HTTPException(404, "No voice profile found for this user")

    stored_vals = [float(x) for x in result[0].strip("[]").split(",")]
    stored_embedding = np.array(stored_vals, dtype=np.float32)

    # Validate MIME type before processing
    from utils.validators import validate_upload_mime_type, ALLOWED_AUDIO_MIME_TYPES
    claimed_type = audio.content_type or "application/octet-stream"
    is_valid, mime_error = validate_upload_mime_type(
        audio.filename or "recording.wav", claimed_type, ALLOWED_AUDIO_MIME_TYPES
    )
    if not is_valid:
        raise HTTPException(400, mime_error)

    audio_bytes = audio.file.read()
    live_embedding = _compute_embedding(audio_bytes)

    confidence = _cosine_similarity(stored_embedding, live_embedding)
    match = confidence >= VERIFICATION_THRESHOLD

    logger.info(f"Voice verify: user={user_id} confidence={confidence:.3f} match={match}")

    return VerifyResponse(match=match, confidence=round(confidence, 4))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_voice_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Delete the user's voice profile and all stored samples (GDPR compliance).
    """
    user_id = str(current_user.id)

    rows = db.execute(text(
        "SELECT s3_key FROM voice_samples WHERE user_id = :uid"
    ), {"uid": user_id})
    keys = [r[0] for r in rows.fetchall()]

    if keys:
        try:
            s3 = get_s3()
            s3.delete_objects(
                Bucket=S3_BUCKET,
                Delete={"Objects": [{"Key": k} for k in keys]}
            )
        except Exception as e:
            logger.warning(f"Failed to delete S3 objects for user {user_id}: {e}")

    db.execute(text("DELETE FROM voice_samples WHERE user_id = :uid"), {"uid": user_id})
    db.execute(text("DELETE FROM voice_profiles WHERE user_id = :uid"), {"uid": user_id})
    db.commit()

    logger.info(f"Voice profile deleted: user={user_id} samples_removed={len(keys)}")
