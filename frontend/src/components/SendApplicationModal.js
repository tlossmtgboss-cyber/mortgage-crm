import React, { useState, useMemo } from 'react';
import { outreachAPI } from '../services/api';
import { toast } from '../utils/toast';
import './SendApplicationModal.css';

const TEMPLATE_STYLES = ['Professional', 'Friendly', 'Concise'];

function buildTemplates(firstName, applicationLink, loName) {
  const link = applicationLink || '[application link]';
  return {
    email: [
      // Professional
      {
        subject: 'Complete Your Mortgage Application',
        body: `Hi ${firstName},\n\nI've prepared a secure application link for your mortgage. You can complete it at your convenience — your progress will be saved automatically.\n\n${link}\n\nPlease don't hesitate to reach out if you have any questions along the way.\n\nBest regards,\n${loName}`,
      },
      // Friendly
      {
        subject: `${firstName}, Your Application Is Ready!`,
        body: `Hi ${firstName}!\n\nGreat news — your mortgage application is ready to go! Just click the link below to get started:\n\n${link}\n\nIt only takes a few minutes, and everything saves as you go. I'm here if you need any help!\n\nTalk soon,\n${loName}`,
      },
      // Concise
      {
        subject: 'Your Mortgage Application Link',
        body: `Hi ${firstName},\n\nHere is your secure mortgage application link:\n\n${link}\n\nLet me know if you have questions.\n\n${loName}`,
      },
    ],
    sms: [
      // Professional
      `Hi ${firstName}, I've created a secure mortgage application for you. Complete it here at your convenience: ${link} — ${loName}`,
      // Friendly
      `Hey ${firstName}! Your mortgage app is ready. Tap here to get started: ${link} Let me know if you need anything! - ${loName}`,
      // Concise
      `Hi ${firstName}, here's your mortgage application link: ${link} - ${loName}`,
    ],
  };
}

