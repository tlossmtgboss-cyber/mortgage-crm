/**
 * AriaChatScreen.jsx
 * Perennia AI — Aria Conversational Interface (Web/Capacitor)
 *
 * Full chat UI for Aria with:
 * - Real-time streaming responses (WebSocket)
 * - Inline task confirmation cards
 * - Task completion result cards
 * - Typing indicators
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './AriaChatScreen.css';

const WS_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';
const WS_URL = WS_BASE.replace(/^http/, 'ws') + '/api/v1/aria/ws';

// ─── WebSocket client ──────────────────────────────────────────────────────
class AriaWebSocket {
  constructor(token, handlers) {
    this.token = token;
    this.onMessage = handlers.onMessage;
    this.onConnect = handlers.onConnect;
    this.onDisconnect = handlers.onDisconnect;
    this.onReconnecting = handlers.onReconnecting || (() => {});
    this.onSessionExpired = handlers.onSessionExpired || (() => {});
    this.ws = null;
    this.intentionalClose = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectTimer = null;
    this.pendingMessages = [];
  }

  connect() {
    this.ws = new WebSocket(`${WS_URL}?token=${this.token}`);
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.onConnect();
      this._flushPendingMessages();
    };
    this.ws.onclose = () => {
      this.onDisconnect();
      if (!this.intentionalClose) {
        this._attemptReconnect();
      }
    };
    this.ws.onmessage = (e) => {
      try {
        this.onMessage(JSON.parse(e.data));
      } catch (err) {
        console.error('Failed to parse message:', err);
      }
    };
  }

  send(data) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      // Queue message for delivery on reconnect
      this.pendingMessages.push(data);
      if (this.pendingMessages.length > 20) {
        this.pendingMessages.shift(); // drop oldest
      }
    }
  }

  disconnect() {
    this.intentionalClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
  }

  _attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.onDisconnect(); // signal final disconnected state
      return;
    }

    // Re-read token in case it was refreshed
    const freshToken = localStorage.getItem('access_token');
    if (!freshToken) {
      this.onSessionExpired();
      return;
    }
    this.token = freshToken;

    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;
    this.onReconnecting(this.reconnectAttempts);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  _flushPendingMessages() {
    const queued = this.pendingMessages.splice(0);
    for (const msg of queued) {
      this.send(msg);
    }
  }
}

// ─── Component ──────────────────────────────────────────────────────────────
export default function AriaChatScreen() {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [connected, setConnected] = useState(false);
  const [connStatus, setConnStatus] = useState('disconnected'); // 'connected' | 'reconnecting' | 'disconnected' | 'expired'
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);
  const wsRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => { scrollToBottom(); }, [messages, isTyping]);

  // ── Connect WebSocket ──
  useEffect(() => {
    initWs();
    return () => wsRef.current?.disconnect();
  }, []);

  const initWs = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setConnStatus('expired');
      return;
    }

    wsRef.current = new AriaWebSocket(token, {
      onConnect: () => { setConnected(true); setConnStatus('connected'); },
      onDisconnect: () => { setConnected(false); setConnStatus('disconnected'); },
      onReconnecting: () => { setConnStatus('reconnecting'); },
      onSessionExpired: () => { setConnected(false); setConnStatus('expired'); },
      onMessage: handleWsMessage,
    });
    wsRef.current.connect();
  };

  const handleWsMessage = useCallback((data) => {
    const { type } = data;

    if (type === 'greeting') {
      addMessage({ role: 'aria', variant: 'text', content: data.content });
      setIsTyping(false);
    }
    else if (type === 'typing') {
      setIsTyping(true);
    }
    else if (type === 'chunk') {
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.streaming) {
          return [...prev.slice(0, -1), { ...last, content: last.content + data.content }];
        }
        const newMsg = {
          id: `aria-${Date.now()}`, role: 'aria', variant: 'text',
          content: data.content, timestamp: new Date(), streaming: true,
        };
        setIsTyping(false);
        return [...prev, newMsg];
      });
    }
    else if (type === 'done') {
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.streaming) {
          return [...prev.slice(0, -1), { ...last, content: data.content, streaming: false }];
        }
        // If no streaming message exists, add as a new message
        return [...prev, {
          id: `aria-${Date.now()}`, role: 'aria', variant: 'text',
          content: data.content, timestamp: new Date(), streaming: false,
        }];
      });
      setIsTyping(false);
    }
    else if (type === 'confirmation_required') {
      setIsTyping(false);
      addMessage({
        role: 'aria', variant: 'confirmation',
        content: data.preview, confirmationPreview: data.preview,
      });
    }
    else if (type === 'task_complete') {
      addMessage({
        role: 'aria', variant: 'task_complete',
        content: 'Task completed', taskResult: data.result,
      });
    }
    else if (type === 'error') {
      setIsTyping(false);
      addMessage({ role: 'aria', variant: 'text', content: `Warning: ${data.message}` });
    }
  }, []);

  const addMessage = (msg) => {
    const full = {
      id: `${msg.role}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      timestamp: new Date(),
      ...msg,
    };
    setMessages(prev => [...prev, full]);
  };

  // ── Send message ──
  const handleSend = useCallback(() => {
    const text = inputText.trim();
    if (!text || !connected) return;

    setInputText('');
    addMessage({ role: 'user', variant: 'text', content: text });
    wsRef.current?.send({ type: 'message', content: text });
    setIsTyping(true);
    inputRef.current?.focus();
  }, [inputText, connected]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Confirm / cancel ──
  const handleConfirm = (confirmed) => {
    wsRef.current?.send({ type: 'confirm', value: confirmed });
    setMessages(prev => prev.map(m =>
      m.variant === 'confirmation' ? { ...m, variant: 'text' } : m
    ));
    if (confirmed) setIsTyping(true);
  };

  return (
    <div className="ac-root">
      {/* Header */}
      <div className="ac-header">
        <div className="ac-header-left">
          <div className={`ac-status-dot ${connected ? 'ac-status--on' : 'ac-status--off'}`} />
          <span className="ac-header-title">Aria</span>
        </div>
        <span className="ac-header-sub">
          {connStatus === 'connected' && 'AI Assistant'}
          {connStatus === 'reconnecting' && 'Reconnecting...'}
          {connStatus === 'disconnected' && 'Disconnected'}
          {connStatus === 'expired' && 'Session expired'}
        </span>
      </div>

      {/* Messages */}
      <div className="ac-messages">
        {messages.map(msg => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onConfirm={handleConfirm}
          />
        ))}
        {isTyping && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="ac-input-bar">
        <textarea
          ref={inputRef}
          className="ac-input"
          value={inputText}
          onChange={e => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Aria anything..."
          rows={1}
          maxLength={1000}
        />
        <button
          className={`ac-send-btn ${(!inputText.trim() || !connected) ? 'ac-send--disabled' : ''}`}
          onClick={handleSend}
          disabled={!inputText.trim() || !connected}
        >
          <span className="ac-send-icon">&uarr;</span>
        </button>
      </div>
    </div>
  );
}

