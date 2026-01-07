import React, { useState } from 'react';
import { LiveCallWhisper, LiveCallWhisperWidget, LiveCallWhisperDemo } from '../components/LiveCallWhisper';
import './LiveCallWhisper.css';

export default function LiveCallWhisperPage() {
  const [mode, setMode] = useState('widget'); // widget, active, demo
  const [callId, setCallId] = useState(null);
  const [callSummary, setCallSummary] = useState(null);

  const handleStartCall = () => {
    // Generate a unique call ID
    const newCallId = `call-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setCallId(newCallId);
    setMode('active');
  };

  const handleEndCall = (summary) => {
    setCallSummary(summary);
    setMode('widget');
    setCallId(null);
  };

  return (
    <div className="live-call-whisper-page">
      <div className="page-header">
        <div className="header-content">
          <h1>Live Call Coaching</h1>
          <p>Real-time AI assistance during phone calls</p>
        </div>
        <div className="header-actions">
          <button
            className={`mode-btn ${mode === 'widget' ? 'active' : ''}`}
            onClick={() => setMode('widget')}
          >
            Widget
          </button>
          <button
            className={`mode-btn ${mode === 'demo' ? 'active' : ''}`}
            onClick={() => setMode('demo')}
          >
            Demo
          </button>
        </div>
      </div>

      {/* Call Summary (shown after call ends) */}
      {callSummary && (
        <div className="call-summary-banner">
          <div className="summary-header">
            <h3>Call Summary</h3>
            <button onClick={() => setCallSummary(null)}>Dismiss</button>
          </div>
          <div className="summary-content">
            <div className="summary-stat">
              <span className="label">Duration</span>
              <span className="value">
                {Math.floor((callSummary.duration_seconds || 0) / 60)}:
                {String((callSummary.duration_seconds || 0) % 60).padStart(2, '0')}
              </span>
            </div>
            <div className="summary-stat">
              <span className="label">Whispers Used</span>
              <span className="value">{callSummary.whispers_used || 0}</span>
            </div>
            <div className="summary-stat">
              <span className="label">Final Stage</span>
              <span className="value">{callSummary.final_stage || 'Unknown'}</span>
            </div>
            <div className="summary-stat">
              <span className="label">Sentiment</span>
              <span className="value">{callSummary.final_sentiment || 'Neutral'}</span>
            </div>
          </div>
          {callSummary.topics_discussed?.length > 0 && (
            <div className="summary-topics">
              <span className="label">Topics Discussed:</span>
              <div className="topic-tags">
                {callSummary.topics_discussed.map((topic, idx) => (
                  <span key={idx} className="topic-tag">{topic}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Main Content */}
      <div className="page-content">
        {mode === 'widget' && (
          <div className="widget-container">
            <LiveCallWhisperWidget
              callId={callId}
              onStartCall={handleStartCall}
            />
          </div>
        )}

        {mode === 'active' && callId && (
          <div className="active-call-container">
            <LiveCallWhisper
              callId={callId}
              callerInfo={{
                name: 'Incoming Call',
                type: 'prospect',
              }}
              onCallEnd={handleEndCall}
            />
          </div>
        )}

        {mode === 'demo' && (
          <LiveCallWhisperDemo />
        )}
      </div>

      {/* Feature Overview */}
      {mode === 'widget' && !callSummary && (
        <div className="feature-overview">
          <h2>AI-Powered Call Coaching Features</h2>
          <div className="features-grid">
            <div className="feature-card">
              <div className="feature-icon">🛡️</div>
              <h3>Objection Handling</h3>
              <p>
                Get instant suggestions when prospects raise concerns about rates,
                timing, or fees. AI detects objection patterns and provides proven
                responses.
              </p>
            </div>
            <div className="feature-card">
              <div className="feature-icon">📊</div>
              <h3>Real-Time Rate Info</h3>
              <p>
                Accurate rate quotes and product comparisons delivered instantly
                during calls, so you never miss a beat.
              </p>
            </div>
            <div className="feature-card">
              <div className="feature-icon">⚖️</div>
              <h3>Compliance Reminders</h3>
              <p>
                Stay compliant with automatic reminders for required disclosures
                and prohibited topics during each call stage.
              </p>
            </div>
            <div className="feature-card">
              <div className="feature-icon">🎯</div>
              <h3>Closing Techniques</h3>
              <p>
                AI detects buying signals and suggests effective closing techniques
                tailored to the conversation flow.
              </p>
            </div>
            <div className="feature-card">
              <div className="feature-icon">🤝</div>
              <h3>Rapport Building</h3>
              <p>
                Personalized talking points and rapport-building suggestions based
                on borrower information and conversation history.
              </p>
            </div>
            <div className="feature-card">
              <div className="feature-icon">📈</div>
              <h3>Call Analytics</h3>
              <p>
                Track sentiment, topics discussed, and call progression in real-time.
                Get comprehensive summaries after each call.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
