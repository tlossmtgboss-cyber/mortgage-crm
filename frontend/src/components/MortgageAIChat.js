/**
 * MortgageAIChat - AI Mortgage Assistant Chat Widget
 *
 * A beautiful, engaging chat widget that allows microsite visitors to:
 * - Ask mortgage and lending questions
 * - Get personalized guidance
 * - Schedule appointments with the loan officer
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './MortgageAIChat.css';
import api from '../services/api';

const MortgageAIChat = ({ userSlug, themeConfig = {} }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [loanOfficer, setLoanOfficer] = useState(null);
  const [showScheduler, setShowScheduler] = useState(false);
  const [showInlineCalendar, setShowInlineCalendar] = useState(false);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [trustPhase, setTrustPhase] = useState(1);
  const [bookingForm, setBookingForm] = useState({
    name: '',
    email: '',
    phone: '',
    selectedSlot: null
  });
  const [bookingStatus, setBookingStatus] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Theme colors with fallbacks
  const primaryColor = themeConfig.primaryColor || '#2d5a27';
  const accentColor = themeConfig.accentColor || '#8bc34a';

  // Initialize chat
  useEffect(() => {
    if (isOpen && !loanOfficer) {
      fetchChatInfo();
    }
  }, [isOpen]);

  // Scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Focus input when chat opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 300);
    }
  }, [isOpen]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const fetchChatInfo = async () => {
    try {
      const { data } = await api.get(`/api/v1/public/themes/chat/${userSlug}/info`);
      setLoanOfficer(data.loan_officer);
      // Add greeting message
      if (data.greeting) {
        setMessages([{
          id: 'greeting',
          role: 'assistant',
          content: data.greeting,
          timestamp: new Date()
        }]);
      }
    } catch (error) {
      console.error('Error fetching chat info:', error);
    }
  };

  const fetchAvailability = async () => {
    try {
      const { data } = await api.get(`/api/v1/public/themes/chat/${userSlug}/availability?days_ahead=7`);
      setAvailableSlots(data.slots || []);
    } catch (error) {
      console.error('Error fetching availability:', error);
    }
  };

  const sendMessage = async (e) => {
    e?.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const userMessage = inputValue.trim();
    setInputValue('');

    // Add user message to chat
    const newUserMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: userMessage,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, newUserMessage]);
    setIsLoading(true);

    try {
      const conversationHistory = messages.map(m => ({
        role: m.role,
        content: m.content
      }));

      const { data } = await api.post(`/api/v1/public/themes/chat/${userSlug}/message`, {
        message: userMessage,
        session_id: sessionId,
        conversation_history: conversationHistory
      });

      if (data.session_id) {
        setSessionId(data.session_id);
      }

      // Track trust phase
      if (data.phase) {
        setTrustPhase(data.phase);
      }

      // Add assistant response
      const assistantMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.response || "I'm sorry, I couldn't process that. Please try again.",
        timestamp: new Date(),
        schedulingIntent: data.scheduling_intent,
        budgetIntent: data.budget_intent,
        phase: data.phase,
        availableSlots: data.available_slots
      };
      setMessages(prev => [...prev, assistantMessage]);

      // If scheduling intent detected, show inline calendar with slots
      if (data.scheduling_intent && data.available_slots?.length > 0) {
        setAvailableSlots(data.available_slots);
        setShowInlineCalendar(true);
      } else if (data.scheduling_intent) {
        fetchAvailability();
      }

    } catch (error) {
      console.error('Error sending message:', error);
      setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: "I'm having trouble connecting. Please try again in a moment.",
        timestamp: new Date(),
        isError: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleScheduleClick = () => {
    setShowScheduler(true);
    fetchAvailability();
  };

  const handleSlotSelect = (slot) => {
    setBookingForm(prev => ({ ...prev, selectedSlot: slot }));
  };

  const handleBookAppointment = async () => {
    if (!bookingForm.name || !bookingForm.email || !bookingForm.selectedSlot) {
      return;
    }

    setBookingStatus('loading');

    try {
      const { data } = await api.post(`/api/v1/public/themes/chat/${userSlug}/book`, {
        contact_name: bookingForm.name,
        contact_email: bookingForm.email,
        contact_phone: bookingForm.phone,
        appointment_date: bookingForm.selectedSlot.date,
        appointment_time: bookingForm.selectedSlot.start_time,
        appointment_type: 'consultation',
        notes: `Booked via AI chat assistant`
      });

      if (data.success) {
        setBookingStatus('success');
        // Add confirmation message
        setMessages(prev => [...prev, {
          id: `booking-${Date.now()}`,
          role: 'assistant',
          content: `Great news! Your appointment has been scheduled for ${bookingForm.selectedSlot.display}. You'll receive a confirmation email at ${bookingForm.email}. ${loanOfficer?.name || 'The loan officer'} looks forward to speaking with you!`,
          timestamp: new Date()
        }]);
        // Reset scheduler
        setTimeout(() => {
          setShowScheduler(false);
          setBookingForm({ name: '', email: '', phone: '', selectedSlot: null });
          setBookingStatus(null);
        }, 2000);
      } else {
        setBookingStatus('error');
      }
    } catch (error) {
      console.error('Error booking appointment:', error);
      setBookingStatus('error');
    }
  };

  const quickQuestions = [
    "What mortgage options do I have?",
    "How much can I afford?",
    "What's the current rate?",
    "Schedule a call"
  ];

  const handleQuickQuestion = (question) => {
    if (question === "Schedule a call") {
      handleScheduleClick();
    } else {
      setInputValue(question);
      setTimeout(() => {
        const form = document.querySelector('.chat-input-form');
        form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      }, 100);
    }
  };

  return (
    <div className="mortgage-ai-chat" style={{ '--primary-color': primaryColor, '--accent-color': accentColor }}>
      {/* Chat Toggle Button */}
      <button
        className={`chat-toggle-btn ${isOpen ? 'open' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-label={isOpen ? 'Close chat' : 'Open chat'}
      >
        {isOpen ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="chat-toggle-label">Ask AI</span>
          </>
        )}
      </button>

      {/* Chat Window */}
      <div className={`chat-window ${isOpen ? 'open' : ''}`}>
        {/* Header */}
        <div className="chat-header">
          <div className="chat-header-content">
            <div className="chat-avatar">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
              </svg>
            </div>
            <div className="chat-header-text">
              <h3>AI Mortgage Assistant</h3>
              <p>{loanOfficer?.name ? `Powered by ${loanOfficer.name}'s expertise` : 'Here to help with your questions'}</p>
            </div>
          </div>
          <button className="chat-close-btn" onClick={() => setIsOpen(false)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Trust Progress Indicator - subtle indicator of conversation progress */}
        {trustPhase > 1 && trustPhase < 4 && (
          <div className="trust-progress-bar">
            <div className="trust-progress-fill" style={{ width: `${(trustPhase / 4) * 100}%` }} />
          </div>
        )}

        {/* Messages Area */}
        <div className="chat-messages">
          {messages.map((message, index) => (
            <div
              key={message.id}
              className={`chat-message ${message.role} ${message.isError ? 'error' : ''}`}
            >
              {message.role === 'assistant' && (
                <div className="message-avatar">
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                  </svg>
                </div>
              )}
              <div className="message-bubble">
                <p>{message.content}</p>

                {/* Inline Calendar - shown when AI offers to schedule */}
                {message.schedulingIntent && message.availableSlots?.length > 0 && !showScheduler && !bookingStatus && (
                  <div className="inline-calendar">
                    <div className="inline-calendar-header">
                      <span className="calendar-icon">📅</span>
                      <span>Pick a time that works for you:</span>
                    </div>
                    <div className="inline-slots">
                      {message.availableSlots.slice(0, 4).map((slot, idx) => (
                        <button
                          key={idx}
                          className={`inline-slot-btn ${bookingForm.selectedSlot === slot ? 'selected' : ''}`}
                          onClick={() => {
                            setBookingForm(prev => ({ ...prev, selectedSlot: slot }));
                            setShowScheduler(true);
                          }}
                        >
                          <span className="slot-day">{slot.day}</span>
                          <span className="slot-time">{slot.start_time}</span>
                        </button>
                      ))}
                    </div>
                    <button
                      className="view-more-times"
                      onClick={handleScheduleClick}
                    >
                      View more times →
                    </button>
                  </div>
                )}

                {/* Fallback schedule button if no inline slots */}
                {message.schedulingIntent && !message.availableSlots?.length && !showScheduler && (
                  <button
                    className="schedule-cta-btn"
                    onClick={handleScheduleClick}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                      <line x1="16" y1="2" x2="16" y2="6"/>
                      <line x1="8" y1="2" x2="8" y2="6"/>
                      <line x1="3" y1="10" x2="21" y2="10"/>
                    </svg>
                    Schedule a Call
                  </button>
                )}

                {/* Budget Calculator Button - shown when discussing affordability/payments */}
                {message.budgetIntent && !message.schedulingIntent && (
                  <a
                    href="/apply/purchase?stage=calculator"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="budget-calculator-btn"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="4" y="2" width="16" height="20" rx="2"/>
                      <line x1="8" y1="6" x2="16" y2="6"/>
                      <line x1="8" y1="10" x2="10" y2="10"/>
                      <line x1="14" y1="10" x2="16" y2="10"/>
                      <line x1="8" y1="14" x2="10" y2="14"/>
                      <line x1="14" y1="14" x2="16" y2="14"/>
                      <line x1="8" y1="18" x2="16" y2="18"/>
                    </svg>
                    Try Our Budget Calculator
                  </a>
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="chat-message assistant">
              <div className="message-avatar">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                </svg>
              </div>
              <div className="message-bubble typing">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Scheduler Panel */}
        {showScheduler && (
          <div className="scheduler-panel">
            <div className="scheduler-header">
              <h4>Schedule Your Consultation</h4>
              <button onClick={() => setShowScheduler(false)}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {bookingStatus === 'success' ? (
              <div className="booking-success">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                </svg>
                <p>Appointment Confirmed!</p>
              </div>
            ) : (
              <>
                <div className="scheduler-form">
                  <input
                    type="text"
                    placeholder="Your Name *"
                    value={bookingForm.name}
                    onChange={(e) => setBookingForm(prev => ({ ...prev, name: e.target.value }))}
                  />
                  <input
                    type="email"
                    placeholder="Email Address *"
                    value={bookingForm.email}
                    onChange={(e) => setBookingForm(prev => ({ ...prev, email: e.target.value }))}
                  />
                  <input
                    type="tel"
                    placeholder="Phone Number"
                    value={bookingForm.phone}
                    onChange={(e) => setBookingForm(prev => ({ ...prev, phone: e.target.value }))}
                  />
                </div>

                <div className="available-slots">
                  <p className="slots-label">Available Times:</p>
                  {availableSlots.length > 0 ? (
                    <div className="slots-grid">
                      {availableSlots.slice(0, 6).map((slot, index) => (
                        <button
                          key={index}
                          className={`slot-btn ${bookingForm.selectedSlot === slot ? 'selected' : ''}`}
                          onClick={() => handleSlotSelect(slot)}
                        >
                          <span className="slot-day">{slot.day}</span>
                          <span className="slot-time">{slot.start_time}</span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="no-slots">Loading available times...</p>
                  )}
                </div>

                <button
                  className="book-btn"
                  onClick={handleBookAppointment}
                  disabled={!bookingForm.name || !bookingForm.email || !bookingForm.selectedSlot || bookingStatus === 'loading'}
                >
                  {bookingStatus === 'loading' ? (
                    <span className="loading-spinner"></span>
                  ) : (
                    <>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M5 12l5 5L20 7"/>
                      </svg>
                      Confirm Appointment
                    </>
                  )}
                </button>

                {bookingStatus === 'error' && (
                  <p className="booking-error">Something went wrong. Please try again.</p>
                )}
              </>
            )}
          </div>
        )}

        {/* Quick Questions */}
        {messages.length <= 1 && !showScheduler && (
          <div className="quick-questions">
            {quickQuestions.map((question, index) => (
              <button
                key={index}
                className="quick-question-btn"
                onClick={() => handleQuickQuestion(question)}
              >
                {question}
              </button>
            ))}
          </div>
        )}

        {/* Input Area */}
        {!showScheduler && (
          <form className="chat-input-form" onSubmit={sendMessage}>
            <input
              ref={inputRef}
              type="text"
              placeholder="Ask me anything about mortgages..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              disabled={isLoading}
            />
            <button type="submit" disabled={!inputValue.trim() || isLoading}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
              </svg>
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default MortgageAIChat;
