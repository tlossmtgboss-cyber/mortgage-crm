"""
Voice Cloning Service using Coqui XTTS v2.

This service provides:
- Voice model training from audio samples
- Text-to-speech synthesis with cloned voices
- Voice preview generation

Runs on GPU for optimal performance.
"""

import os
import io
import uuid
import shutil
import logging
import tempfile
from pathlib import Path
from typing import Optional

import torch
import torchaudio
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Voice Cloning Service",
    description="XTTS v2 based voice cloning and synthesis",
    version="1.0.0"
)

# Configuration
MODEL_DIR = os.getenv("XTTS_MODEL_DIR", "/models/xtts")
VOICE_SAMPLES_DIR = os.getenv("VOICE_SAMPLES_DIR", "/data/voice_samples")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/data/outputs")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Create directories
Path(VOICE_SAMPLES_DIR).mkdir(parents=True, exist_ok=True)
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# Global model instance (lazy loaded)
_tts_model = None


def get_tts_model():
    """Get or load the TTS model."""
    global _tts_model
    if _tts_model is None:
        try:
            from TTS.api import TTS
            logger.info(f"Loading XTTS v2 model on {DEVICE}...")
            _tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(DEVICE)
            logger.info("XTTS v2 model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load XTTS model: {e}")
            raise
    return _tts_model


# =============================================================================
# Request/Response Models
# =============================================================================

class SynthesizeRequest(BaseModel):
    """Request for voice synthesis."""
    text: str
    voice_model_id: str
    language: str = "en"
    speaking_rate: float = 1.0


