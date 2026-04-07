/**
 * Recording Player / Transcript Viewer Component
 *
 * Displays the call transcript with speaker labels.
 * Audio playback will be added in a future phase.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';

const RecordingPlayer = ({ transcript, participants, session }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const audioRef = useRef(null);

  const audioUrl = session?.recording_id
    ? `/api/v1/conversation-intelligence/recordings/${session.recording_id}/audio`
    : null;

  // Audio event handlers
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => setCurrentTime(audio.currentTime);
    const onDurationChange = () => setDuration(audio.duration || 0);
    const onEnded = () => setIsPlaying(false);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('durationchange', onDurationChange);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('durationchange', onDurationChange);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
    };
  }, [audioUrl]);

  const togglePlayback = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
    } else {
      audio.play().catch(() => {});
    }
  }, [isPlaying]);

  const handleSeek = useCallback((e) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Number(e.target.value);
  }, []);

  const skip = useCallback((seconds) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + seconds));
  }, []);

  const formatTime = (seconds) => {
    if (!seconds || !isFinite(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  if (!transcript) {
    return (
      <div className="transcript-viewer">
        <p style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
          No transcript available for this call.
        </p>
      </div>
    );
  }

  // Parse transcript into speaker lines
  const parseTranscript = (text) => {
    if (!text) return [];

    const lines = text.split('\n').filter(line => line.trim());
    return lines.map((line, index) => {
      // Check for speaker label pattern like "[Speaker 1]: text" or "LO: text"
      const speakerMatch = line.match(/^\[([^\]]+)\]:\s*(.*)$/) ||
                           line.match(/^([A-Za-z]+):\s*(.*)$/);

      if (speakerMatch) {
        return {
          id: index,
          speaker: speakerMatch[1],
          text: speakerMatch[2],
        };
      }

      return {
        id: index,
        speaker: null,
        text: line,
      };
    });
  };

  const lines = parseTranscript(transcript);

  // Filter by search term
  const filteredLines = searchTerm
    ? lines.filter(line =>
        line.text.toLowerCase().includes(searchTerm.toLowerCase()) ||
        line.speaker?.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : lines;

  // Get speaker color
  const getSpeakerColor = (speaker) => {
    if (!speaker) return '#6b7280';
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'];
    const index = speaker.charCodeAt(0) % colors.length;
    return colors[index];
  };

  // Get speaker name from participants if available
  const getSpeakerName = (speakerLabel) => {
    if (!speakerLabel || !participants) return speakerLabel;
    const participant = participants.find(p => p.speaker_label === speakerLabel);
    return participant?.name || speakerLabel;
  };

  return (
    <div className="transcript-viewer">
      {/* Controls */}
      <div className="transcript-controls">
        <input
          type="text"
          placeholder="Search transcript..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            flex: 1,
            padding: '8px 12px',
            border: '1px solid #e5e7eb',
            borderRadius: '6px',
            fontSize: '0.875rem',
          }}
        />

        {audioUrl && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              style={{
                padding: '8px 12px',
                background: isPlaying ? '#dbeafe' : '#f3f4f6',
                border: `1px solid ${isPlaying ? '#93c5fd' : '#e5e7eb'}`,
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.875rem',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                minWidth: '36px',
                justifyContent: 'center',
              }}
              onClick={() => skip(-10)}
              title="Back 10s"
            >
              -10s
            </button>
            <button
              style={{
                padding: '8px 16px',
                background: isPlaying ? '#dbeafe' : '#f3f4f6',
                border: `1px solid ${isPlaying ? '#93c5fd' : '#e5e7eb'}`,
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.875rem',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
              onClick={togglePlayback}
            >
              {isPlaying ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="4" width="4" height="16" />
                  <rect x="14" y="4" width="4" height="16" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
              )}
              {isPlaying ? 'Pause' : 'Play'}
            </button>
            <button
              style={{
                padding: '8px 12px',
                background: isPlaying ? '#dbeafe' : '#f3f4f6',
                border: `1px solid ${isPlaying ? '#93c5fd' : '#e5e7eb'}`,
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.875rem',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                minWidth: '36px',
                justifyContent: 'center',
              }}
              onClick={() => skip(10)}
              title="Forward 10s"
            >
              +10s
            </button>
            <span style={{ fontSize: '0.75rem', color: '#6b7280', minWidth: '70px' }}>
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>
        )}
      </div>

      {/* Hidden Audio Element + Seek Bar */}
      {audioUrl && (
        <>
          <audio ref={audioRef} src={audioUrl} preload="metadata" />
          <div style={{ padding: '0 0 12px 0' }}>
            <input
              type="range"
              min="0"
              max={duration || 0}
              value={currentTime}
              onChange={handleSeek}
              style={{ width: '100%', cursor: 'pointer' }}
            />
          </div>
        </>
      )}

      {/* Participants Legend */}
      {participants && participants.length > 0 && (
        <div style={{
          display: 'flex',
          gap: '16px',
          marginBottom: '16px',
          paddingBottom: '12px',
          borderBottom: '1px solid #e5e7eb',
          flexWrap: 'wrap',
        }}>
          {participants.map((p) => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  background: getSpeakerColor(p.speaker_label || p.role),
                }}
              />
              <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>
                {p.name || p.role}
                {p.talk_time_seconds && ` (${Math.round(p.talk_time_seconds / 60)}m)`}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Transcript Content */}
      <div className="transcript-text">
        {filteredLines.length === 0 ? (
          <p style={{ color: '#6b7280', textAlign: 'center', padding: '20px' }}>
            {searchTerm ? 'No matches found' : 'No transcript content'}
          </p>
        ) : (
          filteredLines.map((line) => (
            <div key={line.id} className="speaker-line">
              {line.speaker && (
                <span
                  className="speaker-label"
                  style={{ color: getSpeakerColor(line.speaker) }}
                >
                  {getSpeakerName(line.speaker)}:
                </span>
              )}
              <span>{line.text}</span>
            </div>
          ))
        )}
      </div>

      {/* Word Count */}
      <div style={{
        marginTop: '16px',
        paddingTop: '12px',
        borderTop: '1px solid #e5e7eb',
        fontSize: '0.75rem',
        color: '#9ca3af',
      }}>
        {transcript.split(/\s+/).length} words
        {searchTerm && ` | ${filteredLines.length} matches`}
      </div>
    </div>
  );
};

export default RecordingPlayer;