// ─── Message bubble ──────────────────────────────────────────────────────────
function MessageBubble({ message, onConfirm }) {
  if (message.role === 'user') {
    return (
      <div className="ac-user-row">
        <div className="ac-user-bubble">
          <p className="ac-user-text">{message.content}</p>
        </div>
      </div>
    );
  }

  if (message.variant === 'confirmation') {
    return (
      <div className="ac-aria-row">
        <div className="ac-aria-avatar"><span>A</span></div>
        <div className="ac-aria-bubble ac-confirm-card">
          <p className="ac-aria-text">{message.content}</p>
          <div className="ac-confirm-actions">
            <button className="ac-cancel-btn" onClick={() => onConfirm(false)}>Cancel</button>
            <button className="ac-confirm-btn" onClick={() => onConfirm(true)}>Yes, do it &rarr;</button>
          </div>
        </div>
      </div>
    );
  }

  if (message.variant === 'task_complete' && message.taskResult) {
    const lines = Object.entries(message.taskResult)
      .filter(([k]) => !['action', 'document_id', 'message_id', 'loan_id'].includes(k))
      .map(([k, v]) => ({ key: k.replace(/_/g, ' '), value: String(v) }));

    return (
      <div className="ac-aria-row">
        <div className="ac-aria-avatar"><span>A</span></div>
        <div className="ac-aria-bubble ac-task-card">
          <div className="ac-task-header">
            <span className="ac-task-check">&#10003;</span>
            <span className="ac-task-title">Done</span>
          </div>
          {lines.map(({ key, value }) => (
            <div key={key} className="ac-task-row">
              <span className="ac-task-key">{key}</span>
              <span className="ac-task-val">{value}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="ac-aria-row">
      <div className="ac-aria-avatar"><span>A</span></div>
      <div className="ac-aria-bubble">
        <p className="ac-aria-text">{message.content}</p>
        {message.streaming && <TypingDots />}
      </div>
    </div>
  );
}

// ─── Typing indicators ──────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="ac-aria-row">
      <div className="ac-aria-avatar"><span>A</span></div>
      <div className="ac-aria-bubble ac-typing-bubble">
        <TypingDots />
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="ac-typing-dots">
      <div className="ac-dot" style={{ animationDelay: '0s' }} />
      <div className="ac-dot" style={{ animationDelay: '0.15s' }} />
      <div className="ac-dot" style={{ animationDelay: '0.3s' }} />
    </div>
  );
}
