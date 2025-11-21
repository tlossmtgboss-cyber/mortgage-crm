import React, { useState, useEffect, useRef } from 'react';
import { aiAPI } from '../services/api';
import './SmartAIChat.css';

function SmartAIChat({ leadId, loanId, context = {} }) {
  // Don't render on login/public pages or standalone AI page
  const isAuthPage = ['/', '/login', '/register', '/verify-email', '/verify-email-sent', '/onboarding', '/ai'].includes(window.location.pathname);

  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: 'Hello! I\'m your AI assistant with memory. I remember our past conversations and can provide context-aware responses. How can I help you today?',
      timestamp: new Date().toISOString(),
      contextUsed: false,
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [memoryStats, setMemoryStats] = useState(null);
  const [showStats, setShowStats] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);
  const textareaRef = useRef(null);

  // Auto-resize textarea
  const autoResize = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    }
  };

  useEffect(() => {
    // Only load memory stats if authenticated
    if (localStorage.getItem('token')) {
      loadMemoryStats();
    }

    // Listen for voice commands
    const handleVoiceCommand = (event) => {
      const { transcript } = event.detail;
      if (transcript) {
        console.log('Voice command received in SmartAIChat:', transcript);
        setInputValue(transcript);
        // Auto-submit the voice command after a brief delay
        setTimeout(() => {
          const form = document.querySelector('.smart-ai-input');
          if (form) {
            form.requestSubmit(); // This properly triggers the onSubmit handler
          }
        }, 300);
      }
    };

    window.addEventListener('voiceCommand', handleVoiceCommand);

    return () => {
      window.removeEventListener('voiceCommand', handleVoiceCommand);
      // Stop voice recognition if component unmounts while listening
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadMemoryStats = async () => {
    try {
      const stats = await aiAPI.getMemoryStats();
      setMemoryStats(stats);
    } catch (error) {
      console.error('Failed to load memory stats:', error);
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!inputValue.trim() || loading) return;

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: inputValue,
      timestamp: new Date().toISOString(),
    };

    setMessages([...messages, userMessage]);
    setInputValue('');
    setLoading(true);

    try {
      const response = await aiAPI.smartChat(inputValue, {
        lead_id: leadId,
        loan_id: loanId,
        include_context: true,
        ...context,
      });

      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
        contextUsed: response.context_used,
        contextCount: response.context_count,
        metadata: response.metadata,
      };

      setMessages((prev) => [...prev, aiMessage]);

      // Refresh memory stats after new conversation
      loadMemoryStats();
    } catch (error) {
      console.error('Smart AI chat error:', error);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please make sure the AI Memory System is configured with Pinecone and OpenAI API keys.',
        timestamp: new Date().toISOString(),
        contextUsed: false,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleVoiceInput = () => {
    // Check if browser supports Web Speech API
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('Sorry, your browser does not support speech recognition. Please try Chrome or Edge.');
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
      setInputValue(transcript);
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      if (event.error === 'no-speech') {
        alert('No speech detected. Please try again.');
      } else if (event.error !== 'aborted') {
        alert(`Error occurred: ${event.error}`);
      }
    };

    recognition.onend = () => {
      setIsListening(false);
      console.log('Voice recognition ended');
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  // Don't render on auth pages or without token
  if (isAuthPage || !localStorage.getItem('token')) {
    return null;
  }

  return (
    <div className="smart-ai-chat-wrapper">
      {/* Floating toggle button */}
      <div className="smart-ai-toggle-wrapper">
        <button
          className={`smart-ai-toggle-button ${isOpen ? 'open' : ''}`}
          onClick={() => setIsOpen(!isOpen)}
          title={isOpen ? 'Close AI Assistant' : 'Open AI Assistant'}
        >
          {isOpen ? '✕' : (
            <img
              src="https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=80&h=80&fit=crop&crop=face"
              alt="AI Assistant"
              className="toggle-avatar"
            />
          )}
          {!isOpen && memoryStats && memoryStats.total_memories > 0 && (
            <span className="toggle-badge">{memoryStats.total_memories}</span>
          )}
        </button>
        {!isOpen && <span className="toggle-label">Ask me a Question</span>}
      </div>

      {/* Chat panel */}
      {isOpen && (
        <div className="smart-ai-chat">
          <div className="smart-ai-chat-header">
            <div className="header-content">
              <h3>Smart AI Assistant</h3>
              {memoryStats && (
                <span className="memory-badge" title="Conversation memories stored">
                  {memoryStats.total_memories} memories
                </span>
              )}
            </div>
            <button
              className="stats-toggle"
              onClick={() => setShowStats(!showStats)}
              title="View memory statistics"
            >
              {showStats ? '📊 Hide Stats' : '📊 Stats'}
            </button>
          </div>

      {showStats && memoryStats && (
        <div className="memory-stats">
          <div className="stat-item">
            <span className="stat-label">Total Memories:</span>
            <span className="stat-value">{memoryStats.total_memories}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Vector Store:</span>
            <span className="stat-value">
              {memoryStats.memory_enabled ? (
                <span className="status-enabled">✓ Enabled</span>
              ) : (
                <span className="status-disabled">✗ Disabled</span>
              )}
            </span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Vectors Stored:</span>
            <span className="stat-value">{memoryStats.vector_count}</span>
          </div>
        </div>
      )}

      <div className="smart-ai-messages">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.role === 'user' ? 'message-user' : 'message-assistant'}`}
          >
            <div className="message-content">
              {message.content}
              {message.contextUsed && (
                <div className="context-indicator">
                  <span className="context-badge" title={`Retrieved ${message.contextCount} relevant past conversations`}>
                    🧠 Used {message.contextCount} past conversation{message.contextCount !== 1 ? 's' : ''}
                  </span>
                </div>
              )}
            </div>
            <div className="message-timestamp">
              {formatTimestamp(message.timestamp)}
            </div>
          </div>
        ))}
        {loading && (
          <div className="message message-assistant">
            <div className="message-content loading">
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

      <form className="smart-ai-input" onSubmit={handleSend}>
        <textarea
          ref={textareaRef}
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value);
            autoResize();
          }}
          placeholder={isListening ? '🎤 Listening... Speak now!' : 'Ask me anything... I remember our conversations!'}
          rows={1}
          disabled={loading}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
          style={{ minHeight: '40px', maxHeight: '150px', resize: 'none' }}
        />
        <div className="input-footer">
          <span className="input-hint">
            {memoryStats?.memory_enabled ? '🧠 Memory enabled' : '⚠️ Memory not configured'}
          </span>
          <div className="input-actions">
            <button
              type="button"
              className={`microphone-button ${isListening ? 'listening' : ''}`}
              onClick={handleVoiceInput}
              disabled={loading}
              title={isListening ? 'Stop listening' : 'Click to speak'}
            >
              {isListening ? '🔴' : '🎤'}
            </button>
            <button
              type="submit"
              className="send-button"
              disabled={!inputValue.trim() || loading}
            >
              {loading ? 'Thinking...' : 'Send'}
            </button>
          </div>
        </div>
      </form>
        </div>
      )}
    </div>
  );
}

export default SmartAIChat;
