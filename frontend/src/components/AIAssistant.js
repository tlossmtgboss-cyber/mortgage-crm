import React, { useState, useEffect } from 'react';
import { aiAPI, conversationsAPI } from '../services/api';
import './AIAssistant.css';

function AIAssistant({ isOpen, onClose, context = {} }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: 'Hello! I\'m your AI assistant. I can help you with lead management, task automation, scheduling, and more. How can I assist you today?',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && (context.lead_id || context.loan_id)) {
      loadConversations();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, context.lead_id, context.loan_id]);

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
      // Call AI API
      const response = await aiAPI.chat(inputValue, context);

      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, aiMessage]);
    } catch (error) {
      console.error('AI chat error:', error);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please make sure the OpenAI API key is configured in the backend.',
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="ai-assistant">
      <div className="ai-assistant-header">
        <h3>AI Assistant</h3>
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
          placeholder="Ask me anything..."
          rows={3}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
        />
        <button type="submit" className="send-button" disabled={!inputValue.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}

export default AIAssistant;
