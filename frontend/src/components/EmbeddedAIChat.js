/**
 * EmbeddedAIChat - Claude-style Embedded Chat Component
 *
 * A full-width, inline chat interface for mortgage questions
 * Styled similar to Claude AI's clean, modern interface
 */

import React, { useState, useRef, useEffect } from 'react';
import './EmbeddedAIChat.css';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const EmbeddedAIChat = ({ userSlug, loName, themeConfig = {} }) => {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const textareaRef = useRef(null);

  const primaryColor = themeConfig.primaryColor || '#2d5a27';

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  }, [inputValue]);

  const sendMessage = async (messageText = inputValue) => {
    if (!messageText.trim() || isLoading) return;

    const userMessage = messageText.trim();
    setInputValue('');

    // Add user message
    setMessages(prev => [...prev, {
      id: `user-${Date.now()}`,
      role: 'user',
      content: userMessage,
    }]);
    setIsLoading(true);

    try {
      const conversationHistory = messages.map(m => ({
        role: m.role,
        content: m.content
      }));

      const response = await fetch(`${API_BASE}/api/v1/public/themes/chat/${userSlug}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          session_id: sessionId,
          conversation_history: conversationHistory
        })
      });

      const data = await response.json();

      if (data.session_id) {
        setSessionId(data.session_id);
      }

      setMessages(prev => [...prev, {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.response || "I'm sorry, I couldn't process that. Please try again.",
      }]);

    } catch (error) {
      console.error('Error sending message:', error);
      setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: "I'm having trouble connecting. Please try again in a moment.",
        isError: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const suggestedQuestions = [
    "What mortgage options do I have?",
    "How much home can I afford?",
    "What are current interest rates?",
    "What documents do I need?",
    "How long does the process take?",
    "What's the difference between FHA and conventional?"
  ];

  return (
    <section className="embedded-ai-chat" style={{ '--chat-primary': primaryColor }}>
      <div className="chat-container">
        {/* Header */}
        <div className="chat-header">
          <div className="chat-header-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <div className="chat-header-text">
            <h2>Ask Me Anything About Mortgages</h2>
            <p>Get instant answers to your home financing questions</p>
          </div>
        </div>

        {/* Messages Area */}
        <div className="chat-messages-area">
          {messages.length === 0 ? (
            <div className="chat-welcome">
              <div className="welcome-icon">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
                </svg>
              </div>
              <h3>Hi! I'm your AI mortgage assistant.</h3>
              <p>Ask me anything about home loans, rates, qualifications, or the mortgage process. I'm here to help!</p>

              <div className="suggested-questions">
                <p className="suggestions-label">Try asking:</p>
                <div className="suggestions-grid">
                  {suggestedQuestions.map((question, idx) => (
                    <button
                      key={idx}
                      className="suggestion-btn"
                      onClick={() => sendMessage(question)}
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="messages-list">
              {messages.map((message) => (
                <div key={message.id} className={`message ${message.role}`}>
                  <div className="message-avatar">
                    {message.role === 'assistant' ? (
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                      </svg>
                    )}
                  </div>
                  <div className={`message-content ${message.isError ? 'error' : ''}`}>
                    <p>{message.content}</p>
                  </div>
                </div>
              ))}

              {isLoading && (
                <div className="message assistant">
                  <div className="message-avatar">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                    </svg>
                  </div>
                  <div className="message-content typing">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="chat-input-area">
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about mortgages..."
              rows="1"
              disabled={isLoading}
            />
            <button
              className="send-btn"
              onClick={() => sendMessage()}
              disabled={!inputValue.trim() || isLoading}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
              </svg>
            </button>
          </div>
          <p className="input-hint">Press Enter to send, Shift+Enter for new line</p>
        </div>
      </div>
    </section>
  );
};

export default EmbeddedAIChat;
