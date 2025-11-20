import React, { useState, useEffect, useRef } from 'react';
import { aiAPI, conversationsAPI } from '../services/api';
import './AIAssistant.css';

function AIAssistant({ isOpen, onClose, context = {} }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: 'Hello! I\'m your Smart AI assistant with memory. I remember our past conversations and learn from them. I can help you with lead management, task automation, scheduling, and more. How can I assist you today?',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [memoryStats, setMemoryStats] = useState(null);
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      loadMemoryStats();
      if (context.lead_id || context.loan_id) {
        loadConversations();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, context.lead_id, context.loan_id]);

  useEffect(() => {
    // Cleanup voice recognition on unmount
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  const loadMemoryStats = async () => {
    try {
      const stats = await aiAPI.getMemoryStats();
      setMemoryStats(stats);
    } catch (error) {
      console.error('Failed to load memory stats:', error);
    }
  };

  const loadConversations = async () => {
    try {
      const params = {};
      if (context.lead_id) params.lead_id = context.lead_id;
      if (context.loan_id) params.loan_id = context.loan_id;

      const data = await conversationsAPI.getAll(params);
      if (data.length > 0) {
        const formattedMessages = data.map(conv => ({
          id: conv.id,
          role: conv.role,
          content: conv.role === 'user' ? conv.message : conv.response,
          timestamp: conv.created_at,
        }));
        setMessages(formattedMessages);
      }
    } catch (error) {
      console.error('Failed to load conversations:', error);
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
      // Call Smart AI API with memory
      const response = await aiAPI.smartChat(inputValue, {
        include_context: true,
        lead_id: context.lead_id,
        loan_id: context.loan_id,
        ...context
      });

      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
        contextUsed: response.context_used,
        contextCount: response.context_count,
      };

      setMessages((prev) => [...prev, aiMessage]);

      // Refresh memory stats
      loadMemoryStats();
    } catch (error) {
      console.error('AI chat error:', error);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please make sure the AI Memory System is configured with Pinecone and OpenAI API keys.',
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
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

  if (!isOpen) return null;

  return (
    <div className="ai-assistant">
      <div className="ai-assistant-header">
        <div className="header-content">
          <h3>
            <img
              src="https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=40&h=40&fit=crop&crop=face"
              alt="AI Assistant"
              className="ai-avatar"
            />
            Smart AI Assistant
          </h3>
          {memoryStats && (
            <span className="memory-badge" title="Conversations remembered">
              🧠 {memoryStats.total_memories} memories
            </span>
          )}
        </div>
        <button className="close-button" onClick={onClose}>
          ×
        </button>
      </div>

      <div className="ai-assistant-messages">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.role === 'user' ? 'message-user' : 'message-assistant'}`}
          >
            <div className="message-content">{message.content}</div>
            <div className="message-timestamp">
              {new Date(message.timestamp).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </div>
          </div>
        ))}
      </div>

      <form className="ai-assistant-input" onSubmit={handleSend}>
        <textarea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder={isListening ? '🎤 Listening... Speak now!' : 'Ask me anything...'}
          rows={3}
          disabled={loading}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
        />
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
          <button type="submit" className="send-button" disabled={!inputValue.trim() || loading}>
            {loading ? 'Thinking...' : 'Send'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default AIAssistant;