class VoiceModelInfo(BaseModel):
    """Information about a voice model."""
    model_id: str
    name: str
    sample_duration_seconds: float
    created_at: str
    sample_path: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    device: str
    model_loaded: bool
    gpu_available: bool
    gpu_name: Optional[str] = None


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health and GPU availability."""
    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else None

    return HealthResponse(
        status="healthy",
        device=DEVICE,
        model_loaded=_tts_model is not None,
        gpu_available=gpu_available,
        gpu_name=gpu_name
    )


# =============================================================================
# Voice Model Management
# =============================================================================

@app.post("/voices/create")
async def create_voice_model(
    name: str = Form(...),
    audio_file: UploadFile = File(...)
):
    """
    Create a new voice model from an audio sample.

    The audio should be:
    - At least 6 seconds of clear speech
    - Clean audio without background noise
    - WAV or MP3 format
    """
    # Generate unique model ID
    model_id = f"voice_{uuid.uuid4().hex[:12]}"
    model_dir = Path(VOICE_SAMPLES_DIR) / model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Save uploaded audio
        file_ext = audio_file.filename.split('.')[-1] if '.' in audio_file.filename else 'wav'
        audio_path = model_dir / f"reference.{file_ext}"

        with open(audio_path, 'wb') as f:
            content = await audio_file.read()
            f.write(content)

        # Validate audio duration
        waveform, sample_rate = torchaudio.load(str(audio_path))
        duration_seconds = waveform.shape[1] / sample_rate

        if duration_seconds < 6:
            shutil.rmtree(model_dir)
            raise HTTPException(
                status_code=400,
                detail=f"Audio too short ({duration_seconds:.1f}s). Need at least 6 seconds."
            )

        # Save metadata
        metadata = {
            "model_id": model_id,
            "name": name,
            "sample_duration_seconds": duration_seconds,
            "sample_rate": sample_rate,
            "audio_file": str(audio_path),
        }

        import json
        with open(model_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f)

        logger.info(f"Created voice model: {model_id} ({duration_seconds:.1f}s sample)")

        return {
            "success": True,
            "model_id": model_id,
            "name": name,
            "sample_duration_seconds": duration_seconds,
            "message": "Voice model created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        if model_dir.exists():
            shutil.rmtree(model_dir)
        logger.error(f"Failed to create voice model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/voices/{model_id}")
async def get_voice_model(model_id: str):
    """Get voice model information."""
    model_dir = Path(VOICE_SAMPLES_DIR) / model_id
    metadata_path = model_dir / "metadata.json"

    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Voice model not found")

    import json
    with open(metadata_path) as f:
        metadata = json.load(f)

    return {"success": True, "voice": metadata}


@app.delete("/voices/{model_id}")
async def delete_voice_model(model_id: str):
    """Delete a voice model."""
    model_dir = Path(VOICE_SAMPLES_DIR) / model_id

    if not model_dir.exists():
        raise HTTPException(status_code=404, detail="Voice model not found")

    shutil.rmtree(model_dir)
    logger.info(f"Deleted voice model: {model_id}")

    return {"success": True, "message": "Voice model deleted"}


@app.get("/voices")
async def list_voice_models():
    """List all voice models."""
    models = []
    import json

    for model_dir in Path(VOICE_SAMPLES_DIR).iterdir():
        if model_dir.is_dir():
            metadata_path = model_dir / "metadata.json"
            if metadata_path.exists():
                with open(metadata_path) as f:
                    models.append(json.load(f))

    return {"success": True, "voices": models, "count": len(models)}


# =============================================================================
# Voice Synthesis
# =============================================================================

@app.post("/synthesize")
async def synthesize_speech(request: SynthesizeRequest):
    """
    Synthesize speech using a cloned voice.

    Returns WAV audio file.
    """
    # Validate voice model exists
    model_dir = Path(VOICE_SAMPLES_DIR) / request.voice_model_id
    metadata_path = model_dir / "metadata.json"

    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Voice model not found")

    import json
    with open(metadata_path) as f:
        metadata = json.load(f)

    speaker_wav = metadata["audio_file"]

    try:
        # Get TTS model
        tts = get_tts_model()

        # Generate speech
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            output_path = tmp_file.name

        logger.info(f"Synthesizing: '{request.text[:50]}...' with voice {request.voice_model_id}")

        tts.tts_to_file(
            text=request.text,
            speaker_wav=speaker_wav,
            language=request.language,
            file_path=output_path,
            speed=request.speaking_rate
        )

        # Read and return audio
        with open(output_path, 'rb') as f:
            audio_data = f.read()

        # Clean up
        os.unlink(output_path)

        # Get duration
        waveform, sample_rate = torchaudio.load(io.BytesIO(audio_data))
        duration_seconds = waveform.shape[1] / sample_rate

        logger.info(f"Generated {duration_seconds:.1f}s of audio")

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/wav",
            headers={
                "X-Duration-Seconds": str(duration_seconds),
                "Content-Disposition": f"attachment; filename=speech_{uuid.uuid4().hex[:8]}.wav"
            }
        )

    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/synthesize-to-file")
async def synthesize_to_file(
    text: str = Form(...),
    voice_model_id: str = Form(...),
    language: str = Form("en"),
    speaking_rate: float = Form(1.0),
    output_format: str = Form("wav")
):
    """
    Synthesize speech and save to a file.
    Returns the file path.
    """
    model_dir = Path(VOICE_SAMPLES_DIR) / voice_model_id
    metadata_path = model_dir / "metadata.json"

    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Voice model not found")

    import json
    with open(metadata_path) as f:
        metadata = json.load(f)

    speaker_wav = metadata["audio_file"]

    try:
        tts = get_tts_model()

        # Generate unique output path
        output_filename = f"synth_{uuid.uuid4().hex[:12]}.{output_format}"
        output_path = Path(OUTPUT_DIR) / output_filename

        tts.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            language=language,
            file_path=str(output_path),
            speed=speaking_rate
        )

        # Get duration
        waveform, sample_rate = torchaudio.load(str(output_path))
        duration_seconds = waveform.shape[1] / sample_rate

        return {
            "success": True,
            "output_path": str(output_path),
            "duration_seconds": duration_seconds,
            "format": output_format
        }

    except Exception as e:
        logger.error(f"Synthesis to file failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Utility Endpoints
# =============================================================================

@app.post("/extract-audio")
async def extract_audio_from_video(
    video_file: UploadFile = File(...)
):
    """
    Extract audio track from a video file.
    Used to create voice samples from training videos.
    """
    try:
        import subprocess

        # Save uploaded video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
            content = await video_file.read()
            tmp_video.write(content)
            video_path = tmp_video.name

        # Extract audio with FFmpeg
        audio_path = video_path.replace(".mp4", ".wav")

        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # WAV format
            "-ar", "22050",  # Sample rate
            "-ac", "1",  # Mono
            audio_path
        ], check=True, capture_output=True)

        # Read audio
        with open(audio_path, 'rb') as f:
            audio_data = f.read()

        # Get duration
        waveform, sample_rate = torchaudio.load(audio_path)
        duration_seconds = waveform.shape[1] / sample_rate

        # Clean up
        os.unlink(video_path)
        os.unlink(audio_path)

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/wav",
            headers={
                "X-Duration-Seconds": str(duration_seconds),
                "Content-Disposition": "attachment; filename=extracted_audio.wav"
            }
        )

    except Exception as e:
        logger.error(f"Audio extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/validate-audio")
async def validate_audio(audio_file: UploadFile = File(...)):
    """
    Validate an audio file for voice cloning.
    Checks duration, quality, and format.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            content = await audio_file.read()
            tmp_file.write(content)
            audio_path = tmp_file.name

        # Load and analyze
        waveform, sample_rate = torchaudio.load(audio_path)
        duration_seconds = waveform.shape[1] / sample_rate

        # Calculate audio metrics
        rms_energy = torch.sqrt(torch.mean(waveform ** 2)).item()

        os.unlink(audio_path)

        issues = []
        if duration_seconds < 6:
            issues.append(f"Audio too short ({duration_seconds:.1f}s, need 6s+)")
        if rms_energy < 0.01:
            issues.append("Audio level too low")
        if sample_rate < 16000:
            issues.append(f"Sample rate too low ({sample_rate}Hz, need 16000Hz+)")

        return {
            "valid": len(issues) == 0,
            "duration_seconds": duration_seconds,
            "sample_rate": sample_rate,
            "rms_energy": rms_energy,
            "issues": issues
        }

    except Exception as e:
        logger.error(f"Audio validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Startup
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Pre-load model on startup."""
    logger.info(f"Voice Cloning Service starting on {DEVICE}")
    if DEVICE == "cuda":
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
        logger.info(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")

    # Optionally pre-load model
    if os.getenv("PRELOAD_MODEL", "false").lower() == "true":
        get_tts_model()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5501)
