import React, { useState, useEffect, useRef } from 'react';
import { aiAPI, conversationsAPI } from '../services/api';
import CallIntelligencePanel from './CallIntelligencePanel';
import './AIAssistant.css';
import { toast } from '../utils/toast';

function AIAssistant({ isOpen, onClose, context = {} }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: 'Hey! I\'m Aria, your mortgage assistant. I can help you manage your pipeline, follow up with leads, schedule appointments, or just answer questions. What\'s on your mind?',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [memoryStats, setMemoryStats] = useState(null);
  const [isListening, setIsListening] = useState(false);
  const [showCallIntelligence, setShowCallIntelligence] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState({});
  const recognitionRef = useRef(null);
  const sessionIdRef = useRef(`aria-${Date.now()}`);

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
      // Call the full LangGraph orchestrator with 215 tools (email, tasks, pipeline, etc.)
      const response = await aiAPI.processCommand(inputValue, {
        lead_id: context.lead_id,
        loan_id: context.loan_id,
        ...context
      });

      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.response || response.explanation || '',
        timestamp: new Date().toISOString(),
        intent: response.intent,
        agentUsed: response.agent_used,
        actionsExecuted: response.actions_executed,
        followUpSuggestions: response.follow_up_suggestions,
      };

      setMessages((prev) => [...prev, aiMessage]);

      // Refresh memory stats
      loadMemoryStats();
    } catch (error) {
      console.error('AI chat error:', error);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request. Please try again.',
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
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setInputValue(transcript);
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
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const handleFeedback = async (message, rating) => {
    if (feedbackGiven[message.id]) return;

    setFeedbackGiven(prev => ({ ...prev, [message.id]: rating }));

    // Find the preceding user message for context
    const msgIndex = messages.findIndex(m => m.id === message.id);
    const precedingUserMsg = messages.slice(0, msgIndex).reverse().find(m => m.role === 'user');

    try {
      await aiAPI.submitInlineFeedback({
        sessionId: sessionIdRef.current,
        messageId: String(message.id),
        rating,
        userQuestion: precedingUserMsg?.content,
        aiResponse: message.content,
      });
    } catch (error) {
      console.error('Failed to submit feedback:', error);
      setFeedbackGiven(prev => {
        const updated = { ...prev };
        delete updated[message.id];
        return updated;
      });
    }
  };

  if (!isOpen) return null;

  // Handle artifact generated from Call Intelligence
  const handleArtifactGenerated = (artifact) => {
    // Add a message about the artifact
    const artifactMessage = {
      id: Date.now(),
      role: 'assistant',
      content: `I've captured a ${artifact.artifact_type.replace(/_/g, ' ')} from your call. Would you like me to take action on it?`,
      timestamp: new Date().toISOString(),
      artifact: artifact,
    };
    setMessages(prev => [...prev, artifactMessage]);
  };

  return (
    <div className="ai-assistant">
      <div className="ai-assistant-header">
        <div className="header-content">
          <div className="header-title-row">
            <div className="ai-avatar-container">
              <span className="ai-avatar-letter">A</span>
              <span className="ai-status-dot"></span>
            </div>
            <div className="header-titles">
              <h3>Aria</h3>
              <span className="header-subtitle">Your Mortgage AI</span>
            </div>
          </div>
        </div>
        <div className="header-actions">
          <button
            className={`rec-button ${showCallIntelligence ? 'active' : ''}`}
            onClick={() => setShowCallIntelligence(!showCallIntelligence)}
            title="Call Intelligence - Record and analyze calls"
          >
            <span className="rec-dot"></span>
            <span>REC</span>
          </button>
          <button className="settings-button" title="Settings">
            ⚙️
          </button>
        </div>
      </div>

      {/* Call Intelligence Panel */}
      <CallIntelligencePanel
        isOpen={showCallIntelligence}
        onClose={() => setShowCallIntelligence(false)}
        initialContext={context}
        onArtifactGenerated={handleArtifactGenerated}
      />

      <div className="ai-assistant-messages">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.role === 'user' ? 'message-user' : 'message-assistant'}`}
          >
            <div className="message-content">{message.content}</div>
            <div className="message-meta">
              <span className="message-timestamp">
                {new Date(message.timestamp).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
              {message.role === 'assistant' && (
                <span className="message-feedback">
                  <button
                    className={`feedback-btn${feedbackGiven[message.id] === 'positive' ? ' active' : ''}`}
                    onClick={() => handleFeedback(message, 'positive')}
                    disabled={!!feedbackGiven[message.id]}
                    title="Helpful response"
                    aria-label="Thumbs up"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
                  </button>
                  <button
                    className={`feedback-btn${feedbackGiven[message.id] === 'negative' ? ' active negative' : ''}`}
                    onClick={() => handleFeedback(message, 'negative')}
                    disabled={!!feedbackGiven[message.id]}
                    title="Unhelpful response"
                    aria-label="Thumbs down"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/><path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>
                  </button>
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <form className="ai-assistant-input" onSubmit={handleSend}>
        <div className="input-actions">
          <button
            type="button"
            className={`microphone-button ${isListening ? 'listening' : ''}`}
            onClick={handleVoiceInput}
            disabled={loading}
            title={isListening ? 'Stop listening' : 'Click to speak'}
          >
            🎤
          </button>
          <button type="button" className="add-button" title="Add attachment">
            +
          </button>
          <div className="chat-input-wrapper">
            <input
              type="text"
              className="chat-input"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={isListening ? 'Listening...' : 'Ask Aria anything...'}
              disabled={loading}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend(e);
                }
              }}
            />
          </div>
          <button type="submit" className="send-button" disabled={!inputValue.trim() || loading}>
            ➤
          </button>
        </div>
      </form>
    </div>
  );
}

export default AIAssistant;
