/**
 * PortalVideoMessages Component
 *
 * Displays video messages from loan officers to portal users.
 * Used in both Client Portal (ActiveLoanPortal) and Realtor Portal.
 */

import React, { useState, useEffect, useCallback } from 'react';
import './PortalVideoMessages.css';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const PortalVideoMessages = ({
  portalType = 'client',  // 'client' or 'realtor'
  identifier,             // slug for client, partner_id for realtor
  token = null,           // optional auth token
  title = 'Messages from Your Team',
  onNewVideos = null      // callback when new videos are detected
}) => {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [playingVideoId, setPlayingVideoId] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const fetchVideos = useCallback(async () => {
    if (!identifier) return;

    try {
      setLoading(true);
      let url;

      if (portalType === 'client') {
        url = `${API_URL}/api/v1/portal-video/client/${identifier}/videos`;
      } else {
        url = `${API_URL}/api/v1/portal-video/realtor/${identifier}/videos`;
      }

      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, { headers });
      if (response.ok) {
        const data = await response.json();
        setVideos(data.videos || []);

        // Notify parent if there are new unwatched videos
        const newCount = (data.videos || []).filter(v => v.is_new).length;
        if (onNewVideos && newCount > 0) {
          onNewVideos(newCount);
        }
      }
    } catch (err) {
      console.error('Error fetching videos:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [portalType, identifier, token, onNewVideos]);

  const markVideoViewed = async (videoId) => {
    try {
      const endpoint = portalType === 'client'
        ? `${API_URL}/api/v1/portal-video/client/mark-viewed/${videoId}`
        : `${API_URL}/api/v1/portal-video/realtor/mark-viewed/${videoId}`;

      await fetch(endpoint, { method: 'POST' });

      // Remove video from local state (it's been deleted from the system)
      setVideos(prev => prev.filter(v => v.id !== videoId));
      setPlayingVideoId(null);
    } catch (err) {
      console.error('Error marking video viewed:', err);
    }
  };

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  // Don't render if no videos
  if (!loading && videos.length === 0) {
    return null;
  }

  // Determine which videos to show
  const displayVideos = expanded ? videos : videos.slice(0, 3);
  const hasMore = videos.length > 3;
  const newCount = videos.filter(v => v.is_new).length;

  return (
    <div className="portal-video-messages">
      <div className="video-messages-header">
        <h3>
          <span className="header-icon">🎬</span>
          {title}
          {newCount > 0 && (
            <span className="new-badge">{newCount} NEW</span>
          )}
        </h3>
      </div>

      {loading ? (
        <div className="video-messages-loading">
          <div className="loading-spinner"></div>
          <p>Loading messages...</p>
        </div>
      ) : error ? (
        <div className="video-messages-error">
          <p>Unable to load video messages</p>
        </div>
      ) : (
        <>
          <div className="video-messages-grid">
            {displayVideos.map((video) => (
              <div
                key={video.id}
                className={`video-card ${video.is_new ? 'new' : ''} ${playingVideoId === video.id ? 'playing' : ''}`}
              >
                {video.is_new && <span className="video-new-badge">NEW</span>}
                <div className="video-wrapper">
                  <video
                    controls
                    poster={video.sender_photo || undefined}
                    onPlay={() => setPlayingVideoId(video.id)}
                    onEnded={() => markVideoViewed(video.id)}
                  >
                    <source src={video.video_url} type="video/webm" />
                    <source src={video.video_url} type="video/mp4" />
                    Your browser does not support video playback.
                  </video>
                </div>
                <div className="video-info">
                  <div className="video-sender">
                    <div className="sender-avatar">
                      {video.sender_photo ? (
                        <img src={video.sender_photo} alt={video.sender_name} />
                      ) : (
                        <span>{video.sender_name?.charAt(0) || 'L'}</span>
                      )}
                    </div>
                    <div className="sender-details">
                      <span className="sender-name">{video.sender_name}</span>
                      <span className="video-date">
                        {new Date(video.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  {video.message && (
                    <p className="video-message">{video.message}</p>
                  )}
                  {video.duration_seconds && (
                    <span className="video-duration">
                      {Math.floor(video.duration_seconds / 60)}:{(video.duration_seconds % 60).toString().padStart(2, '0')}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {hasMore && (
            <button
              className="show-more-btn"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? 'Show Less' : `Show All ${videos.length} Videos`}
            </button>
          )}
        </>
      )}
    </div>
  );
};

export default PortalVideoMessages;
