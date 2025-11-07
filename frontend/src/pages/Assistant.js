import React, { useState, useEffect, useRef } from 'react';
import { aiAPI, conversationsAPI } from '../services/api';
import './Assistant.css';

function Assistant() {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [context, setContext] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const messagesEndRef = useRef(null);

  const quickActions = [
    { icon: '📊', text: 'Show my pipeline overview', action: 'pipeline_overview' },
    { icon: '✅', text: 'What tasks need my attention?', action: 'urgent_tasks' },
    { icon: '📈', text: 'Analyze my conversion rates', action: 'conversion_analysis' },
    { icon: '🎯', text: 'Find hot leads to contact', action: 'hot_leads' },
    { icon: '📅', text: 'What\'s on my calendar today?', action: 'today_calendar' },
    { icon: '💰', text: 'Calculate my month\'s pipeline value', action: 'pipeline_value' },
  ];

  useEffect(() => {
    loadConversationHistory();
    generateSuggestions();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadConversationHistory = async () => {
    try {
      const data = await conversationsAPI.getAll();
      // Convert to chat format
      const chatMessages = data.flatMap(conv => [
        { role: 'user', content: conv.message, timestamp: conv.created_at },
        { role: 'assistant', content: conv.response, timestamp: conv.created_at }
      ]);
      setMessages(chatMessages);
    } catch (error) {
      console.error('Failed to load conversation history:', error);
    }
  };

  const generateSuggestions = async () => {
    try {
      const response = await aiAPI.getSuggestions();
      setSuggestions(response.suggestions || []);
    } catch (error) {
      console.error('Failed to generate suggestions:', error);
    }
  };

  const handleSendMessage = async (message = inputMessage) => {
    if (!message.trim()) return;

    const userMessage = {
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setLoading(true);

    try {
      const response = await aiAPI.chat({ message, context });
      
      const assistantMessage = {
        role: 'assistant',
        content: response.response || response.message,
        timestamp: new Date().toISOString(),
        suggestions: response.suggestions
      };

      setMessages(prev => [...prev, assistantMessage]);

      // Update context if provided
      if (response.context) {
        setContext(response.context);
      }

      // Save conversation
      await conversationsAPI.create({
        message: message,
        response: response.response || response.message,
        context: context
      });

    } catch (error) {
      console.error('Failed to send message:', error);
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date().toISOString(),
        isError: true
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickAction = (action) => {
    const actionMessages = {
      pipeline_overview: 'Show me a comprehensive overview of my entire pipeline',
      urgent_tasks: 'What tasks need my immediate attention today?',
      conversion_analysis: 'Analyze my lead-to-close conversion rates and suggest improvements',
      hot_leads: 'Show me the hottest leads I should contact right now',
      today_calendar: 'What appointments and meetings do I have scheduled for today?',
      pipeline_value: 'Calculate the total dollar value of my current pipeline'
    };

    handleSendMessage(actionMessages[action] || action.text);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const clearConversation = () => {
    if (window.confirm('Clear all conversation history?')) {
      setMessages([]);
      setContext(null);
    }
  };

  return (
    <div className="assistant-page">
      <div className="assistant-header">
        <div className="header-content">
          <h1>🤖 AI Assistant</h1>
          <p>Your intelligent mortgage CRM copilot</p>
        </div>
        <button className="btn-clear" onClick={clearConversation}>
          Clear History
        </button>
      </div>

      <div className="assistant-container">
        {/* Quick Actions */}
        <div className="quick-actions">
          <h3>Quick Actions</h3>
          <div className="quick-actions-grid">
            {quickActions.map((action, index) => (
              <button
                key={index}
                className="quick-action-btn"
                onClick={() => handleQuickAction(action.action)}
              >
                <span className="action-icon">{action.icon}</span>
                <span className="action-text">{action.text}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Chat Messages */}
        <div className="chat-container">
          <div className="messages-area">
            {messages.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">🤖</div>
                <h2>Welcome to Your AI Assistant!</h2>
                <p>I can help you with:</p>
                <ul>
                  <li>Analyzing your pipeline and performance metrics</li>
                  <li>Finding and prioritizing leads to contact</li>
                  <li>Managing tasks and appointments</li>
                  <li>Providing insights on loan progress</li>
                  <li>Answering questions about your clients</li>
                  <li>Suggesting next best actions</li>
                </ul>
                <p>Click a quick action above or type a question below to get started!</p>
              </div>
            ) : (
              <>
                {messages.map((msg, index) => (
                  <div key={index} className={`message message-${msg.role}`}>
                    <div className="message-avatar">
                      {msg.role === 'user' ? '👤' : '🤖'}
                    </div>
                    <div className="message-content">
                      <div className="message-text">{msg.content}</div>
                      {msg.suggestions && msg.suggestions.length > 0 && (
                        <div className="message-suggestions">
                          <p className="suggestions-label">Suggested actions:</p>
                          {msg.suggestions.map((suggestion, idx) => (
                            <button
                              key={idx}
                              className="suggestion-chip"
                              onClick={() => handleSendMessage(suggestion)}
                            >
                              {suggestion}
                            </button>
                          ))}
                        </div>
                      )}
                      <div className="message-time">
                        {new Date(msg.timestamp).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="message message-assistant">
                    <div className="message-avatar">🤖</div>
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
              </>
            )}
          </div>

          {/* Input Area */}
          <div className="input-area">
            <textarea
              className="message-input"
              placeholder="Ask me anything about your mortgage business..."
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              rows="3"
              disabled={loading}
            />
            <button
              className="btn-send"
              onClick={() => handleSendMessage()}
              disabled={loading || !inputMessage.trim()}
            >
              {loading ? '⏳' : '📤'} Send
            </button>
          </div>
        </div>

        {/* AI Insights Panel */}
        {suggestions.length > 0 && (
          <div className="insights-panel">
            <h3>💡 AI Insights</h3>
            <div className="insights-list">
              {suggestions.map((suggestion, index) => (
                <div key={index} className="insight-card">
                  <div className="insight-icon">💡</div>
                  <div className="insight-content">
                    <p>{suggestion}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Assistant;
