import React, { useState, useEffect, useRef } from 'react';
import { aiAPI, conversationsAPI } from '../services/api';
import './Assistant.css';
import { toast } from '../utils/toast';

function Assistant() {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [context, setContext] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [isListening, setIsListening] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState({});
  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);
  const sessionIdRef = useRef(`assistant-${Date.now()}`);

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

  useEffect(() => {
    // Cleanup voice recognition on unmount
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadConversationHistory = async () => {
    try {
      const data = await conversationsAPI.getAll();
      // Convert to chat format
      const chatMessages = data.flatMap((conv, i) => [
        { id: `hist-u-${i}`, role: 'user', content: conv.message, timestamp: conv.created_at },
        { id: `hist-a-${i}`, role: 'assistant', content: conv.response, timestamp: conv.created_at }
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
      id: `msg-${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setLoading(true);

    try {
      // Use the full LangGraph orchestrator with 215 tools (email, tasks, pipeline, etc.)
      const response = await aiAPI.processCommand(message, context || {});

      const assistantMessage = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: response.response || response.explanation || '',
        timestamp: new Date().toISOString(),
        suggestions: response.follow_up_suggestions || [],
        intent: response.intent,
        agentUsed: response.agent_used,
        actionsExecuted: response.actions_executed,
      };

      setMessages(prev => [...prev, assistantMessage]);

      // Save conversation (orchestrator saves server-side, but also save to legacy store)
      try {
        await conversationsAPI.create({
          message: message,
          response: response.response || response.explanation || '',
          context: context
        });
      } catch (saveErr) {
        console.warn('Failed to save conversation to legacy store:', saveErr);
      }

    } catch (error) {
      console.error('Failed to send message:', error);
      const errorMessage = {
        id: `msg-err-${Date.now()}`,
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
    setMessages([]);
    setContext(null);
  };

  const handleVoiceInput = () => {
    // Check if browser supports Web Speech API
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      toast.error('Sorry, your browser does not support speech recognition. Please try Chrome or Edge.');
      return;
    }

    // If already listening, stop
    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
      return;
    }

    // Create new recognition instance
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
      console.log('Voice recognition started. Speak now...');
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      console.log('Voice input received:', transcript);
      setInputMessage(transcript);
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      if (event.error === 'no-speech') {
        toast.error('No speech detected. Please try again.');
      } else if (event.error !== 'aborted') {
        toast.error(`Error occurred: ${event.error}`);
      }
    };

    recognition.onend = () => {
      setIsListening(false);
      console.log('Voice recognition ended');
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const handleFeedback = async (msg, rating) => {
    if (feedbackGiven[msg.id]) return;

    setFeedbackGiven(prev => ({ ...prev, [msg.id]: rating }));

    // Find the preceding user message for context
    const msgIndex = messages.findIndex(m => m.id === msg.id);
    const precedingUserMsg = messages.slice(0, msgIndex).reverse().find(m => m.role === 'user');

    try {
      await aiAPI.submitInlineFeedback({
        sessionId: sessionIdRef.current,
        messageId: String(msg.id),
        rating,
        userQuestion: precedingUserMsg?.content,
        aiResponse: msg.content,
      });
    } catch (error) {
      console.error('Failed to submit feedback:', error);
      setFeedbackGiven(prev => {
        const updated = { ...prev };
        delete updated[msg.id];
        return updated;
      });
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
                  <div key={msg.id || index} className={`message message-${msg.role}`}>
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
                      <div className="message-meta-row">
                        <span className="message-time">
                          {new Date(msg.timestamp).toLocaleTimeString()}
                        </span>
                        {msg.role === 'assistant' && msg.id && (
                          <span className="message-feedback-row">
                            <button
                              className={`feedback-btn${feedbackGiven[msg.id] === 'positive' ? ' active' : ''}`}
                              onClick={() => handleFeedback(msg, 'positive')}
                              disabled={!!feedbackGiven[msg.id]}
                              title="Helpful response"
                              aria-label="Thumbs up"
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
                            </button>
                            <button
                              className={`feedback-btn${feedbackGiven[msg.id] === 'negative' ? ' active negative' : ''}`}
                              onClick={() => handleFeedback(msg, 'negative')}
                              disabled={!!feedbackGiven[msg.id]}
                              title="Unhelpful response"
                              aria-label="Thumbs down"
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/><path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>
                            </button>
                          </span>
                        )}
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
              placeholder={isListening ? '🎤 Listening... Speak now!' : 'Ask me anything about your mortgage business...'}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              rows="3"
              disabled={loading}
            />
            <div className="input-actions">
              <button
                type="button"
                className={`btn-microphone ${isListening ? 'listening' : ''}`}
                onClick={handleVoiceInput}
                disabled={loading}
                title={isListening ? 'Stop listening' : 'Click to speak'}
              >
                {isListening ? '🔴 Listening' : '🎤 Speak'}
              </button>
              <button
                className="btn-send"
                onClick={() => handleSendMessage()}
                disabled={loading || !inputMessage.trim()}
              >
                {loading ? '⏳ Thinking...' : '📤 Send'}
              </button>
            </div>
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
