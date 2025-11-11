import React, { useState } from 'react';
import './SMSModal.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function SMSModal({ isOpen, onClose, lead }) {
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [useTemplate, setUseTemplate] = useState('');

  const templates = [
    {
      id: 'intro',
      name: 'Introduction',
      message: `Hi ${lead?.first_name || '[Name]'}, this is [Your Name] from [Company]. I wanted to reach out regarding your mortgage inquiry. When would be a good time to chat?`
    },
    {
      id: 'followup',
      name: 'Follow Up',
      message: `Hi ${lead?.first_name || '[Name]'}, just following up on our conversation. Do you have any questions about your mortgage options?`
    },
    {
      id: 'appointment',
      name: 'Appointment Reminder',
      message: `Hi ${lead?.first_name || '[Name]'}, this is a reminder about our appointment tomorrow. Looking forward to speaking with you!`
    },
    {
      id: 'custom',
      name: 'Custom Message',
      message: ''
    }
  ];

  const handleTemplateChange = (templateId) => {
    setUseTemplate(templateId);
    const template = templates.find(t => t.id === templateId);
    if (template) {
      setMessage(template.message);
    }
  };

  const sendSMS = async () => {
    if (!message.trim()) {
      setResult({ status: 'error', message: 'Please enter a message' });
      return;
    }

    setSending(true);
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/sms/send`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          to_number: lead.phone,
          message: message,
          lead_id: lead.id
        })
      });

      const data = await response.json();

      if (response.ok) {
        setResult({
          status: 'success',
          message: 'SMS sent successfully!',
          details: data
        });
        setMessage('');
        setUseTemplate('');

        // Close modal after 2 seconds
        setTimeout(() => {
          onClose();
        }, 2000);
      } else {
        setResult({
          status: 'error',
          message: data.detail || 'Failed to send SMS'
        });
      }
    } catch (error) {
      setResult({
        status: 'error',
        message: `Error: ${error.message}`
      });
    } finally {
      setSending(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      sendSMS();
    }
  };

  if (!isOpen) return null;

  const characterCount = message.length;
  const smsCount = Math.ceil(characterCount / 160);

  return (
    <div className="sms-modal-overlay" onClick={onClose}>
      <div className="sms-modal" onClick={(e) => e.stopPropagation()}>
        <div className="sms-modal-header">
          <div className="header-info">
            <h2>💬 Send SMS</h2>
            <p className="recipient-info">
              To: <strong>{lead?.first_name} {lead?.last_name}</strong> ({lead?.phone})
            </p>
          </div>
          <button className="btn-close-modal" onClick={onClose}>×</button>
        </div>

        <div className="sms-modal-body">
          {/* Template Selector */}
          <div className="form-group">
            <label>Quick Templates</label>
            <select
              value={useTemplate}
              onChange={(e) => handleTemplateChange(e.target.value)}
              className="template-select"
            >
              <option value="">Select a template...</option>
              {templates.map(template => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </div>

          {/* Message Input */}
          <div className="form-group">
            <label>Message</label>
            <textarea
              className="message-input"
              placeholder="Type your message here..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              rows="6"
              disabled={sending}
            />
            <div className="message-meta">
              <span className="char-count">
                {characterCount} characters • {smsCount} SMS
              </span>
              <span className="hint">Ctrl + Enter to send</span>
            </div>
          </div>

          {/* Result Message */}
          {result && (
            <div className={`result-message ${result.status}`}>
              <span className="result-icon">
                {result.status === 'success' ? '✅' : '❌'}
              </span>
              <span>{result.message}</span>
            </div>
          )}
        </div>

        <div className="sms-modal-footer">
          <button
            className="btn-secondary"
            onClick={onClose}
            disabled={sending}
          >
            Cancel
          </button>
          <button
            className="btn-primary-sms"
            onClick={sendSMS}
            disabled={sending || !message.trim()}
          >
            {sending ? (
              <>
                <span className="spinner"></span>
                Sending...
              </>
            ) : (
              <>
                <span>📤</span>
                Send SMS
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SMSModal;
