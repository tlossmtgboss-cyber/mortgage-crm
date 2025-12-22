import React, { useState, useRef, useEffect, useCallback } from 'react';
import { sanitizeHTML } from '../utils/sanitize';
import './AI1003Concierge.css';

/**
 * AI1003Concierge - Conversational interface for mortgage application
 *
 * Features:
 * - Natural language conversation to fill out 1003 application
 * - Voice input support
 * - Contextual follow-up questions
 * - Progress tracking
 * - Ability to switch to traditional form
 */

const CONVERSATION_STAGES = [
  { id: 'greeting', label: 'Introduction', icon: '👋' },
  { id: 'personal', label: 'Personal Info', icon: '👤' },
  { id: 'property', label: 'Property Details', icon: '🏠' },
  { id: 'income', label: 'Income & Employment', icon: '💼' },
  { id: 'assets', label: 'Assets', icon: '💰' },
  { id: 'liabilities', label: 'Debts', icon: '📊' },
  { id: 'declarations', label: 'Declarations', icon: '📋' },
  { id: 'review', label: 'Review', icon: '🔍' },
];

const AI1003Concierge = ({
  applicationToken,
  existingData = {},
  onDataExtracted,
  onSwitchToForm,
  onComplete,
  borrowerName = '',
  apiBaseUrl,
}) => {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [currentStage, setCurrentStage] = useState('greeting');
  const [extractedData, setExtractedData] = useState(existingData);
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState(null);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);

  // Initialize speech recognition
  useEffect(() => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = 'en-US';

      recognitionRef.current.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map(result => result[0].transcript)
          .join('');
        setInputValue(transcript);
      };

      recognitionRef.current.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
      };
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, []);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Initial greeting
  useEffect(() => {
    const firstName = borrowerName.split(' ')[0] || 'there';
    const greeting = {
      id: Date.now(),
      type: 'assistant',
      content: `Hi ${firstName}! I'm your AI Mortgage Concierge. I'll help you complete your loan application through a simple conversation. You can type or speak your answers - whatever feels more comfortable.

Let's start with the basics. Are you looking to **purchase** a new home, or **refinance** your current one?`,
      timestamp: new Date().toISOString(),
    };
    setMessages([greeting]);
  }, [borrowerName]);

  // Send message to AI backend
  const sendToAI = useCallback(async (userMessage) => {
    try {
      setIsTyping(true);

      // Call the backend AI endpoint
      const response = await fetch(`${apiBaseUrl}/api/v1/apply/${applicationToken}/concierge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMessage,
          current_stage: currentStage,
          extracted_data: extractedData,
          conversation_history: messages.slice(-10).map(m => ({
            role: m.type === 'user' ? 'user' : 'assistant',
            content: m.content,
          })),
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get AI response');
      }

      const data = await response.json();

      // Update extracted data
      if (data.extracted_data) {
        const newData = { ...extractedData, ...data.extracted_data };
        setExtractedData(newData);
        if (onDataExtracted) {
          onDataExtracted(newData);
        }
      }

      // Update stage if AI suggests it
      if (data.next_stage && data.next_stage !== currentStage) {
        setCurrentStage(data.next_stage);
      }

      // Add AI response
      const aiMessage = {
        id: Date.now(),
        type: 'assistant',
        content: data.response,
        timestamp: new Date().toISOString(),
        data_extracted: data.extracted_data,
      };
      setMessages(prev => [...prev, aiMessage]);

      // Check if complete
      if (data.is_complete && onComplete) {
        onComplete(extractedData);
      }

    } catch (err) {
      console.error('Error sending to AI:', err);
      setError('Sorry, I had trouble understanding that. Could you try again?');

      // Add fallback response
      const fallbackMessage = {
        id: Date.now(),
        type: 'assistant',
        content: "I apologize, but I'm having a bit of trouble right now. Could you please rephrase your answer, or you can switch to the traditional form if you prefer.",
        timestamp: new Date().toISOString(),
        isError: true,
      };
      setMessages(prev => [...prev, fallbackMessage]);
    } finally {
      setIsTyping(false);
    }
  }, [applicationToken, apiBaseUrl, currentStage, extractedData, messages, onComplete, onDataExtracted]);

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputValue.trim() || isTyping) return;

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputValue.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');

    await sendToAI(userMessage.content);
  };

  // Toggle voice input
  const toggleVoiceInput = () => {
    if (!recognitionRef.current) {
      setError('Voice input is not supported in your browser');
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
    } else {
      setInputValue('');
      recognitionRef.current.start();
      setIsListening(true);
    }
  };

  // Get progress percentage
  const getProgressPercentage = () => {
    const currentIndex = CONVERSATION_STAGES.findIndex(s => s.id === currentStage);
    return Math.round(((currentIndex + 1) / CONVERSATION_STAGES.length) * 100);
  };

  // Format message content with markdown-like formatting
  const formatMessage = (content) => {
    // Bold - convert markdown bold to HTML
    let formatted = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Line breaks - convert newlines to br tags
    formatted = formatted.replace(/\n/g, '<br />');
    // Sanitize the HTML to prevent XSS
    const sanitized = sanitizeHTML(formatted, { allowedTags: ['strong', 'br', 'em', 'b', 'i'] });
    return <span dangerouslySetInnerHTML={{ __html: sanitized }} />;
  };

  return (
    <div className="concierge-container">
      {/* Header */}
      <div className="concierge-header">
        <div className="concierge-title">
          <span className="concierge-icon">🤖</span>
          <div>
            <h2>AI Mortgage Concierge</h2>
            <p>Powered by Aria</p>
          </div>
        </div>
        <button
          className="switch-to-form-btn"
          onClick={onSwitchToForm}
        >
          Switch to Form →
        </button>
      </div>

      {/* Progress Bar */}
      <div className="concierge-progress">
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${getProgressPercentage()}%` }}
          />
        </div>
        <div className="progress-stages">
          {CONVERSATION_STAGES.map((stage, index) => (
            <div
              key={stage.id}
              className={`progress-stage ${
                CONVERSATION_STAGES.findIndex(s => s.id === currentStage) >= index
                  ? 'completed'
                  : ''
              } ${currentStage === stage.id ? 'current' : ''}`}
              title={stage.label}
            >
              <span className="stage-icon">{stage.icon}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Messages */}
      <div className="concierge-messages">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.type} ${message.isError ? 'error' : ''}`}
          >
            {message.type === 'assistant' && (
              <div className="message-avatar">🤖</div>
            )}
            <div className="message-content">
              <div className="message-text">
                {formatMessage(message.content)}
              </div>
              {message.data_extracted && Object.keys(message.data_extracted).length > 0 && (
                <div className="extracted-data-indicator">
                  ✓ Information captured
                </div>
              )}
            </div>
            {message.type === 'user' && (
              <div className="message-avatar">👤</div>
            )}
          </div>
        ))}

        {isTyping && (
          <div className="message assistant typing">
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
      </div>

      {/* Error banner */}
      {error && (
        <div className="concierge-error" onClick={() => setError(null)}>
          {error}
          <span className="dismiss">✕</span>
        </div>
      )}

      {/* Input area */}
      <form className="concierge-input" onSubmit={handleSubmit}>
        <div className="input-wrapper">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={isListening ? 'Listening...' : 'Type your answer or click the mic to speak...'}
            disabled={isTyping}
            className={isListening ? 'listening' : ''}
          />
          <button
            type="button"
            className={`voice-btn ${isListening ? 'active' : ''}`}
            onClick={toggleVoiceInput}
            disabled={isTyping}
            title={isListening ? 'Stop listening' : 'Use voice input'}
          >
            {isListening ? '🔴' : '🎤'}
          </button>
        </div>
        <button
          type="submit"
          className="send-btn"
          disabled={!inputValue.trim() || isTyping}
        >
          Send
        </button>
      </form>

      {/* Quick actions */}
      <div className="concierge-quick-actions">
        <button
          className="quick-action"
          onClick={() => setInputValue("I'm not sure")}
        >
          I'm not sure
        </button>
        <button
          className="quick-action"
          onClick={() => setInputValue("Skip this for now")}
        >
          Skip for now
        </button>
        <button
          className="quick-action"
          onClick={() => setInputValue("Can you explain?")}
        >
          Explain more
        </button>
      </div>
    </div>
  );
};

export default AI1003Concierge;
