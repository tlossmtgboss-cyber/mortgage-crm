/**
 * Call Recording Player Component
 *
 * Play and analyze recorded Voice OS calls.
 * Features:
 * - Audio playback with timeline scrubbing
 * - Synchronized transcript display
 * - Tool usage highlighting
 * - Call quality metrics
 * - Feedback and annotation tools
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './CallRecordingPlayer.css';

const formatTime = (seconds) => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const TranscriptEntry = ({ entry, isActive, onSeek }) => {
  return (
    <div
      className={`transcript-line ${entry.speaker} ${isActive ? 'active' : ''}`}
      onClick={() => onSeek(entry.startTime)}
    >
      <span className="line-time">{formatTime(entry.startTime)}</span>
      <span className="line-speaker">
        {entry.speaker === 'caller' ? 'Caller' : 'AI Agent'}
      </span>
      <span className="line-text">{entry.text}</span>
      {entry.tool && (
        <span className="line-tool">
          Tool: {entry.tool}
          {entry.toolSuccess !== undefined && (
            <span className={entry.toolSuccess ? 'success' : 'failed'}>
              {entry.toolSuccess ? 'OK' : 'Failed'}
            </span>
          )}
        </span>
      )}
    </div>
  );
};

const CallRecordingPlayer = ({ callId, onClose }) => {
  const [call, setCall] = useState(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [activeTab, setActiveTab] = useState('transcript');
  const [feedback, setFeedback] = useState({ rating: 0, notes: '' });

  const audioRef = useRef(null);
  const transcriptRef = useRef(null);

  const fetchCall = useCallback(async () => {
    if (!callId) return;

    setLoading(true);
    try {
      const response = await fetch(`/api/voice/calls/${callId}/recording`);
      if (response.ok) {
        const data = await response.json();
        setCall(data);
      } else {
        // Mock data for development
        setCall({
          id: callId,
          phoneNumber: '+1 (555) 123-4567',
          callerName: 'John Smith',
          agentName: 'Main Receptionist',
          direction: 'inbound',
          startTime: new Date().toISOString(),
          duration: 187,
          outcome: 'appointment_scheduled',
          recordingUrl: '/api/voice/recordings/sample.mp3',
          transcript: [
            { startTime: 0, speaker: 'agent', text: 'Thank you for calling ABC Mortgage. How can I help you today?' },
            { startTime: 4, speaker: 'caller', text: 'Hi, I wanted to check on the status of my loan application.' },
            { startTime: 8, speaker: 'agent', text: 'I\'d be happy to help with that. May I have your name and the property address?' },
            { startTime: 14, speaker: 'caller', text: 'Sure, it\'s John Smith, and the property is at 123 Main Street.' },
            { startTime: 19, speaker: 'agent', text: 'Thank you, Mr. Smith. Let me look that up for you.', tool: 'lookup_caller', toolSuccess: true },
            { startTime: 24, speaker: 'agent', text: 'I found your file. Your loan is currently in underwriting. The underwriter is reviewing your documentation.' },
            { startTime: 32, speaker: 'caller', text: 'Great, do you know when I might hear back?' },
            { startTime: 35, speaker: 'agent', text: 'Typically underwriting takes 3-5 business days. You should hear back by Friday.' },
            { startTime: 42, speaker: 'caller', text: 'Perfect, thank you so much for your help!' },
            { startTime: 45, speaker: 'agent', text: 'You\'re welcome! Is there anything else I can help you with today?' },
            { startTime: 49, speaker: 'caller', text: 'No, that\'s all. Have a great day!' },
            { startTime: 52, speaker: 'agent', text: 'You too! Goodbye.', tool: 'log_call_note', toolSuccess: true },
          ],
          metrics: {
            sttAccuracy: 0.96,
            llmLatencyMs: 342,
            ttsLatencyMs: 156,
            totalLatencyMs: 498,
            toolsUsed: ['lookup_caller', 'get_loan_status', 'log_call_note'],
            toolSuccessRate: 1.0,
          },
        });
      }
    } catch (err) {
      console.error('Failed to fetch call:', err);
    } finally {
      setLoading(false);
    }
  }, [callId]);

  useEffect(() => {
    fetchCall();
  }, [fetchCall]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleTimeUpdate = () => {
      setCurrentTime(audio.currentTime);
    };

    const handleLoadedMetadata = () => {
      setDuration(audio.duration);
    };

    const handleEnded = () => {
      setPlaying(false);
    };

    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('ended', handleEnded);

    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('ended', handleEnded);
    };
  }, []);

  useEffect(() => {
    // Auto-scroll transcript to current position
    if (!transcriptRef.current || !call?.transcript) return;

    const activeEntry = call.transcript.find((entry, index) => {
      const nextEntry = call.transcript[index + 1];
      return currentTime >= entry.startTime && (!nextEntry || currentTime < nextEntry.startTime);
    });

    if (activeEntry) {
      const activeElement = transcriptRef.current.querySelector('.transcript-line.active');
      if (activeElement) {
        activeElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [currentTime, call?.transcript]);

  const togglePlay = () => {
    if (!audioRef.current) return;

    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setPlaying(!playing);
  };

  const handleSeek = (time) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = time;
    setCurrentTime(time);
  };

  const handleTimelineClick = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    const time = percent * duration;
    handleSeek(time);
  };

  const handleRateChange = (rate) => {
    if (!audioRef.current) return;
    audioRef.current.playbackRate = rate;
    setPlaybackRate(rate);
  };

  const handleVolumeChange = (vol) => {
    if (!audioRef.current) return;
    audioRef.current.volume = vol;
    setVolume(vol);
  };

  const submitFeedback = async () => {
    try {
      await fetch(`/api/voice/calls/${callId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(feedback),
      });
      alert('Feedback submitted successfully');
    } catch (err) {
      console.error('Failed to submit feedback:', err);
    }
  };

  if (loading || !call) {
    return (
      <div className="call-player loading">
        <div className="loading-spinner">Loading recording...</div>
      </div>
    );
  }

  const activeTranscriptIndex = call.transcript.findIndex((entry, index) => {
    const nextEntry = call.transcript[index + 1];
    return currentTime >= entry.startTime && (!nextEntry || currentTime < nextEntry.startTime);
  });

  return (
    <div className="call-player">
      {/* Header */}
      <div className="player-header">
        <div className="call-info">
          <h2>{call.callerName || call.phoneNumber}</h2>
          <div className="call-meta">
            <span className="meta-item">{call.direction === 'inbound' ? 'Inbound' : 'Outbound'}</span>
            <span className="meta-item">{new Date(call.startTime).toLocaleString()}</span>
            <span className="meta-item">{formatTime(call.duration)}</span>
            <span className={`outcome-badge ${call.outcome}`}>{call.outcome.replace(/_/g, ' ')}</span>
          </div>
        </div>

        {onClose && (
          <button className="close-btn" onClick={onClose}>
            X
          </button>
        )}
      </div>

      {/* Audio Player */}
      <div className="audio-player">
        <audio ref={audioRef} src={call.recordingUrl} preload="metadata" />

        <div className="player-controls">
          <button className="play-btn" onClick={togglePlay}>
            {playing ? '||' : '>'}
          </button>

          <span className="time-display">
            {formatTime(currentTime)} / {formatTime(duration || call.duration)}
          </span>

          <div className="timeline" onClick={handleTimelineClick}>
            <div
              className="timeline-progress"
              style={{ width: `${(currentTime / (duration || call.duration)) * 100}%` }}
            />
            <div
              className="timeline-handle"
              style={{ left: `${(currentTime / (duration || call.duration)) * 100}%` }}
            />
            {/* Tool markers */}
            {call.transcript
              .filter(e => e.tool)
              .map((entry, index) => (
                <div
                  key={index}
                  className="tool-marker"
                  style={{ left: `${(entry.startTime / (duration || call.duration)) * 100}%` }}
                  title={entry.tool}
                />
              ))}
          </div>

          <div className="playback-rate">
            {[0.5, 1, 1.5, 2].map(rate => (
              <button
                key={rate}
                className={playbackRate === rate ? 'active' : ''}
                onClick={() => handleRateChange(rate)}
              >
                {rate}x
              </button>
            ))}
          </div>

          <div className="volume-control">
            <span className="volume-icon">{volume > 0 ? 'vol' : 'mute'}</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={volume}
              onChange={e => handleVolumeChange(parseFloat(e.target.value))}
            />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="player-tabs">
        <button
          className={activeTab === 'transcript' ? 'active' : ''}
          onClick={() => setActiveTab('transcript')}
        >
          Transcript
        </button>
        <button
          className={activeTab === 'metrics' ? 'active' : ''}
          onClick={() => setActiveTab('metrics')}
        >
          Metrics
        </button>
        <button
          className={activeTab === 'feedback' ? 'active' : ''}
          onClick={() => setActiveTab('feedback')}
        >
          Feedback
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'transcript' && (
          <div className="transcript-tab" ref={transcriptRef}>
            {call.transcript.map((entry, index) => (
              <TranscriptEntry
                key={index}
                entry={entry}
                isActive={index === activeTranscriptIndex}
                onSeek={handleSeek}
              />
            ))}
          </div>
        )}

        {activeTab === 'metrics' && (
          <div className="metrics-tab">
            <div className="metrics-grid">
              <div className="metric-item">
                <span className="metric-label">STT Accuracy</span>
                <span className="metric-value">{(call.metrics.sttAccuracy * 100).toFixed(1)}%</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">LLM Latency</span>
                <span className="metric-value">{call.metrics.llmLatencyMs}ms</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">TTS Latency</span>
                <span className="metric-value">{call.metrics.ttsLatencyMs}ms</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">Total Latency</span>
                <span className="metric-value">{call.metrics.totalLatencyMs}ms</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">Tool Success Rate</span>
                <span className="metric-value">{(call.metrics.toolSuccessRate * 100).toFixed(0)}%</span>
              </div>
            </div>

            <div className="tools-used">
              <h4>Tools Used</h4>
              <div className="tool-list">
                {call.metrics.toolsUsed.map((tool, index) => (
                  <span key={index} className="tool-badge">
                    {tool.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'feedback' && (
          <div className="feedback-tab">
            <div className="rating-section">
              <label>Call Quality Rating</label>
              <div className="star-rating">
                {[1, 2, 3, 4, 5].map(star => (
                  <button
                    key={star}
                    className={feedback.rating >= star ? 'filled' : ''}
                    onClick={() => setFeedback({ ...feedback, rating: star })}
                  >
                    *
                  </button>
                ))}
              </div>
            </div>

            <div className="notes-section">
              <label>Notes / Comments</label>
              <textarea
                value={feedback.notes}
                onChange={e => setFeedback({ ...feedback, notes: e.target.value })}
                placeholder="Add any observations about this call..."
                rows={4}
              />
            </div>

            <div className="quick-tags">
              <label>Quick Tags</label>
              <div className="tag-buttons">
                {['Good conversation', 'Needs training', 'Tool issue', 'Customer happy', 'Escalation needed'].map(tag => (
                  <button
                    key={tag}
                    onClick={() => setFeedback({ ...feedback, notes: `${feedback.notes}\n[${tag}]`.trim() })}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            <button className="submit-feedback" onClick={submitFeedback}>
              Submit Feedback
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default CallRecordingPlayer;
