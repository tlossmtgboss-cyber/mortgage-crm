"""
Video Render Worker
Background worker that processes render jobs using FFmpeg and self-hosted AI models.

This worker handles the entire render pipeline:
1. Script generation (LLM)
2. Voiceover generation (TTS)
3. Visual generation (Diffusion models)
4. Video composition (FFmpeg)
5. Post-processing (captions, effects, etc.)
"""

import os
import json
import uuid
import shutil
import logging
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import re


def _sanitize_hex_color(color: str) -> str:
    """Validate and return a safe hex color string for FFmpeg."""
    if isinstance(color, str) and re.match(r'^#[0-9A-Fa-f]{3,8}$', color):
        return color
    return "#1a365d"  # default fallback


def _sanitize_float_param(value, min_val: float = 0.0, max_val: float = 1.0, default: float = 0.5) -> float:
    """Validate a numeric parameter is within safe bounds for FFmpeg."""
    try:
        val = float(value)
        if min_val <= val <= max_val:
            return val
    except (TypeError, ValueError):
        pass
    return default


def _sanitize_ffmpeg_text(text: str) -> str:
    """Escape text for safe use in FFmpeg drawtext filter."""
    if not isinstance(text, str):
        return ""
    # FFmpeg drawtext special chars: ' : \ % { }
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    # Remove any control characters
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    return text


def _sanitize_font_name(font: str) -> str:
    """Validate font name contains only safe characters."""
    if isinstance(font, str) and re.match(r'^[a-zA-Z0-9_-]+$', font):
        return font
    return "Roboto"

logger = logging.getLogger(__name__)

