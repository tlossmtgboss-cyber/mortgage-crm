"""
Amazon Chime SDK Meeting Service

Wraps boto3 clients for chime-sdk-meetings and chime-sdk-media-pipelines
to provide meeting lifecycle management, attendee management, recording
via media capture pipelines, and live transcription.

Replaces the custom WebRTC signaling + Telnyx telephony integration.
"""

import os
import logging
import uuid
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class ChimeMeetingService:
    """
    Service for managing Amazon Chime SDK meetings.

    Handles:
    - Meeting creation/deletion
    - Attendee creation with join tokens
    - Media capture pipelines (server-side recording to S3)
    - Live transcription via Amazon Transcribe
    """

    def __init__(self):
        self._region = os.getenv("CHIME_MEDIA_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
        self._s3_bucket = os.getenv("CHIME_RECORDING_S3_BUCKET", "perennia-recordings")

        # Chime SDK Meetings client — always uses us-east-1 for the control plane
        self._meetings_client = boto3.client(
            "chime-sdk-meetings",
            region_name="us-east-1",
        )

        # Media pipelines client
        self._pipelines_client = boto3.client(
            "chime-sdk-media-pipelines",
            region_name=self._region,
        )

        # S3 client for presigned URLs and direct operations
        self._s3_client = boto3.client(
            "s3",
            region_name=self._region,
        )

        logger.info(
            f"ChimeMeetingService initialized: region={self._region}, "
            f"bucket={self._s3_bucket}"
        )

    # ------------------------------------------------------------------ #
    # Meeting lifecycle
    # ------------------------------------------------------------------ #

    def create_meeting(
        self,
        external_id: str,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new Chime SDK meeting.

        Args:
            external_id: External meeting identifier (e.g. room_code or room_id)
            region: Media region override (defaults to CHIME_MEDIA_REGION)

        Returns:
            Chime Meeting object containing MeetingId, MediaPlacement, etc.
        """
        media_region = region or self._region
        try:
            response = self._meetings_client.create_meeting(
                ClientRequestToken=str(uuid.uuid4()),
                MediaRegion=media_region,
                ExternalMeetingId=str(external_id),
            )
            meeting = response["Meeting"]
            logger.info(
                f"Created Chime meeting {meeting['MeetingId']} "
                f"for external_id={external_id} in {media_region}"
            )
            return meeting
        except ClientError as e:
            logger.error(f"Failed to create Chime meeting: {e}")
            raise

    def create_attendee(
        self,
        meeting_id: str,
        external_user_id: str,
        capabilities: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Create an attendee for a Chime meeting and get their join token.

        Args:
            meeting_id: Chime MeetingId
            external_user_id: User identifier (user_id or participant_id)
            capabilities: Optional attendee capabilities override

        Returns:
            Attendee object containing AttendeeId and JoinToken
        """
        params: Dict[str, Any] = {
            "MeetingId": meeting_id,
            "ExternalUserId": str(external_user_id),
        }
        if capabilities:
            params["Capabilities"] = capabilities

        try:
            response = self._meetings_client.create_attendee(**params)
            attendee = response["Attendee"]
            logger.info(
                f"Created Chime attendee {attendee['AttendeeId']} "
                f"for user={external_user_id} in meeting={meeting_id}"
            )
            return attendee
        except ClientError as e:
            logger.error(f"Failed to create Chime attendee: {e}")
            raise

    def delete_meeting(self, meeting_id: str) -> bool:
        """
        End a Chime meeting by deleting it.

        Args:
            meeting_id: Chime MeetingId

        Returns:
            True if deleted successfully
        """
        try:
            self._meetings_client.delete_meeting(MeetingId=meeting_id)
            logger.info(f"Deleted Chime meeting {meeting_id}")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotFoundException":
                logger.warning(f"Chime meeting {meeting_id} already deleted")
                return True
            logger.error(f"Failed to delete Chime meeting {meeting_id}: {e}")
            return False

    def get_meeting_join_info(
        self,
        meeting_id: str,
        attendee_id: str,
    ) -> Dict[str, Any]:
        """
        Get the full meeting + attendee info needed by the frontend SDK.

        Args:
            meeting_id: Chime MeetingId
            attendee_id: Chime AttendeeId

        Returns:
            Dict with 'Meeting' and 'Attendee' keys for SDK initialization
        """
        try:
            meeting_resp = self._meetings_client.get_meeting(MeetingId=meeting_id)
            attendee_resp = self._meetings_client.get_attendee(
                MeetingId=meeting_id,
                AttendeeId=attendee_id,
            )
            return {
                "Meeting": meeting_resp["Meeting"],
                "Attendee": attendee_resp["Attendee"],
            }
        except ClientError as e:
            logger.error(f"Failed to get meeting join info: {e}")
            raise

    # ------------------------------------------------------------------ #
    # Recording via Media Capture Pipelines
    # ------------------------------------------------------------------ #

    def start_recording(
        self,
        meeting_id: str,
        s3_prefix: Optional[str] = None,
    ) -> str:
        """
        Start server-side recording via a Chime media capture pipeline.

        The pipeline captures audio+video and writes to S3 in chunks.
        Use stop_recording() to end capture and trigger concatenation.

        Args:
            meeting_id: Chime MeetingId
            s3_prefix: Optional S3 key prefix (defaults to meetings/{meeting_id})

        Returns:
            MediaPipelineId for the capture pipeline
        """
        prefix = s3_prefix or f"meetings/{meeting_id}"
        try:
            response = self._pipelines_client.create_media_capture_pipeline(
                SourceType="ChimeSdkMeeting",
                SourceArn=f"arn:aws:chime::{self._get_account_id()}:meeting/{meeting_id}",
                SinkType="S3Bucket",
                SinkArn=f"arn:aws:s3:::{self._s3_bucket}",
                ChimeSdkMeetingConfiguration={
                    "ArtifactsConfiguration": {
                        "Audio": {"MuxType": "AudioWithActiveSpeakerVideo"},
                        "Video": {"State": "Enabled", "MuxType": "VideoOnly"},
                        "Content": {"State": "Enabled", "MuxType": "ContentOnly"},
                    },
                },
            )
            pipeline_id = response["MediaCapturePipeline"]["MediaPipelineId"]
            logger.info(
                f"Started recording pipeline {pipeline_id} "
                f"for meeting {meeting_id} → s3://{self._s3_bucket}/{prefix}"
            )
            return pipeline_id
        except ClientError as e:
            logger.error(f"Failed to start recording for meeting {meeting_id}: {e}")
            raise

    def stop_recording(self, pipeline_id: str) -> bool:
        """
        Stop a recording by deleting the media capture pipeline.

        Chime will finalize and concatenate the recording artifacts in S3.

        Args:
            pipeline_id: MediaPipelineId from start_recording()

        Returns:
            True if pipeline was stopped successfully
        """
        try:
            self._pipelines_client.delete_media_pipeline(MediaPipelineId=pipeline_id)
            logger.info(f"Stopped recording pipeline {pipeline_id}")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotFoundException":
                logger.warning(f"Pipeline {pipeline_id} already stopped")
                return True
            logger.error(f"Failed to stop recording pipeline {pipeline_id}: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Transcription
    # ------------------------------------------------------------------ #

    def start_transcription(
        self,
        meeting_id: str,
        language: str = "en-US",
    ) -> bool:
        """
        Start live transcription for a meeting using Amazon Transcribe.

        Args:
            meeting_id: Chime MeetingId
            language: Language code (default en-US)

        Returns:
            True if transcription started successfully
        """
        try:
            self._meetings_client.start_meeting_transcription(
                MeetingId=meeting_id,
                TranscriptionConfiguration={
                    "EngineTranscribeSettings": {
                        "LanguageCode": language,
                        "EnablePartialResultsStabilization": True,
                        "PartialResultsStability": "medium",
                        "ContentIdentificationType": "PII",
                    },
                },
            )
            logger.info(f"Started transcription for meeting {meeting_id}")
            return True
        except ClientError as e:
            logger.error(f"Failed to start transcription for meeting {meeting_id}: {e}")
            return False

    def stop_transcription(self, meeting_id: str) -> bool:
        """
        Stop live transcription for a meeting.

        Args:
            meeting_id: Chime MeetingId

        Returns:
            True if transcription stopped successfully
        """
        try:
            self._meetings_client.stop_meeting_transcription(MeetingId=meeting_id)
            logger.info(f"Stopped transcription for meeting {meeting_id}")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotFoundException":
                logger.warning(f"Transcription for meeting {meeting_id} already stopped")
                return True
            logger.error(f"Failed to stop transcription for meeting {meeting_id}: {e}")
            return False

    # ------------------------------------------------------------------ #
    # S3 helpers
    # ------------------------------------------------------------------ #

    def upload_to_s3(
        self,
        content: bytes,
        s3_key: str,
        content_type: str = "video/webm",
    ) -> str:
        """Upload content to S3 and return the key."""
        try:
            self._s3_client.put_object(
                Bucket=self._s3_bucket,
                Key=s3_key,
                Body=content,
                ContentType=content_type,
            )
            logger.info(f"Uploaded {len(content)} bytes to s3://{self._s3_bucket}/{s3_key}")
            return s3_key
        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise

    def get_presigned_url(
        self,
        s3_key: str,
        expiration: int = 3600,
    ) -> str:
        """Generate a presigned download URL for an S3 object."""
        try:
            url = self._s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._s3_bucket, "Key": s3_key},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {s3_key}: {e}")
            raise

    def delete_from_s3(self, s3_key: str) -> bool:
        """Delete an object from S3."""
        try:
            self._s3_client.delete_object(Bucket=self._s3_bucket, Key=s3_key)
            logger.info(f"Deleted s3://{self._s3_bucket}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete from S3: {e}")
            return False

    def download_from_s3(self, s3_key: str) -> Optional[bytes]:
        """Download an object from S3."""
        try:
            response = self._s3_client.get_object(Bucket=self._s3_bucket, Key=s3_key)
            return response["Body"].read()
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NoSuchKey":
                logger.warning(f"S3 key not found: {s3_key}")
                return None
            logger.error(f"Failed to download from S3: {e}")
            raise

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get_account_id(self) -> str:
        """Get the AWS account ID from STS."""
        try:
            sts = boto3.client("sts", region_name=self._region)
            return sts.get_caller_identity()["Account"]
        except Exception as e:
            logger.error(f"Failed to get AWS account ID: {e}")
            raise


# --------------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------------- #

_chime_service: Optional[ChimeMeetingService] = None


def get_chime_service() -> ChimeMeetingService:
    """Get or create the ChimeMeetingService singleton."""
    global _chime_service
    if _chime_service is None:
        _chime_service = ChimeMeetingService()
    return _chime_service
