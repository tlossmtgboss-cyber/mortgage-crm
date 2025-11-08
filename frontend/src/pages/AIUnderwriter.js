import React, { useState, useRef, useEffect } from 'react';
import './AIUnderwriter.css';

function AIUnderwriter() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I\'m your AI Underwriter assistant. I can answer any mortgage lending questions by searching current guidelines. Just ask me anything!',
      timestamp: new Date(),
    },
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || isLoading) return;

    const userMessage = {
      role: 'user',
      content: inputMessage,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/v1/ai-underwriter/ask', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: inputMessage }),
      });

      if (!response.ok) {
        throw new Error('Failed to get answer');
      }

      const data = await response.json();

      const assistantMessage = {
        role: 'assistant',
        content: data.answer,
        sources: data.sources || [],
        confidence: data.confidence,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error asking question:', error);
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error while searching for that information. Please try again.',
        timestamp: new Date(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const suggestedQuestions = [
    'What are the minimum credit score requirements for FHA loans?',
    'What is the maximum DTI ratio for conventional loans?',
    'What documentation is required for self-employed borrowers?',
    'What are the LTV limits for cash-out refinances?',
    'What are the reserve requirements for investment properties?',
  ];

  const handleSuggestedQuestion = (question) => {
    setInputMessage(question);
  };

  return (
    <div className="ai-underwriter-page">
      <div className="underwriter-header">
        <div className="header-content">
          <h1>AI Underwriter</h1>
          <p className="subtitle">Ask any mortgage lending question and get answers with sources</p>
        </div>
      </div>

      <div className="underwriter-container">
        <div className="messages-container">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`message ${message.role} ${message.isError ? 'error' : ''}`}
            >
              <div className="message-header">
                <span className="message-role">
                  {message.role === 'user' ? 'You' : '🤖 AI Underwriter'}
                </span>
                <span className="message-time">
                  {message.timestamp.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
              <div className="message-content">{message.content}</div>
              {message.sources && message.sources.length > 0 && (
                <div className="message-sources">
                  <div className="sources-header">📚 Sources:</div>
                  {message.sources.map((source, idx) => (
                    <a
                      key={idx}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="source-link"
                    >
                      <span className="source-icon">🔗</span>
                      <span className="source-title">{source.title || source.url}</span>
                    </a>
                  ))}
                </div>
              )}
              {message.confidence && (
                <div className="message-confidence">
                  Confidence: {Math.round(message.confidence * 100)}%
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="message assistant loading-message">
              <div className="message-header">
                <span className="message-role">🤖 AI Underwriter</span>
              </div>
              <div className="message-content">
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                Searching guidelines...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {messages.length === 1 && (
          <div className="suggested-questions">
            <h3>Suggested Questions:</h3>
            <div className="questions-grid">
              {suggestedQuestions.map((question, index) => (
                <button
                  key={index}
                  className="suggested-question-btn"
                  onClick={() => handleSuggestedQuestion(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="input-form">
          <div className="input-container">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="Ask a mortgage lending question..."
              className="message-input"
              disabled={isLoading}
            />
            <button type="submit" className="send-button" disabled={isLoading || !inputMessage.trim()}>
              {isLoading ? '...' : 'Ask'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default AIUnderwriter;
