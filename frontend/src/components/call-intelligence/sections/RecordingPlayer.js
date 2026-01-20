/**
 * Recording Player / Transcript Viewer Component
 *
 * Displays the call transcript with speaker labels.
 * Audio playback will be added in a future phase.
 */

import React, { useState } from 'react';

const RecordingPlayer = ({ transcript, participants, session }) => {
  const [searchTerm, setSearchTerm] = useState('');

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

        {session?.recording_id && (
          <button
            style={{
              padding: '8px 16px',
              background: '#f3f4f6',
              border: '1px solid #e5e7eb',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.875rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
            onClick={() => {/* TODO: Open audio player */}}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            Play Audio
          </button>
        )}
      </div>

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