function SendApplicationModal({ lead, applicationLink, onClose, onSent }) {
  const firstName = lead?.first_name || lead?.name?.split(' ')[0] || 'there';
  const loName = 'Your Loan Officer';
  const appUrl = applicationLink?.url || '';

  const templates = useMemo(
    () => buildTemplates(firstName, appUrl, loName),
    [firstName, appUrl, loName]
  );

  const [sendVia, setSendVia] = useState({
    email: !!lead?.email,
    sms: !!lead?.phone,
  });
  const [templateIndex, setTemplateIndex] = useState(0);
  const [emailSubject, setEmailSubject] = useState(templates.email[0].subject);
  const [emailBody, setEmailBody] = useState(templates.email[0].body);
  const [smsMessage, setSmsMessage] = useState(templates.sms[0]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  const hasEmail = !!lead?.email;
  const hasPhone = !!lead?.phone;
  const canSend = (sendVia.email && hasEmail) || (sendVia.sms && hasPhone);

  const smsCharCount = smsMessage.length;
  const smsSegments = Math.max(1, Math.ceil(smsCharCount / 160));

  const handleToggleChannel = (channel) => {
    if (channel === 'email' && !hasEmail) return;
    if (channel === 'sms' && !hasPhone) return;
    setSendVia((prev) => ({ ...prev, [channel]: !prev[channel] }));
  };

  const handleRegenerate = () => {
    const nextIndex = (templateIndex + 1) % TEMPLATE_STYLES.length;
    setTemplateIndex(nextIndex);
    setEmailSubject(templates.email[nextIndex].subject);
    setEmailBody(templates.email[nextIndex].body);
    setSmsMessage(templates.sms[nextIndex]);
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(appUrl);
      toast.success('Link copied!');
    } catch {
      const ta = document.createElement('textarea');
      ta.value = appUrl;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      toast.success('Link copied!');
    }
  };

  const handleSend = async () => {
    setSending(true);
    setError(null);

    const promises = [];

    if (sendVia.email && hasEmail) {
      promises.push(
        outreachAPI.sendEmail(lead.email, emailSubject, emailBody, lead.id)
      );
    }
    if (sendVia.sms && hasPhone) {
      promises.push(
        outreachAPI.sendSMS(lead.phone, smsMessage, lead.id)
      );
    }

    try {
      await Promise.all(promises);
      const channels = [];
      if (sendVia.email && hasEmail) channels.push('email');
      if (sendVia.sms && hasPhone) channels.push('SMS');
      toast.success(`Application sent via ${channels.join(' and ')}!`);
      if (onSent) onSent();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to send';
      setError(msg);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="send-app-overlay" onClick={onClose}>
      <div className="send-app-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="send-app-header">
          <h2>
            Send Application to {firstName}
          </h2>
          <button className="send-app-close" onClick={onClose}>
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="send-app-body">
          {/* Application link */}
          <div className="send-app-link-row">
            <span className="send-app-link-label">Application Link:</span>
            <input
              type="text"
              className="send-app-link-input"
              value={appUrl}
              readOnly
            />
            <button className="send-app-copy-btn" onClick={handleCopyLink}>
              Copy
            </button>
          </div>

          {/* Channel toggles */}
          <div className="send-app-channels">
            <span className="send-app-channels-label">Send via:</span>
            <button
              className={`send-app-channel-pill ${sendVia.email ? 'active' : ''}`}
              onClick={() => handleToggleChannel('email')}
              disabled={!hasEmail}
              title={!hasEmail ? 'No email on file' : ''}
            >
              <span className="pill-check">{sendVia.email ? '\u2713' : ''}</span>
              Email
            </button>
            <button
              className={`send-app-channel-pill ${sendVia.sms ? 'active' : ''}`}
              onClick={() => handleToggleChannel('sms')}
              disabled={!hasPhone}
              title={!hasPhone ? 'No phone on file' : ''}
            >
              <span className="pill-check">{sendVia.sms ? '\u2713' : ''}</span>
              SMS
            </button>
          </div>

          {/* Email section */}
          {sendVia.email && (
            <>
              <div className="send-app-section-header">
                <span className="send-app-section-label">Email Subject</span>
              </div>
              <input
                type="text"
                className="send-app-subject-input"
                value={emailSubject}
                onChange={(e) => setEmailSubject(e.target.value)}
              />

              <div className="send-app-section-header">
                <span className="send-app-section-label">
                  Email Message
                  <span className="send-app-template-badge">
                    ({TEMPLATE_STYLES[templateIndex]})
                  </span>
                </span>
                <button
                  className="send-app-regenerate-btn"
                  onClick={handleRegenerate}
                >
                  Regenerate
                </button>
              </div>
              <textarea
                className="send-app-textarea"
                value={emailBody}
                onChange={(e) => setEmailBody(e.target.value)}
                rows={8}
              />
            </>
          )}

          {/* SMS section */}
          {sendVia.sms && (
            <>
              <div className="send-app-section-header">
                <span className="send-app-section-label">
                  SMS Message
                  {!sendVia.email && (
                    <span className="send-app-template-badge">
                      ({TEMPLATE_STYLES[templateIndex]})
                    </span>
                  )}
                </span>
                {!sendVia.email && (
                  <button
                    className="send-app-regenerate-btn"
                    onClick={handleRegenerate}
                  >
                    Regenerate
                  </button>
                )}
              </div>
              <textarea
                className="send-app-textarea sms-textarea"
                value={smsMessage}
                onChange={(e) => setSmsMessage(e.target.value)}
                rows={3}
              />
              <div className="send-app-sms-meta">
                {smsCharCount}/160 &middot; {smsSegments} SMS segment{smsSegments !== 1 ? 's' : ''}
              </div>
            </>
          )}

          {/* Error */}
          {error && <div className="send-app-error">{error}</div>}
        </div>

        {/* Footer */}
        <div className="send-app-footer">
          <button
            className="send-app-cancel-btn"
            onClick={onClose}
            disabled={sending}
          >
            Cancel
          </button>
          <button
            className="send-app-send-btn"
            onClick={handleSend}
            disabled={sending || !canSend}
          >
            {sending ? (
              <>
                <span className="send-spinner" />
                Sending...
              </>
            ) : (
              'Send'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SendApplicationModal;
