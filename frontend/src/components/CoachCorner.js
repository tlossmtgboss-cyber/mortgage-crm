import React, { useState } from 'react';
import './CoachCorner.css';

const CoachCorner = () => {
  const [mode, setMode] = useState(null);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [customMessage, setCustomMessage] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);

  const coachModes = [
    {
      id: 'daily_briefing',
      label: 'Daily Briefing',
      icon: '📋',
      description: 'Get your top 3 priorities for today'
    },
    {
      id: 'pipeline_audit',
      label: 'Pipeline Audit',
      icon: '🔍',
      description: 'Identify bottlenecks and stalled deals'
    },
    {
      id: 'focus_reset',
      label: 'Focus Reset',
      icon: '🎯',
      description: 'Get back on track when scattered'
    },
    {
      id: 'priority_guidance',
      label: 'What Should I Do Next?',
      icon: '❓',
      description: 'Priority decision guidance'
    },
    {
      id: 'accountability',
      label: 'Accountability Review',
      icon: '📊',
      description: 'Review your performance'
    },
    {
      id: 'tough_love',
      label: 'Tough Love Mode',
      icon: '💪',
      description: 'Call out inefficiencies directly'
    },
    {
      id: 'teach_process',
      label: 'Teach Me The Process',
      icon: '📚',
      description: 'Learn systems thinking and execution'
    },
    {
      id: 'tactical_advice',
      label: 'Ask a Question',
      icon: '💬',
      description: 'Get specific tactical advice'
    }
  ];

  const callCoach = async (selectedMode, message = null) => {
    setLoading(true);
    setMode(selectedMode);
    setResponse(null);

    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL}/api/v1/coach`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          mode: selectedMode,
          message: message
        })
      });

      if (!res.ok) {
        throw new Error('Coach unavailable');
      }

      const data = await res.json();
      setResponse(data);
    } catch (error) {
      console.error('Coach error:', error);
      alert('Coach unavailable. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleAskQuestion = () => {
    if (!customMessage.trim()) {
      alert('Please enter your question');
      return;
    }
    callCoach('tactical_advice', customMessage);
    setShowCustomInput(false);
    setCustomMessage('');
  };

  if (loading) {
    return (
      <div className="coach-corner">
        <div className="coach-header">
          <h2>🏆 The Process Coach</h2>
          <p className="coach-subtitle">High-Performance Guidance System</p>
        </div>
        <div className="coach-loading">
          <div className="loading-spinner"></div>
          <p>Coach analyzing your pipeline...</p>
        </div>
      </div>
    );
  }

  if (response) {
    return (
      <div className="coach-corner">
        <div className="coach-header">
          <h2>🏆 The Process Coach</h2>
          <button className="btn-back" onClick={() => setResponse(null)}>
            ← Back
          </button>
        </div>

        <div className="coach-response-container">
          <div className="coach-mode-badge">{mode.replace('_', ' ').toUpperCase()}</div>

          <div className="coach-message">
            {response.response.split('\n').map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>

          {response.priorities && response.priorities.length > 0 && (
            <div className="priorities-section">
              <h3>Priority Actions</h3>
              {response.priorities.map((p, i) => (
                <div key={i} className={`priority-item urgency-${p.urgency.toLowerCase()}`}>
                  <div className="priority-header">
                    <span className="priority-number">#{p.priority}</span>
                    <span className="priority-category">{p.category}</span>
                    <span className={`urgency-badge ${p.urgency.toLowerCase()}`}>{p.urgency}</span>
                  </div>
                  <div className="priority-action">{p.action}</div>
                </div>
              ))}
            </div>
          )}

          {response.action_items && response.action_items.length > 0 && (
            <div className="action-items-section">
              <h3>Action Items</h3>
              <ul>
                {response.action_items.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {response.metrics && (
            <div className="metrics-section">
              <div className="metric-card">
                <span className="metric-label">Pipeline Health</span>
                <span className={`metric-value health-${response.metrics.pipeline_health}`}>
                  {response.metrics.pipeline_health === 'good' ? '✅ Good' : '⚠️ Needs Attention'}
                </span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Bottlenecks</span>
                <span className="metric-value">{response.metrics.total_bottlenecks}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Overdue Tasks</span>
                <span className="metric-value">{response.metrics.overdue_tasks}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="coach-corner">
      <div className="coach-header">
        <h2>🏆 The Process Coach</h2>
        <p className="coach-subtitle">Elite Performance Guidance for Mortgage Professionals</p>
      </div>

      <div className="coach-intro">
        <p><strong>Philosophy:</strong> Process over outcome. Standards over feelings. Execution over excuses.</p>
        <p>Select a coaching mode below:</p>
      </div>

      <div className="coach-modes-grid">
        {coachModes.map(m => (
          <button
            key={m.id}
            className="coach-mode-button"
            onClick={() => {
              if (m.id === 'tactical_advice') {
                setShowCustomInput(true);
              } else {
                callCoach(m.id);
              }
            }}
          >
            <div className="mode-icon">{m.icon}</div>
            <div className="mode-label">{m.label}</div>
            <div className="mode-description">{m.description}</div>
          </button>
        ))}
      </div>

      {showCustomInput && (
        <div className="custom-input-modal">
          <div className="modal-content">
            <h3>Ask The Coach</h3>
            <textarea
              value={customMessage}
              onChange={(e) => setCustomMessage(e.target.value)}
              placeholder="What's your question? Be specific."
              rows="4"
            />
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => {
                setShowCustomInput(false);
                setCustomMessage('');
              }}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleAskQuestion}>
                Get Guidance
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="coach-quick-actions">
        <button
          className="quick-action-btn"
          onClick={() => callCoach('daily_briefing')}
        >
          Give Me My Priorities
        </button>
        <button
          className="quick-action-btn"
          onClick={() => callCoach('pipeline_audit')}
        >
          Fix My Pipeline
        </button>
        <button
          className="quick-action-btn"
          onClick={() => callCoach('focus_reset')}
        >
          Reset My Focus
        </button>
      </div>
    </div>
  );
};

export default CoachCorner;
