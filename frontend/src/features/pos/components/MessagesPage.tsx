import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { posApi } from '../api';
import type { BorrowerMessage } from '../types';

import './messages-page.css';

interface MessagesPageProps {
  applicationId: string;
  onAskAria?: () => void;
  onBack: () => void;
}

function formatMessageTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .map(w => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

export const MessagesPage: React.FC<MessagesPageProps> = ({
  applicationId,
  onAskAria,
  onBack,
}) => {
  const [messages, setMessages] = useState<BorrowerMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [markingAll, setMarkingAll] = useState(false);
  const [composeText, setComposeText] = useState('');
  const [sending, setSending] = useState(false);

  const loadMessages = useCallback(async () => {
    try {
      const resp = await posApi.getMessages(applicationId);
      setMessages(resp.messages);
    } catch (err) {
      console.error('Failed to load messages:', err);
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => { loadMessages(); }, [loadMessages]);

  const unreadCount = useMemo(
    () => messages.filter(m => !m.is_read).length,
    [messages],
  );

  const handleExpand = useCallback(async (msg: BorrowerMessage) => {
    const isExpanding = expandedId !== msg.id;
    setExpandedId(isExpanding ? msg.id : null);

    if (isExpanding && !msg.is_read) {
      try {
        const updated = await posApi.markMessageRead(applicationId, msg.id);
        setMessages(prev =>
          prev.map(m => m.id === msg.id ? { ...m, is_read: true, read_at: updated.read_at } : m),
        );
      } catch (err) {
        console.error('Failed to mark message as read:', err);
      }
    }
  }, [applicationId, expandedId]);

  const handleMarkAllRead = useCallback(async () => {
    setMarkingAll(true);
    try {
      const resp = await posApi.markAllMessagesRead(applicationId);
      setMessages(resp.messages);
    } catch (err) {
      console.error('Failed to mark all messages as read:', err);
    } finally {
      setMarkingAll(false);
    }
  }, [applicationId]);

  const handleSend = useCallback(async () => {
    if (!composeText.trim()) return;
    setSending(true);
    try {
      const newMsg = await posApi.sendMessage(applicationId, composeText.trim());
      setMessages(prev => [newMsg, ...prev]);
      setComposeText('');
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      setSending(false);
    }
  }, [applicationId, composeText]);

  if (loading) {
    return (
      <div className="messages-page">
        <div className="messages-page__loading">
          <div className="pos-loading__spinner" />
          <p>Loading messages…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="messages-page">
      <button type="button" className="messages-page__back" onClick={onBack}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to application
      </button>

      <div className="messages-page__header">
        <div className="messages-page__badge-row">
          <span className="messages-chip">Messages</span>
          {unreadCount > 0 && (
            <span className="messages-chip" style={{ background: '#FEF3C7', color: '#92400E' }}>
              {unreadCount} unread
            </span>
          )}
        </div>
        <h1 className="messages-page__title">Your Inbox</h1>
        <p className="messages-page__subtitle">
          Messages from your loan officer and lending team.
          Tap a message to read the full details.
        </p>
      </div>

      {unreadCount > 0 && (
        <div className="messages-page__actions">
          <button
            type="button"
            className="messages-mark-all"
            onClick={handleMarkAllRead}
            disabled={markingAll}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            Mark all as read
          </button>
        </div>
      )}

      {messages.length === 0 ? (
        <div className="messages-empty">
          <div className="messages-empty__icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <h3>No messages yet</h3>
          <p>Your lending team will send you updates here as your loan progresses.</p>
        </div>
      ) : (
        <div className="messages-card-list">
          {messages.map(msg => (
            <MessageCard
              key={msg.id}
              message={msg}
              expanded={expandedId === msg.id}
              onToggle={() => handleExpand(msg)}
            />
          ))}
        </div>
      )}

      <div className="messages-compose">
        <textarea
          className="messages-compose__input"
          placeholder="Type a message to your team…"
          value={composeText}
          onChange={e => setComposeText(e.target.value)}
          rows={2}
          maxLength={2000}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <div className="messages-compose__actions">
          {onAskAria && (
            <button
              type="button"
              className="messages-compose__aria"
              onClick={onAskAria}
            >
              Ask Aria instead
            </button>
          )}
          <button
            type="button"
            className="messages-compose__send"
            onClick={handleSend}
            disabled={sending || !composeText.trim()}
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ---------- Message card ----------

const MessageCard: React.FC<{
  message: BorrowerMessage;
  expanded: boolean;
  onToggle: () => void;
}> = ({ message, expanded, onToggle }) => {
  const isUnread = !message.is_read;
  const classes = [
    'messages-card',
    isUnread && 'messages-card--unread',
    expanded && 'messages-card--expanded',
    message.is_from_borrower && 'messages-card--sent',
  ].filter(Boolean).join(' ');

  return (
    <article className={classes} onClick={onToggle}>
      <div className="messages-card__top">
        <div className="messages-card__avatar">
          {getInitials(message.sender_name)}
        </div>

        <div className="messages-card__info">
          <div className="messages-card__sender-row">
            <span className="messages-card__sender">{message.sender_name}</span>
            <span className="messages-card__role">{message.sender_role}</span>
          </div>
          {!expanded && (
            <p className="messages-card__preview">{message.content}</p>
          )}
        </div>

        <div className="messages-card__meta">
          <span className="messages-card__time">
            {formatMessageTime(message.created_at)}
          </span>
          {isUnread && <span className="messages-card__unread-dot" />}
        </div>
      </div>

      {expanded && (
        <div className="messages-card__body">{message.content}</div>
      )}
    </article>
  );
};
