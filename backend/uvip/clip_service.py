"""
Clip Service - Handle video clip uploads, processing, and management

Provides:
- Presigned URL generation for uploads
- Video processing (thumbnail, transcoding)
- Transcription integration
- Share link management
- View tracking
- Analytics aggregation
"""

import os
import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ClipService:
    """Service for managing async video clips"""

    def __init__(self):
        self.s3_enabled = bool(os.getenv('AWS_ACCESS_KEY_ID'))
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'pipeline360-clips')
        self.s3_region = os.getenv('AWS_REGION', 'us-east-1')
        self.cdn_url = os.getenv('CDN_URL', '')

        if self.s3_enabled:
            try:
                import boto3
                self.s3_client = boto3.client(
                    's3',
                    region_name=self.s3_region,
                    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
                )
                logger.info("S3 client initialized for clip storage")
            except Exception as e:
                logger.warning(f"S3 not configured: {e}")
                self.s3_enabled = False
                self.s3_client = None

    async def create_clip(
        self,
        user_id: int,
        title: str,
        clip_type: str = "screen_camera",
        description: str = None,
        template_id: int = None,
        crm_entity_type: str = None,
        crm_entity_id: int = None,
        tags: List[str] = None,
        organization_id: int = None,
        db: Session = None,
        models: Dict = None
    ) -> Dict[str, Any]:
        """Create a new clip record and return upload URL"""

        VideoClip = models.get('VideoClip')
        if not VideoClip:
            raise ValueError("VideoClip model not available")

        # Generate storage path
        timestamp = datetime.now(timezone.utc).strftime('%Y/%m/%d')
        clip_uuid = secrets.token_hex(16)
        storage_path = f"clips/{organization_id or 'default'}/{timestamp}/{clip_uuid}"

        # Create clip record
        clip = VideoClip(
            user_id=user_id,
            organization_id=organization_id,
            title=title,
            description=description,
            clip_type=clip_type,
            storage_path=storage_path,
            template_id=template_id,
            crm_entity_type=crm_entity_type,
            crm_entity_id=crm_entity_id,
            tags=tags or [],
            status='uploading'
        )

        # Generate share token
        clip.share_token = secrets.token_urlsafe(24)

        db.add(clip)
        db.commit()
        db.refresh(clip)

        # Generate presigned upload URL
        upload_url = await self._generate_upload_url(storage_path)

        return {
            "clip_id": clip.id,
            "share_token": clip.share_token,
            "storage_path": storage_path,
            "upload_url": upload_url,
            "upload_expires_in": 3600
        }

    async def _generate_upload_url(self, storage_path: str) -> str:
        """Generate presigned URL for video upload"""

        if not self.s3_enabled:
            # Return mock URL for development
            return f"/api/v1/clips/upload-mock/{storage_path}"

        try:
            s3_key = f"{storage_path}/video.webm"

            presigned_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key,
                    'ContentType': 'video/webm'
                },
                ExpiresIn=3600
            )

            return presigned_url

        except Exception as e:
            logger.error(f"Error generating upload URL: {e}")
            raise

    async def complete_upload(
        self,
        clip_id: int,
        file_size_bytes: int,
        duration_seconds: int,
        video_width: int = None,
        video_height: int = None,
        db: Session = None,
        models: Dict = None
    ) -> Dict[str, Any]:
        """Mark upload as complete and trigger processing"""

        VideoClip = models.get('VideoClip')

        clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")

        clip.file_size_bytes = file_size_bytes
        clip.duration_seconds = duration_seconds
        clip.video_width = video_width
        clip.video_height = video_height
        clip.status = 'processing'
        clip.processing_started_at = datetime.now(timezone.utc)

        # Set video URL
        clip.video_url = self._get_video_url(clip.storage_path)

        db.commit()
        db.refresh(clip)

        return {
            "clip_id": clip.id,
            "status": clip.status,
            "video_url": clip.video_url
        }

    def _get_video_url(self, storage_path: str) -> str:
        """Get public URL for video"""

        if self.cdn_url:
            return f"{self.cdn_url}/{storage_path}/video.webm"

        if self.s3_enabled:
            return f"https://{self.bucket_name}.s3.{self.s3_region}.amazonaws.com/{storage_path}/video.webm"

        return f"/api/v1/clips/video/{storage_path}"

    async def process_clip(
        self,
        clip_id: int,
        db: Session = None,
        models: Dict = None
    ) -> Dict[str, Any]:
        """Process uploaded clip (thumbnail, transcription)"""

        VideoClip = models.get('VideoClip')

        clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")

        try:
            # Update progress
            clip.processing_progress = 10
            db.commit()

            # Generate thumbnail
            thumbnail_url = await self._generate_thumbnail(clip)
            clip.thumbnail_path = thumbnail_url
            clip.processing_progress = 40
            db.commit()

            # Transcribe audio
            clip.processing_progress = 50
            db.commit()

            transcript_result = await self._transcribe_clip(clip)
            if transcript_result:
                clip.has_transcript = True
                clip.transcript_text = transcript_result.get('text', '')
                clip.transcript_words = transcript_result.get('words', [])
                clip.transcript_language = transcript_result.get('language', 'en')

            clip.processing_progress = 100
            clip.status = 'ready'
            clip.processing_completed_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "clip_id": clip.id,
                "status": "ready",
                "thumbnail_url": clip.thumbnail_path,
                "has_transcript": clip.has_transcript
            }

        except Exception as e:
            logger.error(f"Error processing clip {clip_id}: {e}")
            clip.status = 'failed'
            clip.processing_error = str(e)
            db.commit()
            raise

    async def _generate_thumbnail(self, clip) -> str:
        """Generate thumbnail from video at 1 second mark"""

        # For now, return placeholder thumbnail
        # In production, use FFmpeg to extract frame
        return f"/api/v1/clips/thumbnail/{clip.id}"

    async def _transcribe_clip(self, clip) -> Optional[Dict]:
        """Transcribe clip audio using Whisper or Deepgram"""

        try:
            # Use existing transcription service if available
            from uvip.ai_processing_service import get_ai_processing_service

            ai_service = get_ai_processing_service()

            # For now, return mock transcription
            # In production, download audio and transcribe
            return {
                "text": "",
                "words": [],
                "language": "en"
            }

        except Exception as e:
            logger.warning(f"Transcription not available: {e}")
            return None

    async def create_share(
        self,
        clip_id: int,
        created_by_id: int,
        recipient_email: str = None,
        recipient_name: str = None,
        allow_download: bool = False,
        allow_comments: bool = True,
        require_email: bool = False,
        max_views: int = None,
        expires_in_days: int = None,
        db: Session = None,
        models: Dict = None
    ) -> Dict[str, Any]:
        """Create shareable link for clip"""

        VideoClip = models.get('VideoClip')
        ClipShare = models.get('ClipShare')

        clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")

        # Generate share token
        share_token = secrets.token_urlsafe(24)
        base_url = os.getenv('FRONTEND_URL', 'https://pipeline360.com')
        share_url = f"{base_url}/watch/{share_token}"

        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        share = ClipShare(
            clip_id=clip_id,
            created_by_id=created_by_id,
            share_token=share_token,
            share_url=share_url,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            allow_download=allow_download,
            allow_comments=allow_comments,
            require_email=require_email,
            max_views=max_views,
            expires_at=expires_at
        )

        db.add(share)
        db.commit()
        db.refresh(share)

        return {
            "share_id": share.id,
            "share_token": share_token,
            "share_url": share_url,
            "expires_at": expires_at.isoformat() if expires_at else None
        }

    async def track_view(
        self,
        clip_id: int,
        share_id: int = None,
        viewer_email: str = None,
        viewer_name: str = None,
        viewer_user_id: int = None,
        session_id: str = None,
        ip_address: str = None,
        user_agent: str = None,
        referrer: str = None,
        db: Session = None,
        models: Dict = None
    ) -> Dict[str, Any]:
        """Track clip view and return view session"""

        VideoClip = models.get('VideoClip')
        ClipView = models.get('ClipView')
        ClipShare = models.get('ClipShare')

        clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")

        # Generate session ID if not provided
        if not session_id:
            session_id = secrets.token_hex(16)

        # Parse user agent for device info
        device_type, browser, os_name = self._parse_user_agent(user_agent)

        view = ClipView(
            clip_id=clip_id,
            share_id=share_id,
            viewer_email=viewer_email,
            viewer_name=viewer_name,
            viewer_user_id=viewer_user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            referrer=referrer,
            device_type=device_type,
            browser=browser,
            os=os_name
        )

        db.add(view)

        # Update clip view count
        clip.view_count += 1

        # Check if unique viewer (by session)
        existing_views = db.query(ClipView).filter(
            ClipView.clip_id == clip_id,
            ClipView.session_id == session_id
        ).count()

        if existing_views == 0:
            clip.unique_view_count += 1

        # Update share view count
        if share_id:
            share = db.query(ClipShare).filter(ClipShare.id == share_id).first()
            if share:
                share.view_count += 1
                share.last_viewed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(view)

        # Trigger notification to clip creator
        await self._notify_clip_viewed(clip, view, db, models)

        return {
            "view_id": view.id,
            "session_id": session_id,
            "clip_id": clip_id
        }

    def _parse_user_agent(self, user_agent: str) -> tuple:
        """Parse user agent string for device info"""

        if not user_agent:
            return ('unknown', 'unknown', 'unknown')

        user_agent_lower = user_agent.lower()

        # Device type
        if 'mobile' in user_agent_lower or 'android' in user_agent_lower:
            device_type = 'mobile'
        elif 'tablet' in user_agent_lower or 'ipad' in user_agent_lower:
            device_type = 'tablet'
        else:
            device_type = 'desktop'

        # Browser
        if 'chrome' in user_agent_lower:
            browser = 'Chrome'
        elif 'firefox' in user_agent_lower:
            browser = 'Firefox'
        elif 'safari' in user_agent_lower:
            browser = 'Safari'
        elif 'edge' in user_agent_lower:
            browser = 'Edge'
        else:
            browser = 'Other'

        # OS
        if 'windows' in user_agent_lower:
            os_name = 'Windows'
        elif 'mac' in user_agent_lower:
            os_name = 'macOS'
        elif 'linux' in user_agent_lower:
            os_name = 'Linux'
        elif 'android' in user_agent_lower:
            os_name = 'Android'
        elif 'ios' in user_agent_lower or 'iphone' in user_agent_lower:
            os_name = 'iOS'
        else:
            os_name = 'Other'

        return (device_type, browser, os_name)

    async def update_view_progress(
        self,
        view_id: int,
        watch_duration_seconds: int,
        completion_rate: float,
        play_events: List = None,
        db: Session = None,
        models: Dict = None
    ) -> Dict[str, Any]:
        """Update view progress and completion"""

        ClipView = models.get('ClipView')
        VideoClip = models.get('VideoClip')

        view = db.query(ClipView).filter(ClipView.id == view_id).first()
        if not view:
            raise ValueError(f"View {view_id} not found")

        # Update view stats
        view.watch_duration_seconds = watch_duration_seconds
        view.completion_rate = min(completion_rate, 1.0)
        view.watched_to_end = completion_rate >= 0.95
        view.ended_at = datetime.now(timezone.utc)

        if play_events:
            view.play_events = play_events

        # Update clip aggregate stats
        clip = db.query(VideoClip).filter(VideoClip.id == view.clip_id).first()
        if clip:
            clip.total_watch_time_seconds += watch_duration_seconds

            # Recalculate average completion
            all_views = db.query(ClipView).filter(
                ClipView.clip_id == clip.id,
                ClipView.completion_rate > 0
            ).all()

            if all_views:
                avg_completion = sum(v.completion_rate for v in all_views) / len(all_views)
                clip.average_completion_rate = avg_completion

        db.commit()

        # Notify if completed watching
        if view.watched_to_end:
            await self._notify_clip_completed(clip, view, db, models)

        return {
            "view_id": view.id,
            "completion_rate": view.completion_rate,
            "watched_to_end": view.watched_to_end
        }

    async def _notify_clip_viewed(
        self,
        clip,
        view,
        db: Session,
        models: Dict
    ):
        """Send notification when clip is viewed"""

        ClipNotification = models.get('ClipNotification')
        if not ClipNotification:
            return

        notification = ClipNotification(
            clip_id=clip.id,
            recipient_id=clip.user_id,
            notification_type='viewed',
            event_data={
                'viewer_name': view.viewer_name or 'Someone',
                'viewer_email': view.viewer_email,
                'viewed_at': view.started_at.isoformat() if view.started_at else None,
                'device_type': view.device_type
            }
        )

        db.add(notification)
        db.commit()

    async def _notify_clip_completed(
        self,
        clip,
        view,
        db: Session,
        models: Dict
    ):
        """Send notification when viewer completes clip"""

        ClipNotification = models.get('ClipNotification')
        if not ClipNotification:
            return

        notification = ClipNotification(
            clip_id=clip.id,
            recipient_id=clip.user_id,
            notification_type='completed',
            event_data={
                'viewer_name': view.viewer_name or 'Someone',
                'viewer_email': view.viewer_email,
                'watch_duration': view.watch_duration_seconds,
                'completed_at': view.ended_at.isoformat() if view.ended_at else None
            }
        )

        db.add(notification)
        db.commit()

    async def get_clip_analytics(
        self,
        clip_id: int,
        db: Session = None,
        models: Dict = None
    ) -> Dict[str, Any]:
        """Get comprehensive analytics for a clip"""

        VideoClip = models.get('VideoClip')
        ClipView = models.get('ClipView')
        ClipShare = models.get('ClipShare')

        clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")

        # Get all views
        views = db.query(ClipView).filter(ClipView.clip_id == clip_id).all()

        # Calculate metrics
        total_views = len(views)
        unique_viewers = len(set(v.session_id for v in views))
        completed_views = sum(1 for v in views if v.watched_to_end)
        completion_rate = completed_views / total_views if total_views > 0 else 0

        # Average watch time
        total_watch_time = sum(v.watch_duration_seconds or 0 for v in views)
        avg_watch_time = total_watch_time / total_views if total_views > 0 else 0

        # Device breakdown
        device_breakdown = {}
        for v in views:
            device = v.device_type or 'unknown'
            device_breakdown[device] = device_breakdown.get(device, 0) + 1

        # Browser breakdown
        browser_breakdown = {}
        for v in views:
            browser = v.browser or 'unknown'
            browser_breakdown[browser] = browser_breakdown.get(browser, 0) + 1

        # Views over time (last 7 days)
        from datetime import timedelta
        views_by_day = {}
        for i in range(7):
            day = datetime.now(timezone.utc).date() - timedelta(days=i)
            views_by_day[day.isoformat()] = sum(
                1 for v in views
                if v.started_at and v.started_at.date() == day
            )

        # Get shares
        shares = db.query(ClipShare).filter(ClipShare.clip_id == clip_id).all()

        return {
            "clip_id": clip_id,
            "title": clip.title,
            "duration_seconds": clip.duration_seconds,
            "created_at": clip.created_at.isoformat() if clip.created_at else None,
            "metrics": {
                "total_views": total_views,
                "unique_viewers": unique_viewers,
                "completed_views": completed_views,
                "completion_rate": round(completion_rate, 3),
                "total_watch_time_seconds": total_watch_time,
                "avg_watch_time_seconds": round(avg_watch_time, 1),
                "share_count": len(shares)
            },
            "device_breakdown": device_breakdown,
            "browser_breakdown": browser_breakdown,
            "views_by_day": views_by_day,
            "recent_views": [
                {
                    "viewer_name": v.viewer_name or "Anonymous",
                    "viewer_email": v.viewer_email,
                    "started_at": v.started_at.isoformat() if v.started_at else None,
                    "completion_rate": v.completion_rate,
                    "device_type": v.device_type
                }
                for v in sorted(views, key=lambda x: x.started_at or datetime.min, reverse=True)[:10]
            ]
        }

    async def get_user_clips(
        self,
        user_id: int,
        status: str = None,
        crm_entity_type: str = None,
        crm_entity_id: int = None,
        search: str = None,
        limit: int = 50,
        offset: int = 0,
        db: Session = None,
        models: Dict = None
    ) -> Dict[str, Any]:
        """Get clips for a user with filters"""

        VideoClip = models.get('VideoClip')

        query = db.query(VideoClip).filter(
            VideoClip.user_id == user_id,
            VideoClip.deleted_at == None
        )

        if status:
            query = query.filter(VideoClip.status == status)

        if crm_entity_type and crm_entity_id:
            query = query.filter(
                VideoClip.crm_entity_type == crm_entity_type,
                VideoClip.crm_entity_id == crm_entity_id
            )

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (VideoClip.title.ilike(search_term)) |
                (VideoClip.description.ilike(search_term)) |
                (VideoClip.transcript_text.ilike(search_term))
            )

        total = query.count()
        clips = query.order_by(VideoClip.created_at.desc()).offset(offset).limit(limit).all()

        return {
            "clips": [
                {
                    "id": c.id,
                    "title": c.title,
                    "description": c.description,
                    "clip_type": c.clip_type,
                    "duration_seconds": c.duration_seconds,
                    "status": c.status,
                    "thumbnail_path": c.thumbnail_path,
                    "video_url": c.video_url,
                    "share_token": c.share_token,
                    "view_count": c.view_count,
                    "average_completion_rate": c.average_completion_rate,
                    "crm_entity_type": c.crm_entity_type,
                    "crm_entity_id": c.crm_entity_id,
                    "has_transcript": c.has_transcript,
                    "tags": c.tags,
                    "created_at": c.created_at.isoformat() if c.created_at else None
                }
                for c in clips
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }

    async def delete_clip(
        self,
        clip_id: int,
        user_id: int,
        db: Session = None,
        models: Dict = None
    ) -> bool:
        """Soft delete a clip"""

        VideoClip = models.get('VideoClip')

        clip = db.query(VideoClip).filter(
            VideoClip.id == clip_id,
            VideoClip.user_id == user_id
        ).first()

        if not clip:
            return False

        clip.deleted_at = datetime.now(timezone.utc)
        clip.status = 'deleted'
        db.commit()

        return True


# Singleton instance
_clip_service = None


def get_clip_service() -> ClipService:
    """Get or create clip service singleton"""
    global _clip_service
    if _clip_service is None:
        _clip_service = ClipService()
    return _clip_service
