import React, { useState } from 'react';
import './VoicemailModal.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function VoicemailModal({ isOpen, onClose, lead }) {
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [useTemplate, setUseTemplate] = useState('');

  const templates = [
    {
      id: 'intro',
      name: 'Introduction',
      message: `Hi ${lead?.first_name || '[Name]'}, this is [Your Name] from [Company]. I wanted to reach out regarding your mortgage inquiry. Please give me a call back at your earliest convenience. Looking forward to speaking with you!`
    },
    {
      id: 'followup',
      name: 'Follow Up',
      message: `Hi ${lead?.first_name || '[Name]'}, just following up on our previous conversation. I have some updates on your mortgage options. Please call me back when you have a chance.`
    },
    {
      id: 'rate_update',
      name: 'Rate Update',
      message: `Hi ${lead?.first_name || '[Name]'}, I wanted to let you know that we have some great new rate options available. Please give me a call to discuss how we can save you money.`
    },
    {
      id: 'appointment',
      name: 'Appointment Reminder',
      message: `Hi ${lead?.first_name || '[Name]'}, this is a reminder about our scheduled appointment. Please call me to confirm or if you need to reschedule. Thank you!`
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

  const dropVoicemail = async () => {
    if (!message.trim()) {
      setResult({ status: 'error', message: 'Please enter a message' });
      return;
    }

    setSending(true);
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/voicemail/drop`, {
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
          message: 'Voicemail dropped successfully!',
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
          message: data.detail || 'Failed to drop voicemail'
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
      dropVoicemail();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="voicemail-modal-overlay" onClick={onClose}>
      <div className="voicemail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="voicemail-modal-header">
          <div className="header-info">
            <h2>📞 Drop Voicemail</h2>
            <p className="recipient-info">
              To: <strong>{lead?.first_name} {lead?.last_name}</strong> ({lead?.phone})
            </p>
          </div>
          <button className="btn-close-modal" onClick={onClose}>×</button>
        </div>

        <div className="voicemail-modal-body">
          {/* Template Selector */}
          <div className="form-group">
            <label>Voicemail Templates</label>
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
            <label>Voicemail Message</label>
            <textarea
              className="message-input"
              placeholder="Type your voicemail message here..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              rows="6"
              disabled={sending}
            />
            <div className="message-meta">
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

        <div className="voicemail-modal-footer">
          <button
            className="btn-secondary"
            onClick={onClose}
            disabled={sending}
          >
            Cancel
          </button>
          <button
            className="btn-primary-voicemail"
            onClick={dropVoicemail}
            disabled={sending || !message.trim()}
          >
            {sending ? (
              <>
                <span className="spinner"></span>
                Sending...
              </>
            ) : (
              <>
                <span>📞</span>
                Drop Voicemail
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default VoicemailModal;
