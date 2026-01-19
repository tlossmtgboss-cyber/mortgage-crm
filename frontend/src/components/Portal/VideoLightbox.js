/**
 * VideoLightbox Component
 *
 * Full-screen lightbox that auto-opens when user has unwatched video messages.
 * Video is deleted from the system after being watched to completion.
 */

import React, { useState, useEffect, useCallback } from 'react';
import './VideoLightbox.css';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const VideoLightbox = ({
  portalType = 'client',
  identifier,
  onClose,
  onVideoWatched
}) => {
  const [video, setVideo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);

  // Fetch the first unwatched video
  const fetchUnwatchedVideo = useCallback(async () => {
    if (!identifier) return;

    try {
      setLoading(true);
      let url;

      if (portalType === 'client') {
        url = `${API_URL}/api/v1/portal-video/client/${identifier}/videos`;
      } else {
        url = `${API_URL}/api/v1/portal-video/realtor/${identifier}/videos`;
      }

      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        // Get the first unwatched video
        const unwatchedVideo = (data.videos || []).find(v => v.is_new);
        setVideo(unwatchedVideo || null);
      }
    } catch (err) {
      console.error('Error fetching video:', err);
    } finally {
      setLoading(false);
    }
  }, [portalType, identifier]);

  useEffect(() => {
    fetchUnwatchedVideo();
  }, [fetchUnwatchedVideo]);

  // Mark video as viewed (which also deletes it)
  const markVideoViewed = async (videoId) => {
    try {
      const endpoint = portalType === 'client'
        ? `${API_URL}/api/v1/portal-video/client/mark-viewed/${videoId}`
        : `${API_URL}/api/v1/portal-video/realtor/mark-viewed/${videoId}`;

      await fetch(endpoint, { method: 'POST' });

      if (onVideoWatched) {
        onVideoWatched(videoId);
      }
    } catch (err) {
      console.error('Error marking video viewed:', err);
    }
  };

  const handleVideoEnded = () => {
    if (video) {
      markVideoViewed(video.id);
    }
    setIsPlaying(false);
    onClose();
  };

  const handleClose = () => {
    // If video hasn't been watched yet, just close without deleting
    onClose();
  };

  // Don't render if no unwatched video
  if (loading) {
    return null;
  }

  if (!video) {
    return null;
  }

  return (
    <div className="video-lightbox-overlay">
      <div className="video-lightbox-container">
        <button className="lightbox-close-btn" onClick={handleClose}>
          ×
        </button>

        <div className="lightbox-header">
          <div className="lightbox-sender-info">
            <div className="sender-avatar">
              {video.sender_photo ? (
                <img src={video.sender_photo} alt={video.sender_name} />
              ) : (
                <span>{video.sender_name?.charAt(0) || 'L'}</span>
              )}
            </div>
            <div className="sender-details">
              <span className="sender-name">{video.sender_name || 'Your Loan Officer'}</span>
              <span className="video-date">
                {new Date(video.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
          <span className="new-video-badge">New Message</span>
        </div>

        <div className="lightbox-video-wrapper">
          <video
            controls
            autoPlay={isPlaying}
            onPlay={() => setIsPlaying(true)}
            onEnded={handleVideoEnded}
            poster={video.sender_photo || undefined}
          >
            <source src={video.video_url} type="video/webm" />
            <source src={video.video_url} type="video/mp4" />
            Your browser does not support video playback.
          </video>

          {!isPlaying && (
            <div className="play-overlay" onClick={() => setIsPlaying(true)}>
              <button className="play-button">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </button>
              <span className="play-text">Click to play message</span>
            </div>
          )}
        </div>

        {video.message && (
          <div className="lightbox-message">
            <p>{video.message}</p>
          </div>
        )}

        {video.duration_seconds && (
          <div className="lightbox-duration">
            Duration: {Math.floor(video.duration_seconds / 60)}:{(video.duration_seconds % 60).toString().padStart(2, '0')}
          </div>
        )}
      </div>
    </div>
  );
};

export default VideoLightbox;
