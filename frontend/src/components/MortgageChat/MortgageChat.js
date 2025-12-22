/**
 * MortgageChat - Phase-Based Chat Component
 *
 * A chat widget for microsite integration with:
 * - Phase-aware conversations (1: Reassure, 2: Educate, 3: Personalize, 4: CTA)
 * - Intent detection and scoring display
 * - Click-to-call modal integration
 * - Responsive design with floating button
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './MortgageChat.css';

// API base URL - use environment variable or default
const API_BASE = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

// Phase display info
const PHASES = {
  1: { name: 'Getting Started', icon: '👋', color: '#4CAF50' },
  2: { name: 'Exploring Options', icon: '📚', color: '#2196F3' },
  3: { name: 'Personalizing', icon: '🎯', color: '#FF9800' },
  4: { name: 'Next Steps', icon: '🚀', color: '#9C27B0' },
};

// Generate unique visitor ID
const getVisitorId = () => {
  let visitorId = localStorage.getItem('mortgage_chat_visitor_id');
  if (!visitorId) {
    visitorId = 'visitor_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('mortgage_chat_visitor_id', visitorId);
  }
  return visitorId;
};

function MortgageChat({
  micrositeId,
  loanOfficerName,
  loanOfficerPhoto,
  primaryColor = '#1976D2',
  position = 'bottom-right', // bottom-right, bottom-left
}) {
  // State
  const [isOpen, setIsOpen] = useState(false);
  const [session, setSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // CTA/Call state
  const [showCallModal, setShowCallModal] = useState(false);
  const [callStatus, setCallStatus] = useState(null);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [callerName, setCallerName] = useState('');

  // Refs
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Create or resume session when chat opens
  useEffect(() => {
    if (isOpen && !session) {
      createSession();
    }
  }, [isOpen]);

  // Focus input when chat opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Create or resume chat session
  const createSession = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/api/v1/chat/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          visitor_id: getVisitorId(),
          microsite_id: micrositeId,
          source_url: window.location.href,
        }),
      });

      if (!response.ok) throw new Error('Failed to create session');

      const data = await response.json();
      setSession(data);

      // Add greeting message if provided
      if (data.greeting_message) {
        setMessages([{
          id: 'greeting',
          role: 'assistant',
          content: data.greeting_message,
          timestamp: new Date().toISOString(),
        }]);
      }
    } catch (err) {
      console.error('Session creation error:', err);
      setError('Unable to connect to chat. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Send message
  const sendMessage = async (e) => {
    e?.preventDefault();
    if (!inputValue.trim() || loading || !session) return;

    const userMessage = {
      id: `user_${Date.now()}`,
      role: 'user',
      content: inputValue,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/chat/sessions/${session.id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: inputValue }),
      });

      if (!response.ok) throw new Error('Failed to send message');

      const data = await response.json();

      // Add assistant message
      setMessages(prev => [...prev, {
        id: data.assistant_message.id,
        role: 'assistant',
        content: data.assistant_message.content,
        timestamp: data.assistant_message.createdAt,
        ctaPresented: data.assistant_message.ctaPresented,
      }]);

      // Update session state
      setSession(prev => ({
        ...prev,
        ...data.session_state,
      }));

    } catch (err) {
      console.error('Send message error:', err);
      setError('Message failed to send. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Handle CTA click
  const handleCTAClick = (ctaType) => {
    if (ctaType === 'call_now') {
      setShowCallModal(true);
    } else if (ctaType === 'schedule') {
      // Open scheduling modal or redirect
      window.open(session?.calendlyUrl || '#schedule', '_blank');
    } else if (ctaType === 'application') {
      window.location.href = '/apply';
    }
  };

  // Initiate click-to-call
  const initiateCall = async () => {
    if (!phoneNumber.trim()) return;

    try {
      setCallStatus('connecting');

      // Create call request
      const response = await fetch(`${API_BASE}/api/v1/chat/sessions/${session.id}/call-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone: phoneNumber,
          name: callerName,
          is_immediate: true,
        }),
      });

      if (!response.ok) throw new Error('Failed to initiate call');

      const data = await response.json();

      // Start polling for call status
      pollCallStatus(data.id);

    } catch (err) {
      console.error('Call initiation error:', err);
      setCallStatus('error');
    }
  };

  // Poll call status
  const pollCallStatus = async (callId) => {
    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/chat/call-requests/${callId}/status`);
        const data = await response.json();

        setCallStatus(data.status);

        if (['in_progress', 'completed', 'failed', 'cancelled', 'no_answer'].includes(data.status)) {
          return; // Stop polling
        }

        // Continue polling
        setTimeout(poll, 2000);
      } catch (err) {
        console.error('Status poll error:', err);
      }
    };

    poll();
  };

  // Render chat toggle button
  const renderToggleButton = () => (
    <button
      className={`mortgage-chat-toggle ${position}`}
      onClick={() => setIsOpen(!isOpen)}
      style={{ backgroundColor: primaryColor }}
      aria-label={isOpen ? 'Close chat' : 'Open chat'}
    >
      {isOpen ? (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      ) : (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      )}
      {!isOpen && session?.intent_score > 50 && (
        <span className="notification-badge">!</span>
      )}
    </button>
  );

  // Render phase indicator
  const renderPhaseIndicator = () => {
    if (!session) return null;

    const phase = PHASES[session.current_phase] || PHASES[1];

    return (
      <div className="phase-indicator">
        <div className="phase-progress">
          {[1, 2, 3, 4].map(p => (
            <div
              key={p}
              className={`phase-dot ${p <= session.current_phase ? 'active' : ''}`}
              style={{ backgroundColor: p <= session.current_phase ? phase.color : '#e0e0e0' }}
            />
          ))}
        </div>
        <span className="phase-label" style={{ color: phase.color }}>
          {phase.icon} {phase.name}
        </span>
      </div>
    );
  };

  // Render messages
  const renderMessages = () => (
    <div className="messages-container">
      {messages.map(msg => (
        <div key={msg.id} className={`message ${msg.role}`}>
          {msg.role === 'assistant' && loanOfficerPhoto && (
            <img src={loanOfficerPhoto} alt="" className="message-avatar" />
          )}
          <div className="message-content">
            <div className="message-text">{msg.content}</div>
            {msg.ctaPresented && msg.ctaPresented !== 'none' && (
              <div className="cta-buttons">
                {msg.ctaPresented === 'call_now' && (
                  <button
                    className="cta-button primary"
                    onClick={() => handleCTAClick('call_now')}
                    style={{ backgroundColor: primaryColor }}
                  >
                    📞 Call Now
                  </button>
                )}
                {msg.ctaPresented === 'schedule' && (
                  <button
                    className="cta-button primary"
                    onClick={() => handleCTAClick('schedule')}
                    style={{ backgroundColor: primaryColor }}
                  >
                    📅 Schedule Call
                  </button>
                )}
                {msg.ctaPresented === 'application' && (
                  <button
                    className="cta-button primary"
                    onClick={() => handleCTAClick('application')}
                    style={{ backgroundColor: primaryColor }}
                  >
                    📝 Start Application
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      ))}
      {loading && (
        <div className="message assistant">
          <div className="message-content">
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      )}
      <div ref={messagesEndRef} />
    </div>
  );

  // Render call modal
  const renderCallModal = () => {
    if (!showCallModal) return null;

    return (
      <div className="call-modal-overlay" onClick={() => setShowCallModal(false)}>
        <div className="call-modal" onClick={e => e.stopPropagation()}>
          <button className="close-modal" onClick={() => setShowCallModal(false)}>×</button>

          {callStatus === 'connecting' && (
            <div className="call-status connecting">
              <div className="call-spinner"></div>
              <h3>Connecting your call...</h3>
              <p>Please answer your phone when it rings</p>
            </div>
          )}

          {callStatus === 'in_progress' && (
            <div className="call-status in-progress">
              <div className="call-pulse"></div>
              <h3>Call Connected!</h3>
              <p>You're now speaking with {loanOfficerName || 'the loan officer'}</p>
            </div>
          )}

          {callStatus === 'completed' && (
            <div className="call-status completed">
              <div className="call-checkmark">✓</div>
              <h3>Call Completed</h3>
              <p>Thank you for connecting with us!</p>
              <button onClick={() => setShowCallModal(false)}>Close</button>
            </div>
          )}

          {callStatus === 'error' && (
            <div className="call-status error">
              <h3>Connection Failed</h3>
              <p>We couldn't connect your call. Please try again.</p>
              <button onClick={() => setCallStatus(null)}>Try Again</button>
            </div>
          )}

          {!callStatus && (
            <>
              <h3>Connect with {loanOfficerName || 'Us'}</h3>
              <p>Enter your phone number and we'll connect you right away!</p>

              <div className="call-form">
                <input
                  type="text"
                  placeholder="Your Name (optional)"
                  value={callerName}
                  onChange={e => setCallerName(e.target.value)}
                />
                <input
                  type="tel"
                  placeholder="Phone Number"
                  value={phoneNumber}
                  onChange={e => setPhoneNumber(e.target.value)}
                  required
                />
                <button
                  className="call-submit"
                  onClick={initiateCall}
                  disabled={!phoneNumber.trim()}
                  style={{ backgroundColor: primaryColor }}
                >
                  📞 Call Me Now
                </button>
              </div>

              <p className="call-note">
                We'll call your phone first, then connect you with {loanOfficerName || 'the loan officer'}.
              </p>
            </>
          )}
        </div>
      </div>
    );
  };

  // Render main chat widget
  const renderChatWidget = () => {
    if (!isOpen) return null;

    return (
      <div className={`mortgage-chat-widget ${position}`}>
        {/* Header */}
        <div className="chat-header" style={{ backgroundColor: primaryColor }}>
          <div className="header-info">
            {loanOfficerPhoto && (
              <img src={loanOfficerPhoto} alt="" className="header-avatar" />
            )}
            <div>
              <h4>{loanOfficerName || 'Mortgage Expert'}</h4>
              <span className="online-status">Online now</span>
            </div>
          </div>
          <button className="close-chat" onClick={() => setIsOpen(false)}>×</button>
        </div>

        {/* Phase Indicator */}
        {renderPhaseIndicator()}

        {/* Messages */}
        {renderMessages()}

        {/* Error Banner */}
        {error && (
          <div className="error-banner">
            {error}
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {/* Input */}
        <form className="chat-input-form" onSubmit={sendMessage}>
          <input
            ref={inputRef}
            type="text"
            placeholder="Type your message..."
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            disabled={loading || !session}
          />
          <button
            type="submit"
            disabled={loading || !inputValue.trim() || !session}
            style={{ backgroundColor: primaryColor }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </form>

        {/* Intent Score (debug - hidden in production) */}
        {process.env.NODE_ENV === 'development' && session && (
          <div className="debug-info">
            Intent: {session.intent_score}/100 | Urgency: {session.urgency}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="mortgage-chat-container">
      {renderToggleButton()}
      {renderChatWidget()}
      {renderCallModal()}
    </div>
  );
}

export default MortgageChat;
