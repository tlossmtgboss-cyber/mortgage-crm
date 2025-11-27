import React, { useState, useRef, useEffect, useCallback } from 'react';
import { sanitizeText, SafeHTML } from '../../utils/sanitize';
import './RecordingPlayer.css';

const RecordingPlayer = ({ recording, onClose }) => {
  const audioRef = useRef(null);
  const transcriptRef = useRef(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [activeTab, setActiveTab] = useState('transcript');
  const [activeSegmentIndex, setActiveSegmentIndex] = useState(-1);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);

  // Extract data from recording
  const transcript = recording?.transcript || {};
  const analysis = recording?.analysis || {};
  const segments = transcript.segments || [];

  // Format time as MM:SS
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Handle time update - sync transcript
  const handleTimeUpdate = useCallback(() => {
    if (!audioRef.current) return;

    const time = audioRef.current.currentTime;
    setCurrentTime(time);

    // Find active segment
    const activeIdx = segments.findIndex(
      (seg, idx) => {
        const nextSeg = segments[idx + 1];
        const segEnd = nextSeg ? nextSeg.start : seg.end || duration;
        return time >= seg.start && time < segEnd;
      }
    );

    if (activeIdx !== activeSegmentIndex) {
      setActiveSegmentIndex(activeIdx);

      // Auto-scroll transcript
      if (activeIdx >= 0 && transcriptRef.current) {
        const activeElement = transcriptRef.current.querySelector(
          `[data-segment-index="${activeIdx}"]`
        );
        if (activeElement) {
          activeElement.scrollIntoView({
            behavior: 'smooth',
            block: 'center'
          });
        }
      }
    }
  }, [segments, activeSegmentIndex, duration]);

  // Handle segment click - seek to time
  const handleSegmentClick = (segment) => {
    if (audioRef.current && segment.start !== undefined) {
      audioRef.current.currentTime = segment.start;
      if (!isPlaying) {
        audioRef.current.play();
        setIsPlaying(true);
      }
    }
  };

  // Toggle play/pause
  const togglePlayback = () => {
    if (!audioRef.current) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  // Handle seek
  const handleSeek = (e) => {
    const seekTime = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = seekTime;
      setCurrentTime(seekTime);
    }
  };

  // Skip forward/back
  const skip = (seconds) => {
    if (audioRef.current) {
      audioRef.current.currentTime = Math.max(
        0,
        Math.min(duration, audioRef.current.currentTime + seconds)
      );
    }
  };

  // Change playback rate
  const changePlaybackRate = () => {
    const rates = [0.5, 0.75, 1, 1.25, 1.5, 2];
    const currentIdx = rates.indexOf(playbackRate);
    const nextIdx = (currentIdx + 1) % rates.length;
    const newRate = rates[nextIdx];

    setPlaybackRate(newRate);
    if (audioRef.current) {
      audioRef.current.playbackRate = newRate;
    }
  };

  // Handle volume change
  const handleVolumeChange = (e) => {
    const newVolume = parseFloat(e.target.value);
    setVolume(newVolume);
    if (audioRef.current) {
      audioRef.current.volume = newVolume;
    }
  };

  // Setup audio event listeners
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleLoadedMetadata = () => {
      setDuration(audio.duration);
    };

    const handleEnded = () => {
      setIsPlaying(false);
    };

    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('ended', handleEnded);

    return () => {
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('ended', handleEnded);
    };
  }, [handleTimeUpdate]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.target.tagName === 'INPUT') return;

      switch (e.key) {
        case ' ':
          e.preventDefault();
          togglePlayback();
          break;
        case 'ArrowLeft':
          skip(-10);
          break;
        case 'ArrowRight':
          skip(10);
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [isPlaying]);

  // Get priority class for action items
  const getPriorityClass = (priority) => {
    switch (priority?.toLowerCase()) {
      case 'high': return 'priority-high';
      case 'medium': return 'priority-medium';
      case 'low': return 'priority-low';
      default: return '';
    }
  };

  // Get sentiment indicator
  const getSentimentIndicator = (sentiment) => {
    switch (sentiment?.toLowerCase()) {
      case 'positive': return { icon: '😊', class: 'sentiment-positive' };
      case 'negative': return { icon: '😟', class: 'sentiment-negative' };
      case 'concerned': return { icon: '😐', class: 'sentiment-concerned' };
      default: return { icon: '😐', class: 'sentiment-neutral' };
    }
  };

  return (
    <div className="recording-player-overlay">
      <div className="recording-player-container">
        {/* Header */}
        <div className="recording-player-header">
          <div className="recording-info">
            <h2>{sanitizeText(recording?.meeting_title) || 'Meeting Recording'}</h2>
            <span className="recording-date">
              {recording?.created_at
                ? new Date(recording.created_at).toLocaleDateString('en-US', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                  })
                : 'Recording'
              }
            </span>
          </div>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        {/* Audio Player */}
        <div className="audio-player">
          <audio
            ref={audioRef}
            src={recording?.recording_url}
            preload="metadata"
          />

          <div className="player-controls">
            <button className="skip-btn" onClick={() => skip(-10)}>
              <span>-10s</span>
            </button>

            <button className="play-btn" onClick={togglePlayback}>
              {isPlaying ? '⏸' : '▶'}
            </button>

            <button className="skip-btn" onClick={() => skip(10)}>
              <span>+10s</span>
            </button>
          </div>

          <div className="timeline-container">
            <span className="time-display">{formatTime(currentTime)}</span>
            <input
              type="range"
              className="timeline-slider"
              min="0"
              max={duration || 0}
              value={currentTime}
              onChange={handleSeek}
            />
            <span className="time-display">{formatTime(duration)}</span>
          </div>

          <div className="player-options">
            <button
              className="speed-btn"
              onClick={changePlaybackRate}
              title="Change playback speed"
            >
              {playbackRate}x
            </button>

            <div className="volume-control">
              <span className="volume-icon">🔊</span>
              <input
                type="range"
                className="volume-slider"
                min="0"
                max="1"
                step="0.1"
                value={volume}
                onChange={handleVolumeChange}
              />
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="recording-tabs">
          <button
            className={`tab-btn ${activeTab === 'transcript' ? 'active' : ''}`}
            onClick={() => setActiveTab('transcript')}
          >
            Transcript
          </button>
          <button
            className={`tab-btn ${activeTab === 'summary' ? 'active' : ''}`}
            onClick={() => setActiveTab('summary')}
          >
            Summary
          </button>
          <button
            className={`tab-btn ${activeTab === 'actions' ? 'active' : ''}`}
            onClick={() => setActiveTab('actions')}
          >
            Action Items
            {analysis.action_items?.length > 0 && (
              <span className="tab-badge">{analysis.action_items.length}</span>
            )}
          </button>
          <button
            className={`tab-btn ${activeTab === 'insights' ? 'active' : ''}`}
            onClick={() => setActiveTab('insights')}
          >
            Mortgage Insights
          </button>
        </div>

        {/* Tab Content */}
        <div className="tab-content">
          {/* Transcript Tab */}
          {activeTab === 'transcript' && (
            <div className="transcript-container" ref={transcriptRef}>
              {segments.length > 0 ? (
                segments.map((segment, index) => (
                  <div
                    key={index}
                    data-segment-index={index}
                    className={`transcript-segment ${index === activeSegmentIndex ? 'active' : ''}`}
                    onClick={() => handleSegmentClick(segment)}
                  >
                    <span className="segment-time">
                      {formatTime(segment.start || 0)}
                    </span>
                    <span className="segment-speaker">
                      {sanitizeText(segment.speaker) || 'Speaker'}:
                    </span>
                    <span className="segment-text">{sanitizeText(segment.text)}</span>
                  </div>
                ))
              ) : transcript.transcript ? (
                <div className="transcript-full">
                  <SafeHTML html={transcript.transcript} />
                </div>
              ) : (
                <div className="transcript-empty">
                  <p>Transcript not available</p>
                  <span>Processing may still be in progress</span>
                </div>
              )}
            </div>
          )}

          {/* Summary Tab */}
          {activeTab === 'summary' && (
            <div className="summary-container">
              {analysis.summary ? (
                <>
                  <div className="summary-section">
                    <h3>Executive Summary</h3>
                    <SafeHTML html={analysis.summary} />
                  </div>

                  {analysis.sentiment && (
                    <div className="summary-section sentiment-section">
                      <h3>Sentiment Analysis</h3>
                      <div className="sentiment-grid">
                        <div className="sentiment-item">
                          <span className="sentiment-label">Overall</span>
                          <span className={`sentiment-value ${getSentimentIndicator(analysis.sentiment.overall).class}`}>
                            {getSentimentIndicator(analysis.sentiment.overall).icon} {analysis.sentiment.overall}
                          </span>
                        </div>
                        {analysis.sentiment.borrower_sentiment && (
                          <div className="sentiment-item">
                            <span className="sentiment-label">Borrower</span>
                            <span className={`sentiment-value ${getSentimentIndicator(analysis.sentiment.borrower_sentiment).class}`}>
                              {getSentimentIndicator(analysis.sentiment.borrower_sentiment).icon} {analysis.sentiment.borrower_sentiment}
                            </span>
                          </div>
                        )}
                      </div>
                      {analysis.sentiment.notes && (
                        <p className="sentiment-notes">{analysis.sentiment.notes}</p>
                      )}
                    </div>
                  )}

                  {analysis.key_topics?.length > 0 && (
                    <div className="summary-section">
                      <h3>Key Topics</h3>
                      <ul className="topics-list">
                        {analysis.key_topics.map((topic, idx) => (
                          <li key={idx} className="topic-item">
                            <strong>{topic.topic}</strong>
                            <p>{topic.summary}</p>
                            {topic.timestamp_hint && (
                              <span className="timestamp-hint">{topic.timestamp_hint}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {analysis.decisions_made?.length > 0 && (
                    <div className="summary-section">
                      <h3>Decisions Made</h3>
                      <ul className="decisions-list">
                        {analysis.decisions_made.map((decision, idx) => (
                          <li key={idx} className="decision-item">
                            <strong>{decision.decision}</strong>
                            {decision.context && <p>{decision.context}</p>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {analysis.questions_discussed?.length > 0 && (
                    <div className="summary-section">
                      <h3>Questions Discussed</h3>
                      <ul className="questions-list">
                        {analysis.questions_discussed.map((q, idx) => (
                          <li key={idx} className="question-item">
                            <div className="question-text">
                              <strong>Q:</strong> {q.question}
                            </div>
                            {q.answer && (
                              <div className="answer-text">
                                <strong>A:</strong> {q.answer}
                              </div>
                            )}
                            <span className={`resolved-badge ${q.resolved ? 'resolved' : 'unresolved'}`}>
                              {q.resolved ? '✓ Resolved' : '○ Open'}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <div className="summary-empty">
                  <p>Summary not available</p>
                  <span>AI analysis may still be processing</span>
                </div>
              )}
            </div>
          )}

          {/* Action Items Tab */}
          {activeTab === 'actions' && (
            <div className="actions-container">
              {analysis.action_items?.length > 0 ? (
                <ul className="action-items-list">
                  {analysis.action_items.map((item, idx) => (
                    <li key={idx} className={`action-item ${getPriorityClass(item.priority)}`}>
                      <div className="action-header">
                        <span className={`priority-badge ${getPriorityClass(item.priority)}`}>
                          {item.priority || 'Medium'}
                        </span>
                        {item.category && (
                          <span className="category-badge">{item.category}</span>
                        )}
                      </div>
                      <p className="action-description">{item.description}</p>
                      <div className="action-meta">
                        {item.assignee && item.assignee !== 'Unassigned' && (
                          <span className="assignee">Assigned: {item.assignee}</span>
                        )}
                        {item.due_hint && (
                          <span className="due-hint">Due: {item.due_hint}</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="actions-empty">
                  <p>No action items identified</p>
                  <span>The AI analysis didn't find specific action items in this meeting</span>
                </div>
              )}

              {analysis.follow_up_recommendations?.length > 0 && (
                <div className="follow-up-section">
                  <h3>Recommended Follow-ups</h3>
                  <ul className="follow-up-list">
                    {analysis.follow_up_recommendations.map((rec, idx) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Mortgage Insights Tab */}
          {activeTab === 'insights' && (
            <div className="insights-container">
              {analysis.mortgage_insights ? (
                <>
                  <div className="insights-grid">
                    {analysis.mortgage_insights.loan_type_mentioned && (
                      <div className="insight-card">
                        <span className="insight-label">Loan Type</span>
                        <span className="insight-value">{analysis.mortgage_insights.loan_type_mentioned}</span>
                      </div>
                    )}
                    {analysis.mortgage_insights.loan_amount_mentioned && (
                      <div className="insight-card">
                        <span className="insight-label">Loan Amount</span>
                        <span className="insight-value">{analysis.mortgage_insights.loan_amount_mentioned}</span>
                      </div>
                    )}
                    {analysis.mortgage_insights.rate_mentioned && (
                      <div className="insight-card">
                        <span className="insight-label">Rate Discussed</span>
                        <span className="insight-value">{analysis.mortgage_insights.rate_mentioned}</span>
                      </div>
                    )}
                    {analysis.mortgage_insights.property_type && (
                      <div className="insight-card">
                        <span className="insight-label">Property Type</span>
                        <span className="insight-value">{analysis.mortgage_insights.property_type}</span>
                      </div>
                    )}
                    {analysis.mortgage_insights.purchase_vs_refi && (
                      <div className="insight-card">
                        <span className="insight-label">Transaction Type</span>
                        <span className="insight-value">{analysis.mortgage_insights.purchase_vs_refi}</span>
                      </div>
                    )}
                    {analysis.mortgage_insights.current_stage && (
                      <div className="insight-card">
                        <span className="insight-label">Current Stage</span>
                        <span className="insight-value">{analysis.mortgage_insights.current_stage}</span>
                      </div>
                    )}
                    {analysis.mortgage_insights.timeline_mentioned && (
                      <div className="insight-card">
                        <span className="insight-label">Timeline</span>
                        <span className="insight-value">{analysis.mortgage_insights.timeline_mentioned}</span>
                      </div>
                    )}
                  </div>

                  {analysis.mortgage_insights.next_milestone && (
                    <div className="next-milestone-section">
                      <h3>Next Milestone</h3>
                      <p>{analysis.mortgage_insights.next_milestone}</p>
                    </div>
                  )}

                  {analysis.mortgage_insights.potential_issues?.length > 0 && (
                    <div className="issues-section">
                      <h3>Potential Issues</h3>
                      <ul className="issues-list">
                        {analysis.mortgage_insights.potential_issues.map((issue, idx) => (
                          <li key={idx} className="issue-item">
                            <span className="issue-icon">⚠️</span>
                            {issue}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {analysis.mortgage_insights.competitor_mentions?.length > 0 && (
                    <div className="competitors-section">
                      <h3>Competitor Mentions</h3>
                      <ul className="competitors-list">
                        {analysis.mortgage_insights.competitor_mentions.map((comp, idx) => (
                          <li key={idx}>{comp}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {analysis.compliance_notes?.length > 0 && (
                    <div className="compliance-section">
                      <h3>Compliance Notes</h3>
                      <ul className="compliance-list">
                        {analysis.compliance_notes.map((note, idx) => (
                          <li key={idx} className="compliance-item">
                            <span className="compliance-icon">📋</span>
                            {note}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <div className="insights-empty">
                  <p>Mortgage insights not available</p>
                  <span>No mortgage-specific information was detected in this meeting</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer with metadata */}
        <div className="recording-player-footer">
          <span className="recording-duration">
            Duration: {formatTime(duration || transcript.duration || 0)}
          </span>
          {transcript.language && (
            <span className="recording-language">
              Language: {transcript.language.toUpperCase()}
            </span>
          )}
          {analysis.engagement_metrics?.collaboration_score !== undefined && (
            <span className="collaboration-score">
              Collaboration: {Math.round(analysis.engagement_metrics.collaboration_score * 100)}%
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default RecordingPlayer;
