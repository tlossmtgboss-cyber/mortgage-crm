// ─────────────────────────────────────────────────────────────
// NOTE TAKER CARD
// src/components/callIntelligence/NoteTakerCard.jsx
// ─────────────────────────────────────────────────────────────

import React, { useRef, useEffect } from 'react';
import './NoteTakerCard.css';

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatTimestamp(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function TranscriptRow({ line }) {
  const isLO = line.speaker === 'lo';
  return (
    <div className="note-taker-card__transcript-row">
      <div className={`note-taker-card__speaker-badge ${isLO ? 'note-taker-card__speaker-badge--lo' : 'note-taker-card__speaker-badge--client'}`}>
        <span className={`note-taker-card__speaker-text ${isLO ? 'note-taker-card__speaker-text--lo' : 'note-taker-card__speaker-text--client'}`}>
          {isLO ? 'LO' : 'CLIENT'}
        </span>
      </div>
      <span className={`note-taker-card__transcript-text ${!line.is_final ? 'note-taker-card__transcript-text--partial' : ''}`}>
        {line.text}
      </span>
      <span className="note-taker-card__transcript-time">
        {formatTimestamp(line.timestamp_seconds)}
      </span>
    </div>
  );
}

export default function NoteTakerCard({ state, callDurationSeconds }) {
  const scrollRef = useRef(null);

  // Auto-scroll to bottom as new lines come in
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [state.lines.length]);

  const recentLines = state.lines.slice(-4); // show last 4 lines

  return (
    <div className="note-taker-card">
      {/* Header */}
      <div className="note-taker-card__header">
        <div className="note-taker-card__title-row">
          <div className="note-taker-card__dot" />
          <span className="note-taker-card__agent-name">Note Taker</span>
        </div>
        <div className="note-taker-card__tag-live">
          <div className="note-taker-card__record-dot" />
          <span className="note-taker-card__tag-text">Transcribing</span>
        </div>
      </div>

      {/* Live transcript */}
      {state.lines.length === 0 ? (
        <p className="note-taker-card__waiting">Waiting for conversation...</p>
      ) : (
        <div
          ref={scrollRef}
          className="note-taker-card__transcript-scroll"
        >
          {recentLines.map((line) => (
            <TranscriptRow key={line.id} line={line} />
          ))}
        </div>
      )}

      {/* Topics */}
      {state.key_topics.length > 0 && (
        <div className="note-taker-card__topics-row">
          {state.key_topics.slice(0, 4).map((topic) => (
            <div key={topic} className="note-taker-card__topic-pill">
              <span className="note-taker-card__topic-text">{topic}</span>
            </div>
          ))}
        </div>
      )}

      {/* Stats footer */}
      <div className="note-taker-card__footer">
        <div className="note-taker-card__stat">
          <span className="note-taker-card__stat-val">{formatDuration(callDurationSeconds)}</span>
          <span className="note-taker-card__stat-label">Duration</span>
        </div>
        <div className="note-taker-card__stat-divider" />
        <div className="note-taker-card__stat">
          <span className="note-taker-card__stat-val">{state.word_count}</span>
          <span className="note-taker-card__stat-label">Words</span>
        </div>
        <div className="note-taker-card__stat-divider" />
        <div className="note-taker-card__stat">
          <span className="note-taker-card__stat-val">{state.key_topics.length}</span>
          <span className="note-taker-card__stat-label">Topics</span>
        </div>
      </div>
    </div>
  );
}
