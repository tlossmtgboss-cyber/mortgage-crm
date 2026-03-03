/**
 * ChatPanel — In-meeting chat using Chime SDK data messages.
 *
 * Uses realtimeSendDataMessage / realtimeSubscribeToReceiveDataMessage
 * on the "chat" topic to exchange JSON-encoded chat messages.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAudioVideo } from 'amazon-chime-sdk-component-library-react';
import { sanitizeText } from '../../utils/sanitize';

const CHAT_TOPIC = 'chat';

export default function ChatPanel({ displayName, onClose }) {
  const audioVideo = useAudioVideo();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  // Subscribe to incoming chat messages
  useEffect(() => {
    if (!audioVideo) return;

    const handler = (dataMessage) => {
      try {
        const payload = JSON.parse(new TextDecoder().decode(dataMessage.data));
        setMessages(prev => [...prev, {
          sender: payload.sender || 'Unknown',
          message: payload.message,
          timestamp: payload.timestamp || new Date().toISOString(),
          isLocal: false,
        }]);
      } catch (err) {
        console.warn('Failed to parse chat message:', err);
      }
    };

    audioVideo.realtimeSubscribeToReceiveDataMessage(CHAT_TOPIC, handler);
    return () => {
      audioVideo.realtimeUnsubscribeFromReceiveDataMessage(CHAT_TOPIC);
    };
  }, [audioVideo]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(() => {
    if (!input.trim() || !audioVideo) return;

    const sanitized = sanitizeText(input.trim());
    const payload = {
      sender: displayName || 'You',
      message: sanitized,
      timestamp: new Date().toISOString(),
    };

    try {
      audioVideo.realtimeSendDataMessage(CHAT_TOPIC, JSON.stringify(payload));
      setMessages(prev => [...prev, { ...payload, isLocal: true }]);
      setInput('');
    } catch (err) {
      console.error('Failed to send chat message:', err);
    }
  }, [input, audioVideo, displayName]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatTime = (iso) => {
    try {
      return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>Chat</h3>
        <button className="chat-close-btn" onClick={onClose}>&times;</button>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">No messages yet</div>
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={`chat-message ${msg.isLocal ? 'local' : 'remote'}`}>
            <span className="chat-sender">{msg.isLocal ? 'You' : msg.sender}</span>
            <span className="chat-text">{msg.message}</span>
            <span className="chat-time">{formatTime(msg.timestamp)}</span>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <input
          type="text"
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          maxLength={1000}
        />
        <button className="chat-send-btn" onClick={sendMessage} disabled={!input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
