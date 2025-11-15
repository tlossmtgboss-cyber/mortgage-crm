import React, { useState } from 'react';
import './RecordingModal.css';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname.includes('vercel.app');
const API_BASE_URL = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

function RecordingModal({ isOpen, onClose, lead }) {
  const [meetingUrl, setMeetingUrl] = useState('');
  const [botName, setBotName] = useState('Mortgage CRM Assistant');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);

  const startRecording = async () => {
    if (!meetingUrl.trim()) {
      setResult({ status: 'error', message: 'Please enter a meeting URL' });
      return;
    }

    // Validate URL format
    const urlPattern = /^https:\/\/(zoom\.us|teams\.microsoft\.com|meet\.google\.com)/i;
    if (!urlPattern.test(meetingUrl)) {
      setResult({
        status: 'error',
        message: 'Please enter a valid Zoom, Teams, or Google Meet URL'
      });
      return;
    }

    setSending(true);
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/recallai/start-recording`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          meeting_url: meetingUrl,
          lead_id: lead.id,
          bot_name: botName
        })
      });

      const data = await response.json();

      if (response.ok) {
        setResult({
          status: 'success',
          message: 'Recording bot is joining the meeting!',
          details: data
        });
        setMeetingUrl('');

        // Close modal after 3 seconds
        setTimeout(() => {
          onClose();
          setResult(null);
        }, 3000);
      } else {
        setResult({
          status: 'error',
          message: data.detail || 'Failed to start recording'
        });
      }
    } catch (error) {
      setResult({
        status: 'error',
        message: 'Network error. Please check your connection and try again.'
      });
    } finally {
      setSending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content recording-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>🎥 Record Meeting</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          <p className="modal-description">
            Start a Recall.ai bot to record your Zoom, Teams, or Google Meet meeting.
            The bot will join the meeting and provide a transcript when complete.
          </p>

          <div className="form-group">
            <label htmlFor="meeting-url">Meeting URL *</label>
            <input
              id="meeting-url"
              type="url"
              className="form-control"
              value={meetingUrl}
              onChange={(e) => setMeetingUrl(e.target.value)}
              placeholder="https://zoom.us/j/123456789 or Teams/Meet URL"
              disabled={sending}
            />
            <small className="form-hint">
              Paste the meeting link from Zoom, Microsoft Teams, or Google Meet
            </small>
          </div>

          <div className="form-group">
            <label htmlFor="bot-name">Bot Name (Optional)</label>
            <input
              id="bot-name"
              type="text"
              className="form-control"
              value={botName}
              onChange={(e) => setBotName(e.target.value)}
              placeholder="Mortgage CRM Assistant"
              disabled={sending}
            />
            <small className="form-hint">
              This name will be displayed in the meeting participant list
            </small>
          </div>

          {result && (
            <div className={`result-message ${result.status}`}>
              {result.status === 'success' ? '✅' : '❌'} {result.message}
              {result.details && result.details.bot_id && (
                <div className="bot-details">
                  <small>Bot ID: {result.details.bot_id}</small>
                  <br />
                  <small>Status: {result.details.status}</small>
                </div>
              )}
            </div>
          )}

          <div className="meeting-platforms">
            <div className="platform-info">
              <strong>Supported Platforms:</strong>
              <div className="platforms">
                <span className="platform">📹 Zoom</span>
                <span className="platform">👥 Microsoft Teams</span>
                <span className="platform">📞 Google Meet</span>
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={sending}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={startRecording}
            disabled={sending || !meetingUrl}
          >
            {sending ? 'Starting Bot...' : 'Start Recording'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default RecordingModal;