# Configuration
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")
WORKER_ID = os.getenv("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
TEMP_DIR = os.getenv("VIDEO_TEMP_DIR", "/tmp/video_render")
OUTPUT_DIR = os.getenv("VIDEO_OUTPUT_DIR", "/var/data/videos")
S3_BUCKET = os.getenv("VIDEO_S3_BUCKET", "")
LOCAL_TTS_URL = os.getenv("LOCAL_TTS_URL", "http://localhost:5500")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:8080")
LOCAL_DIFFUSION_URL = os.getenv("LOCAL_DIFFUSION_URL", "http://localhost:7860")

# Format configurations
FORMAT_CONFIGS = {
    "portrait_9x16": {"width": 1080, "height": 1920, "aspect": "9:16"},
    "square_1x1": {"width": 1080, "height": 1080, "aspect": "1:1"},
    "landscape_16x9": {"width": 1920, "height": 1080, "aspect": "16:9"},
}


@dataclass
class RenderContext:
    """Context for a render job."""
    job_id: str  # String job ID (e.g., "VRJ-XXXX") for logging/paths
    render_job_db_id: int  # Integer database ID for service calls
    project_id: int
    format: str
    resolution: str
    fps: int
    work_dir: Path
    output_dir: Path
    brand_template: Dict[str, Any]
    voice_profile: Dict[str, Any]
    scenes: List[Dict[str, Any]]
    artifacts: Dict[str, Path] = None
    organization_id: int = None

    def __post_init__(self):
        self.artifacts = {}


class VideoRenderWorker:
    """Worker that processes video render jobs."""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._running = False

    def start(self):
        """Start the worker loop."""
        self._running = True
        logger.info(f"Video render worker {WORKER_ID} starting...")

        while self._running:
            try:
                self._process_next_job()
            except Exception as e:
                logger.exception("Error in worker loop")
                import time
                time.sleep(5)

    def stop(self):
        """Stop the worker."""
        self._running = False
        self.executor.shutdown(wait=True)
        logger.info(f"Video render worker {WORKER_ID} stopped")

    def _process_next_job(self):
        """Claim and process the next available job."""
        from services.video_render_service import video_render_service

        db = self.db_session_factory()
        try:
            # Try to claim a job
            job = video_render_service.claim_next_job(db, WORKER_ID)
            if not job:
                import time
                time.sleep(2)  # No jobs available, wait
                return

            logger.info(f"Processing render job {job['job_id']}")

            # Process the job
            self._process_job(db, job)

        except Exception as e:
            logger.exception(f"Failed to process job")
        finally:
            db.close()

    def _process_job(self, db, job: Dict[str, Any]):
        """Process a single render job through all stages."""
        from services.video_render_service import video_render_service, RenderState
        from services.video_project_service import video_project_service

        job_id = job["job_id"]
        work_dir = Path(TEMP_DIR) / job_id
        output_dir = Path(OUTPUT_DIR) / job_id

        try:
            # Setup directories
            work_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Get project details
            project = video_project_service.get_project(db, job["project_id"])
            if not project:
                raise ValueError(f"Project {job['project_id']} not found")

            # Get brand template
            brand_template = {}
            if project.get("brand_template_id"):
                brand_template = video_project_service.get_brand_template(
                    db, project["brand_template_id"]
                ) or {}

            # Get voice profile
            voice_profile = {}
            if project.get("voice_profile_id"):
                voice_profile = video_project_service.get_voice_profile(
                    db, project["voice_profile_id"]
                ) or {}

            # Get scenes
            scenes = video_project_service.get_storyboard_scenes(db, project["id"])

            # Create render context
            ctx = RenderContext(
                job_id=job_id,
                render_job_db_id=job["id"],  # Integer database ID
                project_id=project["id"],
                format=job["format"],
                resolution=job["resolution"],
                fps=job["fps"],
                work_dir=work_dir,
                output_dir=output_dir,
                brand_template=brand_template,
                voice_profile=voice_profile,
                scenes=scenes,
            )

            # Execute render pipeline
            self._execute_pipeline(db, ctx, job)

        except Exception as e:
            logger.exception(f"Job {job_id} failed")
            video_render_service.fail_job(db, job_id, str(e), {"traceback": str(e)})
        finally:
            # Cleanup work directory
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    def _execute_pipeline(self, db, ctx: RenderContext, job: Dict[str, Any]):
        """Execute the full render pipeline."""
        from services.video_render_service import video_render_service, RenderState

        # ctx.render_job_db_id is the integer database ID for service calls
        # ctx.job_id is the string job ID (e.g., "VRJ-XXXX") for logging
        db_id = ctx.render_job_db_id

        # Stage 1: Generate/verify script
        video_render_service.update_progress(db, db_id, 5, "Preparing script")
        self._ensure_script(db, ctx)
        video_render_service.transition_state(db, db_id, RenderState.SCRIPTED)

        # Stage 2: Generate voiceover
        video_render_service.update_progress(db, db_id, 15, "Generating voiceover")
        self._generate_voiceover(db, ctx)
        video_render_service.transition_state(db, db_id, RenderState.VOICED)

        # Stage 3: Generate storyboard visuals
        video_render_service.update_progress(db, db_id, 30, "Generating storyboard")
        self._ensure_storyboard(db, ctx)
        video_render_service.transition_state(db, db_id, RenderState.STORYBOARDED)

        # Stage 4: Generate visuals
        video_render_service.update_progress(db, db_id, 50, "Generating visuals")
        self._generate_visuals(db, ctx)
        video_render_service.transition_state(db, db_id, RenderState.VISUALIZED)

        # Stage 5: Render video
        video_render_service.update_progress(db, db_id, 70, "Rendering video")
        video_render_service.transition_state(db, db_id, RenderState.RENDERING)
        output_path = self._render_video(db, ctx)

        # Stage 6: Post-processing
        video_render_service.update_progress(db, db_id, 90, "Post-processing")
        final_path = self._post_process(db, ctx, output_path)

        # Stage 7: Upload and finalize
        video_render_service.update_progress(db, db_id, 95, "Uploading")
        video_url = self._upload_video(ctx, final_path)

        # Get video metadata
        duration, file_size = self._get_video_metadata(final_path)

        # Save artifact
        video_render_service.add_artifact(
            db=db,
            render_job_id=db_id,
            artifact_type="final_video",
            file_url=video_url,
            file_size_bytes=file_size,
            mime_type="video/mp4",
            duration_seconds=duration,
            resolution=ctx.resolution,
        )

        # Complete the job (uses string job_id for lookup)
        video_render_service.complete_job(db, ctx.job_id, duration, file_size)
        video_render_service.update_progress(db, db_id, 100, "Complete")
        video_render_service.transition_state(db, db_id, RenderState.RENDERED)

        logger.info(f"Job {ctx.job_id} completed successfully")

    # =========================================================================
    # PIPELINE STAGES
    # =========================================================================

    def _ensure_script(self, db, ctx: RenderContext):
        """Ensure the project has a script."""
        from services.video_project_service import video_project_service

        project = video_project_service.get_project(db, ctx.project_id)
        if not project.get("generated_script"):
            video_project_service.generate_script(db, ctx.project_id)

    def _generate_voiceover(self, db, ctx: RenderContext):
        """Generate voiceover audio for all scenes."""
        from services.video_render_service import video_render_service

        audio_files = []

        for i, scene in enumerate(ctx.scenes):
            voiceover_text = scene.get("voiceover_text", "")
            if not voiceover_text:
                continue

            # Generate audio using local TTS
            audio_path = ctx.work_dir / f"scene_{i:03d}_audio.wav"
            self._generate_tts_audio(voiceover_text, audio_path, ctx.voice_profile)
            audio_files.append(audio_path)

            # Get audio duration and update scene timing
            duration = self._get_audio_duration(audio_path)
            scene["audio_path"] = str(audio_path)
            scene["duration_seconds"] = duration

            # Save as artifact
            video_render_service.add_artifact(
                db=db,
                render_job_id=ctx.render_job_db_id,
                artifact_type=f"voiceover_scene_{i}",
                file_url=str(audio_path),
                duration_seconds=duration,
                mime_type="audio/wav",
            )

        ctx.artifacts["audio_files"] = audio_files

    def _ensure_storyboard(self, db, ctx: RenderContext):
        """Ensure all scenes have storyboard data."""
        from services.video_project_service import video_project_service

        if not ctx.scenes:
            video_project_service.generate_storyboard(db, ctx.project_id)
            ctx.scenes = video_project_service.get_storyboard_scenes(db, ctx.project_id)

    def _generate_visuals(self, db, ctx: RenderContext):
        """Generate visual assets for all scenes."""
        from services.video_render_service import video_render_service

        format_config = FORMAT_CONFIGS.get(ctx.format, FORMAT_CONFIGS["portrait_9x16"])
        width, height = format_config["width"], format_config["height"]

        futures = []
        for i, scene in enumerate(ctx.scenes):
            if scene.get("visual_url"):
                # Already has a visual
                scene["visual_path"] = self._download_asset(
                    scene["visual_url"],
                    ctx.work_dir / f"scene_{i:03d}_visual.png"
                )
            elif scene.get("visual_prompt"):
                # Generate visual from prompt
                future = self.executor.submit(
                    self._generate_image,
                    scene["visual_prompt"],
                    ctx.work_dir / f"scene_{i:03d}_visual.png",
                    width,
                    height,
                    scene.get("visual_style", "professional"),
                )
                futures.append((i, future))
            else:
                # Use placeholder
                scene["visual_path"] = self._create_placeholder_image(
                    ctx.work_dir / f"scene_{i:03d}_visual.png",
                    width,
                    height,
                    ctx.brand_template,
                )

        # Wait for all image generation to complete
        for i, future in futures:
            try:
                image_path = future.result(timeout=120)
                ctx.scenes[i]["visual_path"] = str(image_path)

                video_render_service.add_artifact(
                    db=db,
                    render_job_id=ctx.render_job_db_id,
                    artifact_type=f"visual_scene_{i}",
                    file_url=str(image_path),
                    mime_type="image/png",
                )
            except Exception as e:
                logger.error(f"Failed to generate visual for scene {i}: {e}")
                ctx.scenes[i]["visual_path"] = self._create_placeholder_image(
                    ctx.work_dir / f"scene_{i:03d}_visual.png",
                    width,
                    height,
                    ctx.brand_template,
                )

    def _render_video(self, db, ctx: RenderContext) -> Path:
        """Render the final video using FFmpeg."""
        format_config = FORMAT_CONFIGS.get(ctx.format, FORMAT_CONFIGS["portrait_9x16"])
        width, height = format_config["width"], format_config["height"]

        output_path = ctx.output_dir / "output.mp4"
        temp_segments = []

        # Render each scene as a segment
        for i, scene in enumerate(ctx.scenes):
            segment_path = ctx.work_dir / f"segment_{i:03d}.mp4"
            self._render_scene_segment(scene, segment_path, width, height, ctx)
            temp_segments.append(segment_path)

        # Concatenate all segments
        if len(temp_segments) == 1:
            shutil.copy(temp_segments[0], output_path)
        else:
            self._concatenate_videos(temp_segments, output_path)

        # Add intro/outro if configured
        if ctx.brand_template.get("intro_video_url") or ctx.brand_template.get("outro_video_url"):
            output_path = self._add_intro_outro(ctx, output_path)

        # Add background music if configured
        if ctx.brand_template.get("background_music_url"):
            output_path = self._add_background_music(ctx, output_path)

        return output_path

    def _render_scene_segment(
        self,
        scene: Dict[str, Any],
        output_path: Path,
        width: int,
        height: int,
        ctx: RenderContext
    ):
        """Render a single scene segment."""
        visual_path = scene.get("visual_path")
        audio_path = scene.get("audio_path")
        duration = scene.get("duration_seconds", 3.0)
        motion_style = scene.get("motion_style", "ken_burns")

        # Build FFmpeg filter complex
        filter_parts = []

        # Motion effect on image
        if motion_style == "ken_burns":
            filter_parts.append(
                f"scale={width*1.1}:{height*1.1},"
                f"zoompan=z='1.1':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={int(duration*ctx.fps)}:s={width}x{height}:fps={ctx.fps}"
            )
        elif motion_style == "zoom_in":
            filter_parts.append(
                f"scale={width*1.2}:{height*1.2},"
                f"zoompan=z='min(zoom+0.001,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={int(duration*ctx.fps)}:s={width}x{height}:fps={ctx.fps}"
            )
        elif motion_style == "pan_left":
            filter_parts.append(
                f"scale={int(width*1.3)}:{height},"
                f"crop={width}:{height}:x='(iw-ow)*t/{duration}':y=0"
            )
        else:  # static
            filter_parts.append(f"scale={width}:{height}")

        # Add captions if voiceover text exists
        voiceover_text = scene.get("voiceover_text", "")
        if voiceover_text and ctx.brand_template.get("caption_style"):
            filter_parts.append(self._build_caption_filter(scene, ctx, width, height))

        filter_complex = ",".join(filter_parts) if filter_parts else f"scale={width}:{height}"

        # Build FFmpeg command
        cmd = [FFMPEG_PATH, "-y"]

        # Input image (looped for duration)
        cmd.extend(["-loop", "1", "-i", str(visual_path)])

        # Input audio if available
        if audio_path and Path(audio_path).exists():
            cmd.extend(["-i", str(audio_path)])
            audio_mapping = ["-map", "0:v", "-map", "1:a", "-shortest"]
        else:
            cmd.extend(["-t", str(duration)])
            audio_mapping = ["-map", "0:v"]

        # Filter and encoding
        cmd.extend([
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
        ])

        if audio_path:
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])

        cmd.extend(audio_mapping)
        cmd.append(str(output_path))

        # Execute FFmpeg
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    def _post_process(self, db, ctx: RenderContext, video_path: Path) -> Path:
        """Apply post-processing to the video."""
        output_path = ctx.output_dir / "final.mp4"

        # Add watermark if configured
        watermark_url = ctx.brand_template.get("watermark_url")
        if watermark_url:
            watermark_path = self._download_asset(
                watermark_url,
                ctx.work_dir / "watermark.png"
            )
            video_path = self._add_watermark(video_path, watermark_path, output_path, ctx)
        else:
            shutil.copy(video_path, output_path)

        # Add disclaimer if configured
        if ctx.brand_template.get("show_disclaimer") and ctx.brand_template.get("disclaimer_text"):
            video_path = self._add_disclaimer(output_path, ctx)

        return output_path

    def _upload_video(self, ctx: RenderContext, video_path: Path) -> str:
        """Upload video to storage and return URL."""
        if S3_BUCKET:
            # Upload to S3
            return self._upload_to_s3(video_path, ctx)
        else:
            # Return local path
            return f"/videos/{ctx.job_id}/final.mp4"

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _generate_tts_audio(self, text: str, output_path: Path, voice_profile: Dict[str, Any]):
        """Generate TTS audio using local TTS service."""
        import requests

        try:
            response = requests.post(
                f"{LOCAL_TTS_URL}/tts",
                json={
                    "text": text,
                    "voice_id": voice_profile.get("voice_id", "default"),
                    "speaking_rate": voice_profile.get("speaking_rate", 1.0),
                    "pitch": voice_profile.get("pitch", 1.0),
                },
                timeout=60
            )
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)
        except Exception as e:
            logger.warning(f"TTS failed, using placeholder: {e}")
            self._create_silence(output_path, 3.0)

    def _generate_image(
        self,
        prompt: str,
        output_path: Path,
        width: int,
        height: int,
        style: str = "professional"
    ) -> Path:
        """Generate image using local diffusion model or OpenAI DALL-E fallback."""
        import requests
        import os

        enhanced_prompt = f"{style} style, {prompt}, high quality, 4k, professional photography"

        # Try local Stable Diffusion first
        try:
            response = requests.post(
                f"{LOCAL_DIFFUSION_URL}/sdapi/v1/txt2img",
                json={
                    "prompt": enhanced_prompt,
                    "negative_prompt": "blurry, low quality, distorted, amateur",
                    "width": width,
                    "height": height,
                    "steps": 30,
                    "cfg_scale": 7.5,
                },
                timeout=120
            )
            response.raise_for_status()

            import base64
            data = response.json()
            image_data = base64.b64decode(data["images"][0])

            with open(output_path, "wb") as f:
                f.write(image_data)

            logger.info(f"Generated image with local diffusion for: {prompt[:50]}...")
            return output_path

        except Exception as e:
            logger.warning(f"Local diffusion failed: {e}, trying OpenAI DALL-E...")

        # Fallback to OpenAI DALL-E
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            try:
                # Determine DALL-E size (must be 1024x1024, 1024x1792, or 1792x1024 for dall-e-3)
                if width > height:
                    dalle_size = "1792x1024"  # landscape
                elif height > width:
                    dalle_size = "1024x1792"  # portrait
                else:
                    dalle_size = "1024x1024"  # square

                response = requests.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "dall-e-3",
                        "prompt": f"{enhanced_prompt}. Professional mortgage and real estate marketing image.",
                        "n": 1,
                        "size": dalle_size,
                        "quality": "standard",
                        "response_format": "b64_json"
                    },
                    timeout=90
                )
                response.raise_for_status()

                import base64
                data = response.json()
                image_data = base64.b64decode(data["data"][0]["b64_json"])

                with open(output_path, "wb") as f:
                    f.write(image_data)

                # Resize to exact dimensions if needed using PIL
                try:
                    from PIL import Image
                    img = Image.open(output_path)
                    if img.size != (width, height):
                        img = img.resize((width, height), Image.Resampling.LANCZOS)
                        img.save(output_path)
                except ImportError:
                    logger.warning("PIL not available, using DALL-E output dimensions")

                logger.info(f"Generated image with DALL-E for: {prompt[:50]}...")
                return output_path

            except Exception as dalle_error:
                logger.warning(f"DALL-E generation failed: {dalle_error}")
        else:
            logger.warning("OPENAI_API_KEY not set, cannot use DALL-E fallback")

        # Final fallback to placeholder
        logger.info(f"Using placeholder image for: {prompt[:50]}...")
        return self._create_placeholder_image(output_path, width, height, {})

    def _create_placeholder_image(
        self,
        output_path: Path,
        width: int,
        height: int,
        brand_template: Dict[str, Any]
    ) -> str:
        """Create a placeholder image with brand colors."""
        bg_color = _sanitize_hex_color(brand_template.get("background_color", "#1a365d"))

        # Use FFmpeg to create a solid color image
        cmd = [
            FFMPEG_PATH, "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={width}x{height}:d=1",
            "-frames:v", "1",
            str(output_path)
        ]
        subprocess.run(cmd, capture_output=True)
        return str(output_path)

    def _create_silence(self, output_path: Path, duration: float):
        """Create a silent audio file."""
        cmd = [
            FFMPEG_PATH, "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            str(output_path)
        ]
        subprocess.run(cmd, capture_output=True)

    def _download_asset(self, url: str, output_path: Path) -> str:
        """Download an asset from URL."""
        import requests

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
            return str(output_path)
        except Exception as e:
            logger.warning(f"Failed to download asset: {e}")
            return str(output_path)

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get duration of an audio file."""
        cmd = [
            FFPROBE_PATH,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Error parsing audio duration: {e}")
            return 3.0

    def _get_video_metadata(self, video_path: Path) -> Tuple[float, int]:
        """Get video duration and file size."""
        # Get duration
        cmd = [
            FFPROBE_PATH,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            duration = float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Error parsing video duration: {e}")
            duration = 0.0

        # Get file size
        file_size = video_path.stat().st_size if video_path.exists() else 0

        return duration, file_size

    def _concatenate_videos(self, segments: List[Path], output_path: Path):
        """Concatenate video segments."""
        # Create concat file
        concat_file = segments[0].parent / "concat.txt"
        with open(concat_file, "w") as f:
            for segment in segments:
                f.write(f"file '{segment}'\n")

        cmd = [
            FFMPEG_PATH, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path)
        ]
        subprocess.run(cmd, capture_output=True)

    def _add_watermark(
        self,
        video_path: Path,
        watermark_path: Path,
        output_path: Path,
        ctx: RenderContext
    ) -> Path:
        """Add watermark to video."""
        position = ctx.brand_template.get("watermark_position", "bottom_right")
        opacity = _sanitize_float_param(ctx.brand_template.get("watermark_opacity", 0.7), 0.0, 1.0, 0.7)

        # Position mapping
        positions = {
            "top_left": "10:10",
            "top_right": "W-w-10:10",
            "bottom_left": "10:H-h-10",
            "bottom_right": "W-w-10:H-h-10",
            "center": "(W-w)/2:(H-h)/2",
        }
        overlay_pos = positions.get(position, "W-w-10:H-h-10")

        cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(video_path),
            "-i", str(watermark_path),
            "-filter_complex",
            f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[wm];"
            f"[0:v][wm]overlay={overlay_pos}",
            "-c:a", "copy",
            str(output_path)
        ]
        subprocess.run(cmd, capture_output=True)
        return output_path

    def _add_background_music(self, ctx: RenderContext, video_path: Path) -> Path:
        """Add background music to video."""
        music_url = ctx.brand_template.get("background_music_url")
        music_volume = _sanitize_float_param(ctx.brand_template.get("music_volume", 0.15), 0.0, 2.0, 0.15)

        music_path = self._download_asset(music_url, ctx.work_dir / "music.mp3")
        output_path = ctx.output_dir / "with_music.mp4"

        cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(video_path),
            "-stream_loop", "-1",
            "-i", str(music_path),
            "-filter_complex",
            f"[1:a]volume={music_volume}[bg];[0:a][bg]amix=inputs=2:duration=first",
            "-c:v", "copy",
            "-shortest",
            str(output_path)
        ]
        subprocess.run(cmd, capture_output=True)
        return output_path

    def _add_intro_outro(self, ctx: RenderContext, video_path: Path) -> Path:
        """Add intro and/or outro to video."""
        segments = []

        if ctx.brand_template.get("intro_video_url"):
            intro_path = self._download_asset(
                ctx.brand_template["intro_video_url"],
                ctx.work_dir / "intro.mp4"
            )
            segments.append(Path(intro_path))

        segments.append(video_path)

        if ctx.brand_template.get("outro_video_url"):
            outro_path = self._download_asset(
                ctx.brand_template["outro_video_url"],
                ctx.work_dir / "outro.mp4"
            )
            segments.append(Path(outro_path))

        if len(segments) == 1:
            return video_path

        output_path = ctx.output_dir / "with_intro_outro.mp4"
        self._concatenate_videos(segments, output_path)
        return output_path

    def _add_disclaimer(self, video_path: Path, ctx: RenderContext) -> Path:
        """Add disclaimer text overlay to video."""
        disclaimer = ctx.brand_template.get("disclaimer_text", "")
        nmls = ctx.brand_template.get("nmls_number", "")

        if nmls:
            disclaimer = f"NMLS #{nmls}. {disclaimer}"

        output_path = ctx.output_dir / "with_disclaimer.mp4"

        cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(video_path),
            "-vf", f"drawtext=text='{disclaimer}':fontsize=16:fontcolor=white@0.7:x=10:y=h-30",
            "-c:a", "copy",
            str(output_path)
        ]
        subprocess.run(cmd, capture_output=True)
        return output_path

    def _build_caption_filter(
        self,
        scene: Dict[str, Any],
        ctx: RenderContext,
        width: int,
        height: int
    ) -> str:
        """Build FFmpeg drawtext filter for captions."""
        text = scene.get("voiceover_text", "")
        style = ctx.brand_template.get("caption_style", "pop")
        font = _sanitize_font_name(ctx.brand_template.get("caption_font", "Roboto"))
        max_words = ctx.brand_template.get("caption_max_words", 3)

        # Escape special characters for FFmpeg drawtext filter
        text = _sanitize_ffmpeg_text(text)

        # Truncate to max words
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]) + "..."

        # Position based on style
        if style == "karaoke":
            y_pos = f"h-{height//4}"
        else:
            y_pos = f"h-{height//5}"

        return (
            f"drawtext=text='{text}':"
            f"fontfile=/usr/share/fonts/truetype/{font}.ttf:"
            f"fontsize=48:fontcolor=white:borderw=3:bordercolor=black:"
            f"x=(w-text_w)/2:y={y_pos}"
        )

    def _upload_to_s3(self, video_path: Path, ctx: RenderContext) -> str:
        """Upload video to S3 using VideoS3Service."""
        from services.video_hosting_service import get_video_s3_service

        video_s3 = get_video_s3_service()
        result = video_s3.upload_video(
            file_path=str(video_path),
            job_id=ctx.job_id,
            artifact_type="final",
            content_type="video/mp4",
            organization_id=ctx.organization_id,
        )

        if result.get("success"):
            return result["url"]
        else:
            # Fallback to local path if upload fails
            logger.warning(f"S3 upload failed: {result.get('error')}, using local path")
            return f"/videos/{ctx.job_id}/final.mp4"


# Entry point for running as standalone worker
def run_worker():
    """Run the video render worker."""
    from database import get_db_session

    worker = VideoRenderWorker(get_db_session)
    try:
        worker.start()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
