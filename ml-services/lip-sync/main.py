"""
Lip Sync Service using Wav2Lip.

This service provides:
- Lip-synced video generation from reference image/video + audio
- Face detection and extraction
- Video post-processing

Runs on GPU for optimal performance.
"""

import os
import io
import uuid
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Lip Sync Service",
    description="Wav2Lip based lip synchronization for avatar videos",
    version="1.0.0"
)

# Configuration
WAV2LIP_DIR = os.getenv("WAV2LIP_DIR", "/app/Wav2Lip")
CHECKPOINT_PATH = os.getenv("WAV2LIP_CHECKPOINT", "/models/wav2lip_gan.pth")
FACE_DETECT_MODEL = os.getenv("FACE_DETECT_MODEL", "/models/s3fd.pth")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/data/outputs")
TEMP_DIR = os.getenv("TEMP_DIR", "/tmp/lipsync")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Create directories
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)


# =============================================================================
# Request/Response Models
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    device: str
    wav2lip_available: bool
    checkpoint_exists: bool
    gpu_available: bool
    gpu_name: Optional[str] = None


class GenerateRequest(BaseModel):
    """Request for lip sync generation."""
    reference_image_url: Optional[str] = None
    emotion: str = "neutral"
    output_format: str = "mp4"
    fps: int = 25
    resize_factor: int = 1


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health and GPU availability."""
    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else None
    checkpoint_exists = Path(CHECKPOINT_PATH).exists()
    wav2lip_available = Path(WAV2LIP_DIR).exists()

    return HealthResponse(
        status="healthy" if checkpoint_exists else "degraded",
        device=DEVICE,
        wav2lip_available=wav2lip_available,
        checkpoint_exists=checkpoint_exists,
        gpu_available=gpu_available,
        gpu_name=gpu_name
    )


# =============================================================================
# Face Detection & Extraction
# =============================================================================

def detect_face(image_path: str) -> Optional[tuple]:
    """Detect face in image and return bounding box."""
    try:
        import face_detection
        detector = face_detection.build_detector(
            "DSFDDetector",
            confidence_threshold=0.5,
            nms_iou_threshold=0.3
        )

        image = cv2.imread(image_path)
        if image is None:
            return None

        # Detect faces
        detections = detector.detect(image)

        if len(detections) == 0:
            return None

        # Get largest face
        areas = [(d[2] - d[0]) * (d[3] - d[1]) for d in detections]
        best_idx = np.argmax(areas)
        return tuple(map(int, detections[best_idx][:4]))

    except Exception as e:
        logger.error(f"Face detection failed: {e}")
        return None


def extract_face_frame(video_path: str, output_path: str) -> bool:
    """Extract the best face frame from a video."""
    try:
        cap = cv2.VideoCapture(video_path)
        best_frame = None
        best_face_size = 0

        frame_count = 0
        while cap.isOpened() and frame_count < 100:  # Check first 100 frames
            ret, frame = cap.read()
            if not ret:
                break

            # Save frame temporarily
            temp_frame = f"{TEMP_DIR}/temp_frame.jpg"
            cv2.imwrite(temp_frame, frame)

            # Detect face
            face_box = detect_face(temp_frame)
            if face_box:
                x1, y1, x2, y2 = face_box
                face_size = (x2 - x1) * (y2 - y1)

                if face_size > best_face_size:
                    best_face_size = face_size
                    best_frame = frame.copy()

            frame_count += 1

        cap.release()

        if best_frame is not None:
            cv2.imwrite(output_path, best_frame)
            return True

        return False

    except Exception as e:
        logger.error(f"Face extraction failed: {e}")
        return False


@app.post("/extract-face")
async def extract_face(
    file: UploadFile = File(...),
    file_type: str = Form("image")  # "image" or "video"
):
    """Extract best face from image or video."""
    try:
        # Save uploaded file
        suffix = ".mp4" if file_type == "video" else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            input_path = tmp.name

        output_path = f"{TEMP_DIR}/extracted_face_{uuid.uuid4().hex[:8]}.jpg"

        if file_type == "video":
            success = extract_face_frame(input_path, output_path)
        else:
            # For image, just validate face exists
            face_box = detect_face(input_path)
            if face_box:
                shutil.copy(input_path, output_path)
                success = True
            else:
                success = False

        os.unlink(input_path)

        if not success:
            raise HTTPException(status_code=400, detail="No face detected in input")

        # Return the extracted face image
        with open(output_path, 'rb') as f:
            image_data = f.read()

        os.unlink(output_path)

        return StreamingResponse(
            io.BytesIO(image_data),
            media_type="image/jpeg",
            headers={"Content-Disposition": "attachment; filename=face.jpg"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Face extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Lip Sync Generation
# =============================================================================

@app.post("/generate")
async def generate_lipsync(
    reference_image: UploadFile = File(None),
    reference_video: UploadFile = File(None),
    audio: UploadFile = File(...),
    reference_image_url: str = Form(None),
    emotion: str = Form("neutral"),
    output_format: str = Form("mp4"),
    fps: int = Form(25),
    resize_factor: int = Form(1),
    pads: str = Form("0,10,0,0"),  # top, bottom, left, right
    nosmooth: bool = Form(False)
):
    """
    Generate lip-synced video from reference + audio.

    Either reference_image, reference_video, or reference_image_url must be provided.
    """
    job_id = uuid.uuid4().hex[:12]
    work_dir = Path(TEMP_DIR) / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get reference image/video
        if reference_image:
            ref_path = work_dir / "reference.jpg"
            with open(ref_path, 'wb') as f:
                f.write(await reference_image.read())
        elif reference_video:
            ref_path = work_dir / "reference.mp4"
            with open(ref_path, 'wb') as f:
                f.write(await reference_video.read())
        elif reference_image_url:
            # Download from URL
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(reference_image_url)
                ref_path = work_dir / "reference.jpg"
                with open(ref_path, 'wb') as f:
                    f.write(response.content)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide reference_image, reference_video, or reference_image_url"
            )

        # Save audio
        audio_path = work_dir / "audio.wav"
        with open(audio_path, 'wb') as f:
            f.write(await audio.read())

        # Output path
        output_path = work_dir / f"output.{output_format}"

        # Parse pads
        pad_values = [int(p) for p in pads.split(',')]

        # Run Wav2Lip inference
        logger.info(f"Starting lip sync generation for job {job_id}")

        cmd = [
            "python3", f"{WAV2LIP_DIR}/inference.py",
            "--checkpoint_path", CHECKPOINT_PATH,
            "--face", str(ref_path),
            "--audio", str(audio_path),
            "--outfile", str(output_path),
            "--resize_factor", str(resize_factor),
            "--fps", str(fps),
            "--pads", *[str(p) for p in pad_values],
        ]

        if nosmooth:
            cmd.append("--nosmooth")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=WAV2LIP_DIR
        )

        if result.returncode != 0:
            logger.error(f"Wav2Lip failed: {result.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"Lip sync generation failed: {result.stderr[:500]}"
            )

        if not output_path.exists():
            raise HTTPException(status_code=500, detail="Output file not created")

        # Get video info
        cap = cv2.VideoCapture(str(output_path))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps_actual = cap.get(cv2.CAP_PROP_FPS)
        duration_seconds = frame_count / fps_actual if fps_actual > 0 else 0
        cap.release()

        # Read output
        with open(output_path, 'rb') as f:
            video_data = f.read()

        # Clean up
        shutil.rmtree(work_dir)

        logger.info(f"Generated {duration_seconds:.1f}s lip-synced video")

        return StreamingResponse(
            io.BytesIO(video_data),
            media_type=f"video/{output_format}",
            headers={
                "X-Duration-Seconds": str(duration_seconds),
                "X-Job-Id": job_id,
                "Content-Disposition": f"attachment; filename=lipsync_{job_id}.{output_format}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lip sync generation failed: {e}")
        if work_dir.exists():
            shutil.rmtree(work_dir)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-to-file")
async def generate_lipsync_to_file(
    reference_image: UploadFile = File(None),
    reference_video: UploadFile = File(None),
    audio: UploadFile = File(...),
    reference_image_url: str = Form(None),
    output_format: str = Form("mp4"),
    fps: int = Form(25)
):
    """
    Generate lip-synced video and save to output directory.
    Returns the file path.
    """
    job_id = uuid.uuid4().hex[:12]
    work_dir = Path(TEMP_DIR) / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get reference
        if reference_image:
            ref_path = work_dir / "reference.jpg"
            with open(ref_path, 'wb') as f:
                f.write(await reference_image.read())
        elif reference_video:
            ref_path = work_dir / "reference.mp4"
            with open(ref_path, 'wb') as f:
                f.write(await reference_video.read())
        elif reference_image_url:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(reference_image_url)
                ref_path = work_dir / "reference.jpg"
                with open(ref_path, 'wb') as f:
                    f.write(response.content)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide reference"
            )

        # Save audio
        audio_path = work_dir / "audio.wav"
        with open(audio_path, 'wb') as f:
            f.write(await audio.read())

        # Output to persistent directory
        output_filename = f"lipsync_{job_id}.{output_format}"
        output_path = Path(OUTPUT_DIR) / output_filename

        # Run Wav2Lip
        cmd = [
            "python3", f"{WAV2LIP_DIR}/inference.py",
            "--checkpoint_path", CHECKPOINT_PATH,
            "--face", str(ref_path),
            "--audio", str(audio_path),
            "--outfile", str(output_path),
            "--fps", str(fps),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=WAV2LIP_DIR)

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Generation failed: {result.stderr[:500]}")

        # Get duration
        cap = cv2.VideoCapture(str(output_path))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps_actual = cap.get(cv2.CAP_PROP_FPS)
        duration_seconds = frame_count / fps_actual if fps_actual > 0 else 0
        cap.release()

        # Clean up work dir
        shutil.rmtree(work_dir)

        return {
            "success": True,
            "job_id": job_id,
            "output_path": str(output_path),
            "duration_seconds": duration_seconds,
            "format": output_format
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        if work_dir.exists():
            shutil.rmtree(work_dir)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Utility Endpoints
# =============================================================================

@app.post("/validate-reference")
async def validate_reference(file: UploadFile = File(...)):
    """
    Validate a reference image/video for lip sync.
    Checks for face presence, quality, and compatibility.
    """
    try:
        # Save file
        suffix = ".mp4" if "video" in file.content_type else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            input_path = tmp.name

        issues = []

        if suffix == ".mp4":
            # Video validation
            cap = cv2.VideoCapture(input_path)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            cap.release()

            # Extract a frame for face detection
            temp_frame = f"{TEMP_DIR}/validate_frame.jpg"
            success = extract_face_frame(input_path, temp_frame)

            if not success:
                issues.append("No face detected in video")
            else:
                os.unlink(temp_frame)

            if width < 256 or height < 256:
                issues.append(f"Resolution too low ({width}x{height})")

            info = {
                "type": "video",
                "duration_seconds": duration,
                "resolution": f"{width}x{height}",
                "fps": fps,
                "frame_count": frame_count
            }
        else:
            # Image validation
            image = cv2.imread(input_path)
            if image is None:
                issues.append("Could not read image")
            else:
                height, width = image.shape[:2]
                face_box = detect_face(input_path)

                if face_box is None:
                    issues.append("No face detected in image")
                else:
                    x1, y1, x2, y2 = face_box
                    face_size = (x2 - x1) * (y2 - y1)
                    face_percent = (face_size / (width * height)) * 100

                    if face_percent < 5:
                        issues.append(f"Face too small ({face_percent:.1f}% of image)")

                if width < 256 or height < 256:
                    issues.append(f"Resolution too low ({width}x{height})")

            info = {
                "type": "image",
                "resolution": f"{width}x{height}" if image is not None else "unknown"
            }

        os.unlink(input_path)

        return {
            "valid": len(issues) == 0,
            "info": info,
            "issues": issues
        }

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Startup
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info(f"Lip Sync Service starting on {DEVICE}")
    if DEVICE == "cuda":
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")

    # Check for required files
    if not Path(CHECKPOINT_PATH).exists():
        logger.warning(f"Wav2Lip checkpoint not found at {CHECKPOINT_PATH}")
        logger.warning("Download from: https://github.com/Rudrabha/Wav2Lip")

    if not Path(WAV2LIP_DIR).exists():
        logger.warning(f"Wav2Lip directory not found at {WAV2LIP_DIR}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5502)
