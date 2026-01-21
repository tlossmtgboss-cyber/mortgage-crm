/**
 * Live Call Assistant Component
 *
 * Real-time AI assistant panel for active calls showing:
 * - Live transcript with auto-scroll
 * - AI suggestions (questions, objection handling, compliance)
 * - Sentiment indicators
 * - Quick actions
 */

import React, { useState, useEffect, useRef } from 'react';

const LiveCallAssistant = ({
  session,
  transcript,
  suggestions,
  isPolling,
}) => {
  const [activeTab, setActiveTab] = useState('transcript');
  const [showNoteInput, setShowNoteInput] = useState(false);
  const [note, setNote] = useState('');
  const transcriptRef = useRef(null);

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptRef.current && activeTab === 'transcript') {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript, activeTab]);

  // Calculate duration
  const calculateLiveDuration = (startedAt) => {
    if (!startedAt) return '00:00';
    const start = new Date(startedAt);
    const now = new Date();
    const diffSeconds = Math.floor((now - start) / 1000);
    const mins = Math.floor(diffSeconds / 60);
    const secs = diffSeconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Parse transcript into lines with speaker labels
  const parseTranscript = (text) => {
    if (!text) return [];
    // Split by common transcript patterns
    const lines = text.split(/(?=(?:Speaker|Agent|Borrower|LO|Client)[\s\d]*:)/gi);
    return lines.filter(line => line.trim()).map((line, idx) => {
      const match = line.match(/^((?:Speaker|Agent|Borrower|LO|Client)[\s\d]*):?\s*(.*)/i);
      if (match) {
        return {
          id: idx,
          speaker: match[1].trim(),
          text: match[2].trim(),
        };
      }
      return {
        id: idx,
        speaker: null,
        text: line.trim(),
      };
    });
  };

  // Get suggestion icon
  const getSuggestionIcon = (type) => {
    switch (type) {
      case 'question':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        );
      case 'info':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        );
      case 'compliance':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        );
      case 'objection':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        );
      default:
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        );
    }
  };

  // Get priority class
  const getPriorityClass = (priority) => {
    switch (priority) {
      case 'high':
        return 'priority-high';
      case 'medium':
        return 'priority-medium';
      case 'low':
        return 'priority-low';
      default:
        return '';
    }
  };

  // Quick prompts
  const quickPrompts = [
    { label: 'Income Details', text: 'What is your annual income and employment type?' },
    { label: 'Timeline', text: 'What is your ideal timeline for closing?' },
    { label: 'Pre-approval', text: 'Have you been pre-approved by any other lender?' },
    { label: 'Property Type', text: 'What type of property are you looking for?' },
  ];

  const transcriptLines = parseTranscript(transcript);

  return (
    <div className="live-call-assistant">
      {/* Header */}
      <div className="lca-header">
        <div className="lca-header-info">
          <div className="lca-caller">
            {session.metadata?.caller_name || 'Active Call'}
          </div>
          <div className="lca-duration">
            <span className="live-indicator"></span>
            {calculateLiveDuration(session.started_at)}
          </div>
        </div>
        <div className="lca-status">
          {isPolling ? (
            <span className="polling-indicator">
              <span className="pulse-dot"></span>
              Live
            </span>
          ) : (
            <span>Paused</span>
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="lca-tabs">
        <button
          className={activeTab === 'transcript' ? 'active' : ''}
          onClick={() => setActiveTab('transcript')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          Transcript
        </button>
        <button
          className={activeTab === 'suggestions' ? 'active' : ''}
          onClick={() => setActiveTab('suggestions')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          AI Assist
          {suggestions.length > 0 && (
            <span className="tab-badge">{suggestions.length}</span>
          )}
        </button>
        <button
          className={activeTab === 'prompts' ? 'active' : ''}
          onClick={() => setActiveTab('prompts')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          Prompts
        </button>
      </div>

      {/* Content */}
      <div className="lca-content">
        {/* Transcript Tab */}
        {activeTab === 'transcript' && (
          <div className="lca-transcript" ref={transcriptRef}>
            {transcriptLines.length === 0 ? (
              <div className="lca-transcript-empty">
                <p>Waiting for transcript...</p>
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            ) : (
              transcriptLines.map(line => (
                <div key={line.id} className="transcript-line">
                  {line.speaker && (
                    <span className={`speaker-label ${line.speaker.toLowerCase().includes('agent') || line.speaker.toLowerCase().includes('lo') ? 'agent' : 'client'}`}>
                      {line.speaker}:
                    </span>
                  )}
                  <span className="transcript-text">{line.text}</span>
                </div>
              ))
            )}
          </div>
        )}

        {/* Suggestions Tab */}
        {activeTab === 'suggestions' && (
          <div className="lca-suggestions">
            {suggestions.length === 0 ? (
              <div className="lca-suggestions-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="16" x2="12" y2="12" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
                <p>AI suggestions will appear here based on the conversation</p>
              </div>
            ) : (
              suggestions.map((suggestion, idx) => (
                <div
                  key={idx}
                  className={`lca-suggestion ${getPriorityClass(suggestion.priority)}`}
                >
                  <div className="suggestion-icon">
                    {getSuggestionIcon(suggestion.type)}
                  </div>
                  <div className="suggestion-content">
                    <span className="suggestion-type">{suggestion.type}</span>
                    <p className="suggestion-text">{suggestion.text}</p>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Quick Prompts Tab */}
        {activeTab === 'prompts' && (
          <div className="lca-prompts">
            <p className="prompts-intro">Quick discovery questions to ask:</p>
            {quickPrompts.map((prompt, idx) => (
              <div key={idx} className="lca-prompt-card">
                <div className="prompt-label">{prompt.label}</div>
                <div className="prompt-text">"{prompt.text}"</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="lca-actions">
        {showNoteInput ? (
          <div className="lca-note-input">
            <input
              type="text"
              placeholder="Add a note..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
              autoFocus
            />
            <button
              className="save-note-btn"
              onClick={() => {
                // In production, save note to session
                setNote('');
                setShowNoteInput(false);
              }}
            >
              Save
            </button>
            <button
              className="cancel-note-btn"
              onClick={() => {
                setNote('');
                setShowNoteInput(false);
              }}
            >
              Cancel
            </button>
          </div>
        ) : (
          <>
            <button
              className="lca-action-btn"
              onClick={() => setShowNoteInput(true)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              Add Note
            </button>
            <button className="lca-action-btn flag">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
                <line x1="4" y1="22" x2="4" y2="15" />
              </svg>
              Flag for Review
            </button>
          </>
        )}
      </div>
    </div>
  );
};

export default LiveCallAssistant;
