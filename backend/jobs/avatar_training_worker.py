"""
Avatar Training Worker

Background worker that processes avatar training videos:
1. Downloads training video from S3/URL
2. Extracts audio track (for voice cloning)
3. Extracts best face frame (for lip sync reference)
4. Creates voice model via XTTS service
5. Updates avatar profile status

Can be run as a standalone process or triggered via job queue.
"""

import os
import io
import time
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

import httpx

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TrainingContext:
    """Context for a training job."""
    avatar_id: int
    training_video_url: str
    work_dir: Path
    voice_clone_url: str
    lip_sync_url: str
    s3_bucket: Optional[str]
    cdn_base_url: Optional[str]


class AvatarTrainingWorker:
    """Worker for processing avatar training videos."""

    def __init__(self):
        """Initialize worker with service URLs."""
        self.voice_clone_url = os.getenv("VOICE_CLONE_SERVICE_URL", "http://localhost:5501")
        self.lip_sync_url = os.getenv("LIP_SYNC_SERVICE_URL", "http://localhost:5502")
        self.s3_bucket = os.getenv("AVATAR_ASSETS_BUCKET", os.getenv("AWS_S3_BUCKET"))
        self.cdn_base_url = os.getenv("AVATAR_CDN_URL", os.getenv("CDN_BASE_URL", ""))
        self.work_base_dir = Path(os.getenv("AVATAR_WORK_DIR", "/tmp/avatar_training"))
        self.work_base_dir.mkdir(parents=True, exist_ok=True)

    async def process_training(
        self,
        db,
        avatar_id: int,
        training_video_url: str
    ) -> bool:
        """
        Process a training video for an avatar.

        Returns True if successful, False otherwise.
        """
        from services.avatar_service import avatar_service

        # Create work directory
        work_dir = self.work_base_dir / f"avatar_{avatar_id}_{int(time.time())}"
        work_dir.mkdir(parents=True, exist_ok=True)

        ctx = TrainingContext(
            avatar_id=avatar_id,
            training_video_url=training_video_url,
            work_dir=work_dir,
            voice_clone_url=self.voice_clone_url,
            lip_sync_url=self.lip_sync_url,
            s3_bucket=self.s3_bucket,
            cdn_base_url=self.cdn_base_url,
        )

        try:
            # Step 1: Download training video (10%)
            logger.info(f"[Avatar {avatar_id}] Downloading training video...")
            avatar_service.update_training_status(
                db, avatar_id, "training", progress=10
            )

            video_path = await self._download_video(ctx)
            if not video_path:
                raise Exception("Failed to download training video")

            # Step 2: Extract audio (30%)
            logger.info(f"[Avatar {avatar_id}] Extracting audio...")
            avatar_service.update_training_status(
                db, avatar_id, "training", progress=30
            )

            audio_path = await self._extract_audio(ctx, video_path)
            if not audio_path:
                raise Exception("Failed to extract audio from video")

            # Step 3: Extract best face frame (50%)
            logger.info(f"[Avatar {avatar_id}] Extracting reference face...")
            avatar_service.update_training_status(
                db, avatar_id, "training", progress=50
            )

            face_path = await self._extract_face(ctx, video_path)
            if not face_path:
                raise Exception("Failed to extract face from video")

            # Step 4: Create voice model (80%)
            logger.info(f"[Avatar {avatar_id}] Creating voice model...")
            avatar_service.update_training_status(
                db, avatar_id, "training", progress=80
            )

            voice_model_id = await self._create_voice_model(ctx, audio_path)
            if not voice_model_id:
                raise Exception("Failed to create voice model")

            # Step 5: Upload assets and finalize (100%)
            logger.info(f"[Avatar {avatar_id}] Uploading assets...")
            avatar_service.update_training_status(
                db, avatar_id, "training", progress=90
            )

            # Upload face reference
            reference_image_url = await self._upload_asset(
                ctx, face_path, f"avatars/{avatar_id}/reference.jpg"
            )

            # Upload voice sample
            voice_sample_url = await self._upload_asset(
                ctx, audio_path, f"avatars/{avatar_id}/voice_sample.wav"
            )

            # Update avatar profile as ready
            avatar_service.update_training_status(
                db, avatar_id, "ready", progress=100,
                reference_image_url=reference_image_url,
                voice_sample_url=voice_sample_url,
                voice_model_id=voice_model_id
            )

            # Log analytics
            avatar_service.log_analytics_event(
                db, avatar_id, "training_completed",
                {"voice_model_id": voice_model_id}
            )

            logger.info(f"[Avatar {avatar_id}] Training completed successfully!")
            return True

        except Exception as e:
            logger.error(f"[Avatar {avatar_id}] Training failed: {e}")
            avatar_service.update_training_status(
                db, avatar_id, "failed", error=str(e)
            )
            avatar_service.log_analytics_event(
                db, avatar_id, "training_failed",
                {"error": "Internal server error"}
            )
            return False

        finally:
            # Clean up work directory
            try:
                import shutil
                shutil.rmtree(work_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up work dir: {e}")

    async def _download_video(self, ctx: TrainingContext) -> Optional[Path]:
        """Download training video to work directory."""
        video_path = ctx.work_dir / "training_video.mp4"

        try:
            url = ctx.training_video_url

            # Handle S3 URLs
            if url.startswith("s3://"):
                import boto3
                s3 = boto3.client('s3')
                bucket, key = url.replace("s3://", "").split("/", 1)
                s3.download_file(bucket, key, str(video_path))
            else:
                # HTTP download
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    with open(video_path, 'wb') as f:
                        f.write(response.content)

            if video_path.exists() and video_path.stat().st_size > 0:
                return video_path

        except Exception as e:
            logger.error(f"Video download failed: {e}")

        return None

    async def _extract_audio(
        self,
        ctx: TrainingContext,
        video_path: Path
    ) -> Optional[Path]:
        """Extract audio track from video using FFmpeg."""
        audio_path = ctx.work_dir / "audio.wav"

        try:
            result = subprocess.run([
                "ffmpeg", "-i", str(video_path),
                "-vn",  # No video
                "-acodec", "pcm_s16le",  # WAV format
                "-ar", "22050",  # Sample rate (good for TTS)
                "-ac", "1",  # Mono
                "-y",  # Overwrite
                str(audio_path)
            ], capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"FFmpeg audio extraction failed: {result.stderr}")
                return None

            # Validate audio duration
            probe_result = subprocess.run([
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path)
            ], capture_output=True, text=True)

            duration = float(probe_result.stdout.strip())
            if duration < 6:
                logger.error(f"Audio too short: {duration}s (need 6s+)")
                return None

            logger.info(f"Extracted {duration:.1f}s of audio")
            return audio_path

        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            return None

    async def _extract_face(
        self,
        ctx: TrainingContext,
        video_path: Path
    ) -> Optional[Path]:
        """Extract best face frame using lip sync service."""
        face_path = ctx.work_dir / "reference_face.jpg"

        try:
            # Use lip sync service's face extraction
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(video_path, 'rb') as f:
                    response = await client.post(
                        f"{ctx.lip_sync_url}/extract-face",
                        files={"file": ("video.mp4", f, "video/mp4")},
                        data={"file_type": "video"}
                    )

                if response.status_code != 200:
                    logger.error(f"Face extraction failed: {response.text}")
                    # Fall back to FFmpeg frame extraction
                    return await self._extract_face_fallback(ctx, video_path)

                with open(face_path, 'wb') as f:
                    f.write(response.content)

                return face_path

        except Exception as e:
            logger.warning(f"Face extraction via service failed: {e}")
            return await self._extract_face_fallback(ctx, video_path)

    async def _extract_face_fallback(
        self,
        ctx: TrainingContext,
        video_path: Path
    ) -> Optional[Path]:
        """Fallback face extraction using FFmpeg."""
        face_path = ctx.work_dir / "reference_face.jpg"

        try:
            # Extract frame at 2 seconds (usually good lighting/pose)
            result = subprocess.run([
                "ffmpeg", "-i", str(video_path),
                "-ss", "2",  # Seek to 2 seconds
                "-vframes", "1",  # Extract 1 frame
                "-q:v", "2",  # High quality
                "-y",
                str(face_path)
            ], capture_output=True, text=True)

            if result.returncode == 0 and face_path.exists():
                return face_path

        except Exception as e:
            logger.error(f"Fallback face extraction failed: {e}")

        return None

    async def _create_voice_model(
        self,
        ctx: TrainingContext,
        audio_path: Path
    ) -> Optional[str]:
        """Create voice model using voice clone service."""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                with open(audio_path, 'rb') as f:
                    response = await client.post(
                        f"{ctx.voice_clone_url}/voices/create",
                        files={"audio_file": ("voice.wav", f, "audio/wav")},
                        data={"name": f"Avatar {ctx.avatar_id}"}
                    )

                if response.status_code != 200:
                    logger.error(f"Voice model creation failed: {response.text}")
                    return None

                result = response.json()
                return result.get("model_id")

        except Exception as e:
            logger.error(f"Voice model creation failed: {e}")
            return None

    async def _upload_asset(
        self,
        ctx: TrainingContext,
        local_path: Path,
        s3_key: str
    ) -> str:
        """Upload asset to S3 and return URL."""
        try:
            if ctx.s3_bucket:
                import boto3
                s3 = boto3.client('s3')
                s3.upload_file(
                    str(local_path),
                    ctx.s3_bucket,
                    s3_key,
                    ExtraArgs={'ContentType': self._get_content_type(local_path)}
                )

                if ctx.cdn_base_url:
                    return f"{ctx.cdn_base_url}/{s3_key}"
                return f"s3://{ctx.s3_bucket}/{s3_key}"
            else:
                # Local storage fallback
                dest_dir = Path("/data/avatars") / str(ctx.avatar_id)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / local_path.name

                import shutil
                shutil.copy(local_path, dest_path)
                return f"file://{dest_path}"

        except Exception as e:
            logger.error(f"Asset upload failed: {e}")
            return f"file://{local_path}"

    def _get_content_type(self, path: Path) -> str:
        """Get content type for file."""
        suffix = path.suffix.lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".mp4": "video/mp4",
        }
        return content_types.get(suffix, "application/octet-stream")


# Worker instance
avatar_training_worker = AvatarTrainingWorker()


async def process_pending_training_jobs():
    """Process any pending avatar training jobs."""
    from database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # Find avatars in 'processing' status (uploaded but not trained)
        result = db.execute(text("""
            SELECT id, training_video_url
            FROM video_avatar_profiles
            WHERE status = 'processing'
            ORDER BY updated_at ASC
            LIMIT 5
        """))

        pending = result.fetchall()
        if not pending:
            return

        logger.info(f"Found {len(pending)} pending training jobs")

        for avatar_id, video_url in pending:
            await avatar_training_worker.process_training(
                db, avatar_id, video_url
            )

    finally:
        db.close()


if __name__ == "__main__":
    import asyncio

    async def main():
        """Run worker as standalone process."""
        logger.info("Avatar Training Worker started")
        while True:
            try:
                await process_pending_training_jobs()
            except Exception as e:
                logger.error(f"Worker error: {e}")

            # Poll every 30 seconds
            await asyncio.sleep(30)

    asyncio.run(main())
