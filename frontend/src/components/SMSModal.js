import React, { useState, useEffect } from 'react';
import api, { aiAPI, borrowerApplicationAPI } from '../services/api';
import { toast } from '../utils/toast';
import './SMSModal.css';

const APP_BASE = process.env.REACT_APP_BASE_URL || 'https://app.perenniaai.com';

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

  // Calendar/booking link state
  const [bookingLinks, setBookingLinks] = useState([]);
  const [showCalendarPicker, setShowCalendarPicker] = useState(false);
  const [calendarAdded, setCalendarAdded] = useState(false);

  // Application link state
  const [appLinkAdded, setAppLinkAdded] = useState(false);
  const [appLinkLoading, setAppLinkLoading] = useState(false);

  // TCPA consent state
  const [tcpaStatus, setTcpaStatus] = useState(null); // null = loading, object = result
  const [tcpaLoading, setTcpaLoading] = useState(false);

  // Check TCPA consent status when modal opens
  useEffect(() => {
    if (isOpen && lead?.phone) {
      const checkTcpaConsent = async () => {
        setTcpaLoading(true);
        setTcpaStatus(null);
        try {
          const response = await api.get(
            `/api/v1/compliance/tcpa/consent/${encodeURIComponent(lead.phone)}`
          );
          setTcpaStatus(response.data);
          if (response.data && !response.data.sms_permitted) {
            toast.warning(
              'TCPA consent not on file for this contact. SMS sending is blocked.'
            );
          }
        } catch (err) {
          // If the endpoint returns 404 or fails, treat as no consent
          console.warn('TCPA consent check failed:', err);
          setTcpaStatus({
            has_active_consent: false,
            sms_permitted: false,
            message: 'Unable to verify TCPA consent status.',
          });
        } finally {
          setTcpaLoading(false);
        }
      };
      checkTcpaConsent();
    } else if (!isOpen) {
      setTcpaStatus(null);
    }
  }, [isOpen, lead?.phone]);

  // Derived: is SMS blocked by TCPA?
  const smsBlocked = tcpaStatus !== null && !tcpaStatus.sms_permitted;

  // Fetch booking links when modal opens
  useEffect(() => {
    if (isOpen) {
      const fetchBookingLinks = async () => {
        try {
          const token = localStorage.getItem('token');
          const response = await api.get('/api/v1/scheduler/booking-links');
          setBookingLinks(response.data?.booking_links || []);
        } catch (err) {
          console.warn('Failed to fetch booking links:', err);
        }
      };
      fetchBookingLinks();
      setCalendarAdded(false);
      setAppLinkAdded(false);
    }
  }, [isOpen]);

  const insertCalendarLink = (link) => {
    const bookingUrl = `${APP_BASE}/book/${link.slug}`;
    const calendarText = `\nSchedule a time to talk: ${bookingUrl}`;
    setMessage(prev => prev + calendarText);
    setCalendarAdded(true);
    setShowCalendarPicker(false);
  };

  const handleCalendarClick = () => {
    if (bookingLinks.length === 0) {
      setResult({ status: 'error', message: 'No booking links found. Create one in Smart Scheduler first.' });
      return;
    }
    if (bookingLinks.length === 1) {
      insertCalendarLink(bookingLinks[0]);
    } else {
      setShowCalendarPicker(prev => !prev);
    }
  };

  const handleAppLinkClick = async () => {
    if (!lead?.id) return;
    setAppLinkLoading(true);
    try {
      const response = await borrowerApplicationAPI.createForLead(lead.id, {
        send_email: false,
        send_sms: false,
      });
      const appUrl = `${window.location.origin}/apply/${response.public_token}`;
      const appText = `\nComplete your mortgage application here: ${appUrl}`;
      setMessage(prev => prev + appText);
      setAppLinkAdded(true);
    } catch (err) {
      setResult({ status: 'error', message: 'Failed to create application link. Please try again.' });
    } finally {
      setAppLinkLoading(false);
    }
  };

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

    // Block send if TCPA consent is not active
    if (smsBlocked) {
      toast.error('Cannot send SMS -- TCPA consent is not on file for this contact.');
      setResult({
        status: 'error',
        message: 'TCPA consent required. Obtain express written consent before sending SMS.',
      });
      return;
    }

    setSending(true);
    setResult(null);

    try {
      const response = await api.post('/api/v1/sms-intelligence/send', {
        to_phone: lead.phone,
        message: message,
        lead_id: lead.id
      });

      setResult({
        status: 'success',
        message: 'SMS sent successfully!',
        details: response.data
      });
      setMessage('');
      setUseTemplate('');

      // Close modal after 2 seconds
      setTimeout(() => {
        onClose();
      }, 2000);
    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.message || 'Failed to send SMS';
      setResult({
        status: 'error',
        message: errorMsg
      });
    } finally {
      setSending(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && e.ctrlKey && !smsBlocked) {
      sendSMS();
    }
  };

  const executeAITask = async () => {
    if (!aiTask.trim()) {
      setResult({ status: 'error', message: 'Please enter a task for the AI agent' });
      return;
    }

    // Block AI agent if TCPA consent is not active
    if (smsBlocked) {
      toast.error('Cannot execute SMS task -- TCPA consent is not on file for this contact.');
      setResult({
        status: 'error',
        message: 'TCPA consent required. Obtain express written consent before sending SMS.',
      });
      return;
    }

    setAiRunning(true);
    setAiActivity([]);
    setAiComplete(false);
    setResult(null);

    try {
      // Call autonomous AI task endpoint
      const response = await api.post('/api/v1/ai/autonomous-task', {
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
      });

      // Show activity log from AI
      if (response.data.activity_log) {
        setAiActivity(response.data.activity_log);
      }

      setAiComplete(true);
      setResult({
        status: 'success',
        message: 'AI Agent completed the task successfully!',
        details: response.data
      });

      // Close modal after 3 seconds
      setTimeout(() => {
        onClose();
      }, 3000);
    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.message || 'AI Agent failed to complete the task';
      setResult({
        status: 'error',
        message: errorMsg
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
          {/* TCPA Consent Status Banner */}
          {tcpaLoading && (
            <div className="tcpa-banner tcpa-loading">
              <span className="tcpa-icon">
                <span className="spinner" style={{ width: 14, height: 14 }}></span>
              </span>
              <span>Checking TCPA consent status...</span>
            </div>
          )}
          {!tcpaLoading && tcpaStatus && !tcpaStatus.sms_permitted && (
            <div className="tcpa-banner tcpa-blocked">
              <span className="tcpa-icon">&#x26D4;</span>
              <div className="tcpa-text">
                <strong>SMS Blocked -- No TCPA Consent</strong>
                <p>{tcpaStatus.message || 'No active TCPA consent on file for this phone number. Obtain express written consent before sending SMS.'}</p>
              </div>
            </div>
          )}
          {!tcpaLoading && tcpaStatus && tcpaStatus.sms_permitted && (
            <div className="tcpa-banner tcpa-permitted">
              <span className="tcpa-icon">&#x2705;</span>
              <span>TCPA consent active ({tcpaStatus.consent_type || 'verified'})</span>
            </div>
          )}

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
                <div className="sms-toolbar">
                  <button
                    type="button"
                    className={`btn-calendar-link ${calendarAdded ? 'added' : ''}`}
                    onClick={handleCalendarClick}
                    disabled={sending || calendarAdded}
                    title="Insert calendar booking link"
                  >
                    {calendarAdded ? '📅 Calendar link added' : '📅 Add Calendar Link'}
                  </button>
                  {showCalendarPicker && bookingLinks.length > 1 && (
                    <div className="calendar-picker-dropdown">
                      {bookingLinks.map(link => (
                        <button
                          key={link.id}
                          className="calendar-picker-item"
                          onClick={() => insertCalendarLink(link)}
                        >
                          {link.name || link.slug}
                        </button>
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    className={`btn-calendar-link ${appLinkAdded ? 'added' : ''}`}
                    onClick={handleAppLinkClick}
                    disabled={sending || appLinkAdded || appLinkLoading}
                    title="Generate and insert application link"
                  >
                    {appLinkLoading ? 'Creating...' : appLinkAdded ? '📋 App link added' : '📋 Add Application Link'}
                  </button>
                </div>
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
              className={`btn-primary-sms ${smsBlocked ? 'btn-blocked' : ''}`}
              onClick={sendSMS}
              disabled={sending || !message.trim() || smsBlocked || tcpaLoading}
              title={smsBlocked ? 'SMS blocked -- no TCPA consent on file' : ''}
            >
              {sending ? (
                <>
                  <span className="spinner"></span>
                  Sending...
                </>
              ) : smsBlocked ? (
                <>
                  <span>&#x26D4;</span>
                  Consent Required
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
              className={`btn-primary-sms ${smsBlocked ? 'btn-blocked' : ''}`}
              onClick={executeAITask}
              disabled={aiRunning || !aiTask.trim() || smsBlocked || tcpaLoading}
              title={smsBlocked ? 'SMS blocked -- no TCPA consent on file' : ''}
            >
              {aiRunning ? (
                <>
                  <span className="spinner"></span>
                  AI Working...
                </>
              ) : smsBlocked ? (
                <>
                  <span>&#x26D4;</span>
                  Consent Required
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
