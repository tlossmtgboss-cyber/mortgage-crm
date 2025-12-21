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
  const [availableSlots, setAvailableSlots] = useState([]);
  const [showBookingForm, setShowBookingForm] = useState(false);
  const [bookingData, setBookingData] = useState({ name: '', email: '', phone: '', selectedSlot: null });
  const [bookingStatus, setBookingStatus] = useState(null);
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

      // Check if scheduling_intent and available_slots are present
      if (data.scheduling_intent && data.available_slots && data.available_slots.length > 0) {
        setAvailableSlots(data.available_slots);
      }

      setMessages(prev => [...prev, {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.response || "I'm sorry, I couldn't process that. Please try again.",
        availableSlots: data.available_slots,
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

  // Handle slot selection
  const handleSlotSelect = (slot) => {
    setBookingData(prev => ({ ...prev, selectedSlot: slot }));
    setShowBookingForm(true);
  };

  // Handle booking submission
  const handleBookAppointment = async () => {
    if (!bookingData.name || !bookingData.email || !bookingData.selectedSlot) {
      setBookingStatus({ type: 'error', message: 'Please fill in all required fields' });
      return;
    }

    setBookingStatus({ type: 'loading', message: 'Scheduling your appointment...' });

    try {
      const response = await fetch(`${API_BASE}/api/v1/public/themes/chat/${userSlug}/book`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_name: bookingData.name,
          contact_email: bookingData.email,
          contact_phone: bookingData.phone,
          appointment_date: bookingData.selectedSlot.date,
          appointment_time: bookingData.selectedSlot.start_time,
          appointment_type: 'consultation'
        })
      });

      const data = await response.json();

      if (data.success) {
        setBookingStatus({ type: 'success', message: data.message || 'Appointment confirmed!' });
        setShowBookingForm(false);
        setAvailableSlots([]);

        // Add confirmation message to chat
        setMessages(prev => [...prev, {
          id: `system-${Date.now()}`,
          role: 'assistant',
          content: `Great news! Your appointment with ${loName} is confirmed for ${bookingData.selectedSlot.display}. You'll receive a confirmation at ${bookingData.email}. We look forward to speaking with you!`,
          isConfirmation: true
        }]);

        // Reset booking data
        setBookingData({ name: '', email: '', phone: '', selectedSlot: null });
      } else {
        setBookingStatus({ type: 'error', message: data.error || 'Could not book appointment. Please try again.' });
      }
    } catch (error) {
      console.error('Error booking appointment:', error);
      setBookingStatus({ type: 'error', message: 'Something went wrong. Please try again.' });
    }
  };

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

        {/* Suggested Questions - Show when no messages */}
        {messages.length === 0 && (
          <div className="suggested-questions">
            <p className="suggestions-label">Popular questions:</p>
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
        )}

        {/* Messages Area - Shows conversation */}
        {messages.length > 0 && (
          <div className="chat-messages-area">
            <div className="messages-list">
              {messages.map((message) => (
                <div key={message.id} className={`message ${message.role} ${message.isConfirmation ? 'confirmation' : ''}`}>
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
                  <div className={`message-content ${message.isError ? 'error' : ''} ${message.isConfirmation ? 'confirmation' : ''}`}>
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
          </div>
        )}

        {/* Available Slots - Show when AI offers scheduling */}
        {availableSlots.length > 0 && !showBookingForm && (
          <div className="available-slots">
            <p className="slots-label">Select a time for your call with {loName}:</p>
            <div className="slots-grid">
              {availableSlots.slice(0, 6).map((slot, idx) => (
                <button
                  key={idx}
                  className="slot-btn"
                  onClick={() => handleSlotSelect(slot)}
                >
                  {slot.display}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Booking Form - Show when slot is selected */}
        {showBookingForm && (
          <div className="booking-form">
            <h4>Complete Your Booking</h4>
            <p className="booking-time">
              <strong>Selected time:</strong> {bookingData.selectedSlot?.display}
              <button className="change-time-btn" onClick={() => setShowBookingForm(false)}>Change</button>
            </p>

            <div className="form-group">
              <label>Your Name *</label>
              <input
                type="text"
                value={bookingData.name}
                onChange={(e) => setBookingData(prev => ({ ...prev, name: e.target.value }))}
                placeholder="John Smith"
              />
            </div>

            <div className="form-group">
              <label>Email *</label>
              <input
                type="email"
                value={bookingData.email}
                onChange={(e) => setBookingData(prev => ({ ...prev, email: e.target.value }))}
                placeholder="john@example.com"
              />
            </div>

            <div className="form-group">
              <label>Phone Number</label>
              <input
                type="tel"
                value={bookingData.phone}
                onChange={(e) => setBookingData(prev => ({ ...prev, phone: e.target.value }))}
                placeholder="(555) 123-4567"
              />
            </div>

            {bookingStatus && (
              <div className={`booking-status ${bookingStatus.type}`}>
                {bookingStatus.message}
              </div>
            )}

            <button
              className="book-btn"
              onClick={handleBookAppointment}
              disabled={bookingStatus?.type === 'loading'}
            >
              {bookingStatus?.type === 'loading' ? 'Scheduling...' : 'Confirm Appointment'}
            </button>
          </div>
        )}

        {/* Input Area - Always at bottom */}
        <div className="chat-input-area">
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your mortgage question here..."
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
        </div>
      </div>
    </section>
  );
};

export default EmbeddedAIChat;
