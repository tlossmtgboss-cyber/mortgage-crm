import React, { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../services/api';
import { sanitizeText, sanitizeHTML, SafeHTML } from '../../utils/sanitize';
import ScheduleMeetingButton from './ScheduleMeetingButton';
import './ClipPlayer.css';
import { toast } from '../../utils/toast';

const ClipPlayer = ({ clip, onClose, isPublicView = false, shareToken = null }) => {
  // State
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [showTranscript, setShowTranscript] = useState(false);
  const [transcript, setTranscript] = useState(null);
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [showCommentInput, setShowCommentInput] = useState(false);
  const [viewTracked, setViewTracked] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  // Refs
  const videoRef = useRef(null);
  const containerRef = useRef(null);
  const controlsTimeoutRef = useRef(null);
  const progressUpdateRef = useRef(null);

  // Generate session ID for view tracking
  useEffect(() => {
    const id = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setSessionId(id);
  }, []);

  // Load clip data
  useEffect(() => {
    if (clip?.transcript_text) {
      try {
        setTranscript(JSON.parse(clip.transcript_text));
      } catch {
        setTranscript(null);
      }
    }

    // Load comments if not public view
    if (!isPublicView && clip?.id) {
      loadComments();
    }
  }, [clip, isPublicView]);

  // Track view on first play
  const trackView = useCallback(async () => {
    if (viewTracked || !sessionId) return;

    try {
      const endpoint = isPublicView && shareToken
        ? `/api/v1/clips/watch/${shareToken}/view`
        : `/api/v1/clips/${clip.id}/view`;

      await api.post(endpoint, {
        session_id: sessionId,
        user_agent: navigator.userAgent,
        referrer: document.referrer || null
      });

      setViewTracked(true);
    } catch (err) {
      console.error('Error tracking view:', err);
    }
  }, [clip?.id, isPublicView, shareToken, sessionId, viewTracked]);

  // Update view progress periodically
  const updateProgress = useCallback(async () => {
    if (!viewTracked || !sessionId || !videoRef.current) return;

    const video = videoRef.current;
    const progress = video.duration > 0 ? video.currentTime / video.duration : 0;

    try {
      const endpoint = isPublicView && shareToken
        ? `/api/v1/clips/watch/${shareToken}/progress`
        : `/api/v1/clips/${clip.id}/progress`;

      await api.post(endpoint, {
        session_id: sessionId,
        watched_seconds: Math.floor(video.currentTime),
        completion_rate: progress,
        completed: progress >= 0.9
      });
    } catch (err) {
      console.error('Error updating progress:', err);
    }
  }, [clip?.id, isPublicView, shareToken, sessionId, viewTracked]);

  // Set up progress tracking interval
  useEffect(() => {
    if (isPlaying && viewTracked) {
      progressUpdateRef.current = setInterval(updateProgress, 10000); // Every 10 seconds
    }

    return () => {
      if (progressUpdateRef.current) {
        clearInterval(progressUpdateRef.current);
      }
    };
  }, [isPlaying, viewTracked, updateProgress]);

  // Update progress when video ends or pauses
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handlePause = () => {
      updateProgress();
    };

    const handleEnded = () => {
      updateProgress();
    };

    video.addEventListener('pause', handlePause);
    video.addEventListener('ended', handleEnded);

    return () => {
      video.removeEventListener('pause', handlePause);
      video.removeEventListener('ended', handleEnded);
    };
  }, [updateProgress]);

  // Load comments
  const loadComments = async () => {
    try {
      const response = await api.get(`/api/v1/clips/${clip.id}/comments`);
      setComments(response.data.comments || []);
    } catch (err) {
      console.error('Error loading comments:', err);
    }
  };

  // Handle play/pause
  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;

    if (video.paused) {
      video.play();
      trackView();
    } else {
      video.pause();
    }
  };

  // Handle time update
  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (video) {
      setCurrentTime(video.currentTime);
    }
  };

  // Handle loaded metadata
  const handleLoadedMetadata = () => {
    const video = videoRef.current;
    if (video) {
      setDuration(video.duration);
    }
  };

  // Handle seek
  const handleSeek = (e) => {
    const video = videoRef.current;
    if (!video) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const pos = (e.clientX - rect.left) / rect.width;
    video.currentTime = pos * video.duration;
  };

  // Handle volume change
  const handleVolumeChange = (e) => {
    const video = videoRef.current;
    const newVolume = parseFloat(e.target.value);
    if (video) {
      video.volume = newVolume;
      setVolume(newVolume);
      setIsMuted(newVolume === 0);
    }
  };

  // Toggle mute
  const toggleMute = () => {
    const video = videoRef.current;
    if (video) {
      video.muted = !video.muted;
      setIsMuted(video.muted);
    }
  };

  // Handle playback rate change
  const handlePlaybackRateChange = (rate) => {
    const video = videoRef.current;
    if (video) {
      video.playbackRate = rate;
      setPlaybackRate(rate);
    }
  };

  // Toggle fullscreen
  const toggleFullscreen = async () => {
    const container = containerRef.current;
    if (!container) return;

    try {
      if (!document.fullscreenElement) {
        await container.requestFullscreen();
        setIsFullscreen(true);
      } else {
        await document.exitFullscreen();
        setIsFullscreen(false);
      }
    } catch (err) {
      console.error('Fullscreen error:', err);
    }
  };

  // Handle fullscreen change
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // Handle mouse move for controls visibility
  const handleMouseMove = () => {
    setShowControls(true);

    if (controlsTimeoutRef.current) {
      clearTimeout(controlsTimeoutRef.current);
    }

    if (isPlaying) {
      controlsTimeoutRef.current = setTimeout(() => {
        setShowControls(false);
      }, 3000);
    }
  };

  // Handle adding comment
  const handleAddComment = async () => {
    if (!newComment.trim()) return;

    try {
      await api.post(`/api/v1/clips/${clip.id}/comments`, {
        comment_text: newComment,
        timestamp_seconds: Math.floor(currentTime)
      });

      setNewComment('');
      setShowCommentInput(false);
      loadComments();
    } catch (err) {
      console.error('Error adding comment:', err);
      toast.error('Failed to add comment');
    }
  };

  // Format time
  const formatTime = (seconds) => {
    if (!seconds || isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Get current transcript segment
  const getCurrentTranscriptSegment = () => {
    if (!transcript?.segments) return null;
    return transcript.segments.find(
      seg => currentTime >= seg.start && currentTime <= seg.end
    );
  };

  // Seek to transcript segment
  const seekToSegment = (segment) => {
    const video = videoRef.current;
    if (video) {
      video.currentTime = segment.start;
    }
  };

  // Get video source URL
  const getVideoSrc = () => {
    if (isPublicView && shareToken) {
      return `/api/v1/clips/watch/${shareToken}/stream`;
    }
    return clip?.storage_path || '';
  };

  return (
    <div className="clip-player" ref={containerRef}>
      {/* Header */}
      <div className="player-header">
        <div className="header-info">
          <h2>{sanitizeText(clip?.title) || 'Video Clip'}</h2>
          {clip?.description && (
            <SafeHTML className="clip-description" html={clip.description} />
          )}
        </div>
        {onClose && (
          <button className="close-button" onClick={onClose}>×</button>
        )}
      </div>

      {/* Video Container */}
      <div
        className={`video-container ${isFullscreen ? 'fullscreen' : ''}`}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => isPlaying && setShowControls(false)}
      >
        <video
          ref={videoRef}
          className="video-element"
          src={getVideoSrc()}
          onClick={togglePlay}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
          playsInline
        />

        {/* Play Button Overlay */}
        {!isPlaying && (
          <div className="play-overlay" onClick={togglePlay}>
            <div className="play-button-large">
              <span>▶</span>
            </div>
          </div>
        )}

        {/* Schedule Meeting CTA - shows after video ends */}
        {currentTime >= duration - 0.5 && duration > 0 && (
          <div className="end-cta-overlay">
            <div className="end-cta-content">
              <p>Ready to take the next step?</p>
              <ScheduleMeetingButton
                buttonText="Schedule a Call"
                buttonStyle="primary"
                buttonSize="large"
                clipId={clip?.id}
                leadId={clip?.crm_entity_type === 'lead' ? clip?.crm_entity_id : null}
                loanId={clip?.crm_entity_type === 'loan' ? clip?.crm_entity_id : null}
                isPublic={isPublicView}
              />
            </div>
          </div>
        )}

        {/* Controls */}
        <div className={`video-controls ${showControls ? 'visible' : ''}`}>
          {/* Progress Bar */}
          <div className="progress-bar-container" onClick={handleSeek}>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
              />
              <div
                className="progress-handle"
                style={{ left: `${duration ? (currentTime / duration) * 100 : 0}%` }}
              />
            </div>
          </div>

          <div className="controls-row">
            {/* Left Controls */}
            <div className="controls-left">
              <button className="control-btn play-btn" onClick={togglePlay}>
                {isPlaying ? '⏸' : '▶'}
              </button>

              <div className="volume-control">
                <button className="control-btn" onClick={toggleMute}>
                  {isMuted || volume === 0 ? '🔇' : volume < 0.5 ? '🔉' : '🔊'}
                </button>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={isMuted ? 0 : volume}
                  onChange={handleVolumeChange}
                  className="volume-slider"
                />
              </div>

              <div className="time-display">
                {formatTime(currentTime)} / {formatTime(duration)}
              </div>
            </div>

            {/* Right Controls */}
            <div className="controls-right">
              {/* Playback Speed */}
              <div className="speed-control">
                <select
                  value={playbackRate}
                  onChange={(e) => handlePlaybackRateChange(parseFloat(e.target.value))}
                >
                  <option value="0.5">0.5x</option>
                  <option value="0.75">0.75x</option>
                  <option value="1">1x</option>
                  <option value="1.25">1.25x</option>
                  <option value="1.5">1.5x</option>
                  <option value="2">2x</option>
                </select>
              </div>

              {/* Transcript Toggle */}
              {transcript && (
                <button
                  className={`control-btn ${showTranscript ? 'active' : ''}`}
                  onClick={() => setShowTranscript(!showTranscript)}
                  title="Transcript"
                >
                  📝
                </button>
              )}

              {/* Fullscreen */}
              <button
                className="control-btn"
                onClick={toggleFullscreen}
                title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
              >
                {isFullscreen ? '⤓' : '⤢'}
              </button>
            </div>
          </div>
        </div>

        {/* Transcript Overlay */}
        {showTranscript && transcript && (
          <div className="transcript-overlay">
            <div className="current-transcript">
              {sanitizeText(getCurrentTranscriptSegment()?.text) || ''}
            </div>
          </div>
        )}
      </div>

      {/* Info Panel */}
      <div className="player-info">
        <div className="info-tabs">
          <button
            className={`tab ${!showTranscript ? 'active' : ''}`}
            onClick={() => setShowTranscript(false)}
          >
            Details
          </button>
          {transcript && (
            <button
              className={`tab ${showTranscript ? 'active' : ''}`}
              onClick={() => setShowTranscript(true)}
            >
              Transcript
            </button>
          )}
        </div>

        <div className="info-content">
          {/* Details Tab */}
          {!showTranscript && (
            <div className="details-tab">
              <div className="clip-stats">
                <div className="stat">
                  <span className="stat-label">Views</span>
                  <span className="stat-value">{clip?.view_count || 0}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Duration</span>
                  <span className="stat-value">{formatTime(clip?.duration_seconds)}</span>
                </div>
                {clip?.average_completion_rate > 0 && (
                  <div className="stat">
                    <span className="stat-label">Avg. Watched</span>
                    <span className="stat-value">
                      {Math.round(clip.average_completion_rate * 100)}%
                    </span>
                  </div>
                )}
              </div>

              {/* Schedule Meeting CTA */}
              <div className="schedule-cta-section">
                <p className="schedule-cta-text">Have questions? Let's talk!</p>
                <ScheduleMeetingButton
                  buttonText="Schedule a Meeting"
                  buttonStyle="primary"
                  buttonSize="medium"
                  clipId={clip?.id}
                  leadId={clip?.crm_entity_type === 'lead' ? clip?.crm_entity_id : null}
                  loanId={clip?.crm_entity_type === 'loan' ? clip?.crm_entity_id : null}
                  isPublic={isPublicView}
                />
              </div>

              {/* Comments Section */}
              {!isPublicView && (
                <div className="comments-section">
                  <div className="comments-header">
                    <h3>Comments ({comments.length})</h3>
                    <button
                      className="add-comment-btn"
                      onClick={() => setShowCommentInput(!showCommentInput)}
                    >
                      + Add Comment
                    </button>
                  </div>

                  {showCommentInput && (
                    <div className="comment-input">
                      <div className="comment-timestamp">
                        At {formatTime(currentTime)}
                      </div>
                      <textarea
                        value={newComment}
                        onChange={(e) => setNewComment(e.target.value)}
                        placeholder="Add a comment..."
                        rows={2}
                      />
                      <div className="comment-actions">
                        <button
                          className="cancel-btn"
                          onClick={() => {
                            setShowCommentInput(false);
                            setNewComment('');
                          }}
                        >
                          Cancel
                        </button>
                        <button
                          className="submit-btn"
                          onClick={handleAddComment}
                          disabled={!newComment.trim()}
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="comments-list">
                    {comments.length === 0 ? (
                      <p className="no-comments">No comments yet</p>
                    ) : (
                      comments.map((comment) => (
                        <div key={comment.id} className="comment-item">
                          <div className="comment-meta">
                            <span className="comment-author">
                              {sanitizeText(comment.user_name) || 'User'}
                            </span>
                            {comment.timestamp_seconds > 0 && (
                              <button
                                className="comment-timestamp-link"
                                onClick={() => {
                                  const video = videoRef.current;
                                  if (video) {
                                    video.currentTime = comment.timestamp_seconds;
                                  }
                                }}
                              >
                                {formatTime(comment.timestamp_seconds)}
                              </button>
                            )}
                          </div>
                          <p className="comment-text">{sanitizeText(comment.comment_text)}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Transcript Tab */}
          {showTranscript && transcript && (
            <div className="transcript-tab">
              <div className="transcript-segments">
                {transcript.segments?.map((segment, index) => (
                  <div
                    key={index}
                    className={`transcript-segment ${
                      currentTime >= segment.start && currentTime <= segment.end
                        ? 'active'
                        : ''
                    }`}
                    onClick={() => seekToSegment(segment)}
                  >
                    <span className="segment-time">
                      {formatTime(segment.start)}
                    </span>
                    <span className="segment-text">{sanitizeText(segment.text)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ClipPlayer;
