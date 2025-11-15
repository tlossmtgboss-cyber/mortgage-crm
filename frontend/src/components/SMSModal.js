import React, { useState } from 'react';
import { aiAPI } from '../services/api';
import './SMSModal.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function SMSModal({ isOpen, onClose, lead }) {
  const [mode, setMode] = useState('manual'); // 'manual' or 'ai'
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [useTemplate, setUseTemplate] = useState('');

  // AI Agent state
  const [aiTask, setAiTask] = useState('');
  const [aiRunning, setAiRunning] = useState(false);
  const [aiActivity, setAiActivity] = useState([]);
  const [aiComplete, setAiComplete] = useState(false);

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

  const executeAITask = async () => {
    if (!aiTask.trim()) {
      setResult({ status: 'error', message: 'Please enter a task for the AI agent' });
      return;
    }

    setAiRunning(true);
    setAiActivity([]);
    setAiComplete(false);
    setResult(null);

    try {
      // Call autonomous AI task endpoint
      const response = await fetch(`${API_BASE_URL}/api/v1/ai/autonomous-task`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          task: aiTask,
          lead_id: lead.id,
          lead_name: `${lead.first_name} ${lead.last_name}`,
          lead_phone: lead.phone,
          context: {
            lead_first_name: lead.first_name,
            lead_last_name: lead.last_name,
            lead_phone: lead.phone,
            lead_email: lead.email
          }
        })
      });

      const data = await response.json();

      if (response.ok) {
        // Show activity log from AI
        if (data.activity_log) {
          setAiActivity(data.activity_log);
        }

        setAiComplete(true);
        setResult({
          status: 'success',
          message: 'AI Agent completed the task successfully!',
          details: data
        });

        // Close modal after 3 seconds
        setTimeout(() => {
          onClose();
        }, 3000);
      } else {
        setResult({
          status: 'error',
          message: data.detail || 'AI Agent failed to complete the task'
        });
      }
    } catch (error) {
      setResult({
        status: 'error',
        message: `Error: ${error.message}`
      });
    } finally {
      setAiRunning(false);
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
          {/* Mode Toggle */}
          <div className="mode-toggle">
            <button
              className={`mode-btn ${mode === 'manual' ? 'active' : ''}`}
              onClick={() => setMode('manual')}
            >
              📝 Manual SMS
            </button>
            <button
              className={`mode-btn ${mode === 'ai' ? 'active' : ''}`}
              onClick={() => setMode('ai')}
            >
              🤖 AI Agent
            </button>
          </div>

          {/* Manual Mode */}
          {mode === 'manual' && (
            <>
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
            </>
          )}

          {/* AI Agent Mode */}
          {mode === 'ai' && (
            <>
              <div className="ai-agent-section">
                <div className="form-group">
                  <label>AI Agent Task</label>
                  <textarea
                    className="ai-task-input"
                    placeholder="Example: Please reach out to Sarah and coordinate a time for us to speak, use my pre-purchase calendar for the appointment setter, then hit the complete button."
                    value={aiTask}
                    onChange={(e) => setAiTask(e.target.value)}
                    rows="4"
                    disabled={aiRunning}
                  />
                  <div className="ai-task-hint">
                    The AI agent will autonomously execute multi-step tasks including SMS conversations and calendar scheduling.
                  </div>
                </div>

                {/* AI Activity Log */}
                {aiActivity.length > 0 && (
                  <div className="ai-activity-log">
                    <h4>🔄 AI Agent Activity</h4>
                    {aiActivity.map((activity, index) => (
                      <div key={index} className="activity-item">
                        <span className="activity-icon">{activity.icon || '•'}</span>
                        <span className="activity-text">{activity.message}</span>
                        {activity.timestamp && (
                          <span className="activity-time">
                            {new Date(activity.timestamp).toLocaleTimeString()}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* AI Running Indicator */}
                {aiRunning && (
                  <div className="ai-running-indicator">
                    <div className="spinner"></div>
                    <span>AI Agent is working on your task...</span>
                  </div>
                )}

                {/* AI Complete Badge */}
                {aiComplete && (
                  <div className="ai-complete-badge">
                    ✅ Task completed successfully!
                  </div>
                )}
              </div>
            </>
          )}

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
            disabled={sending || aiRunning}
          >
            Cancel
          </button>
          {mode === 'manual' ? (
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
          ) : (
            <button
              className="btn-primary-sms"
              onClick={executeAITask}
              disabled={aiRunning || !aiTask.trim()}
            >
              {aiRunning ? (
                <>
                  <span className="spinner"></span>
                  AI Working...
                </>
              ) : (
                <>
                  <span>🤖</span>
                  Execute Task
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default SMSModal;
