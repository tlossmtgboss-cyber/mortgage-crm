/**
 * AriaChatPanel - Slide-over AI chat panel
 *
 * Sits alongside the application form so borrowers can ask Aria questions
 * without losing their place. Slides in from the right edge.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import './AriaChatPanel.css';

const SUGGESTIONS = [
  'What documents do I need?',
  'How much can I afford?',
  'What is PMI?',
  'Explain closing costs',
];

const AriaChatPanel = ({ isOpen, onClose, applicationData, applicationType }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const apiBase = process.env.REACT_APP_API_URL || '';

  // Auto-focus input when panel opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      // Small delay so the slide animation has started
      const timer = setTimeout(() => inputRef.current?.focus(), 150);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Escape key closes panel
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Auto-scroll to bottom on new messages or typing indicator
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const buildContext = useCallback(() => {
    const summary = {};
    if (applicationData) {
      summary.has_coborrower = !!applicationData.has_coborrower;
      summary.property_type = applicationData.property_type || undefined;
      summary.loan_purpose = applicationType || 'purchase';
    }
    return {
      page: 'application',
      application_type: applicationType || 'purchase',
      form_data_summary: summary,
    };
  }, [applicationData, applicationType]);

  const sendMessage = useCallback(async (text) => {
    if (!text.trim()) return;

    const userMessage = { role: 'user', content: text.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);

    try {
      const res = await fetch(`${apiBase}/api/v1/portal/ai-assistant/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          context: buildContext(),
        }),
      });

      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.response || 'I wasn\'t able to generate a response. Please try again.',
          sources: data.sources || [],
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'I\'m having trouble connecting right now. Please try again in a moment.',
          sources: [],
          isError: true,
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  }, [apiBase, buildContext]);

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleSuggestionClick = (suggestion) => {
    sendMessage(suggestion);
  };

  const showSuggestions = messages.length === 0;

  return (
    <div className={`aria-chat-panel ${isOpen ? 'open' : ''}`} role="complementary" aria-label="Aria AI Chat">
      {/* Backdrop for mobile */}
      {isOpen && <div className="aria-chat-backdrop" onClick={onClose} />}

      <div className="aria-chat-container">
        {/* Header */}
        <div className="aria-chat-header">
          <div className="aria-chat-header-left">
            <div className="aria-avatar">A</div>
            <div className="aria-header-info">
              <span className="aria-name">Aria</span>
              <span className="aria-status">AI Assistant</span>
            </div>
          </div>
          <button
            type="button"
            className="aria-chat-close"
            onClick={onClose}
            aria-label="Close chat"
          >
            &times;
          </button>
        </div>

        {/* Messages */}
        <div className="aria-chat-messages">
          {showSuggestions && (
            <div className="aria-welcome">
              <p className="aria-welcome-text">
                Hi! I'm Aria, your AI assistant. Ask me anything about your mortgage application.
              </p>
              <div className="aria-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="aria-suggestion-chip"
                    onClick={() => handleSuggestionClick(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`aria-message aria-message-${msg.role}`}>
              <div className={`aria-bubble aria-bubble-${msg.role}${msg.isError ? ' aria-bubble-error' : ''}`}>
                {msg.content}
              </div>
              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <div className="aria-sources">
                  {msg.sources.map((src, j) => (
                    <span key={j} className="aria-source-chip">{src}</span>
                  ))}
                </div>
              )}
            </div>
          ))}

          {isTyping && (
            <div className="aria-message aria-message-assistant">
              <div className="aria-typing-indicator">
                <span className="aria-dot" />
                <span className="aria-dot" />
                <span className="aria-dot" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <form className="aria-chat-input-area" onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            className="aria-chat-input"
            placeholder="Ask Aria a question..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isTyping}
          />
          <button
            type="submit"
            className="aria-send-btn"
            disabled={!input.trim() || isTyping}
            aria-label="Send message"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
};

export default AriaChatPanel;
