import React, { useCallback, useEffect, useState } from 'react';

import { posApi } from '../api';
import type { TeamMember } from '../types';
import { SmartCalendar } from './SmartCalendar';

import './team-contact-panel.css';

interface TeamContactPanelProps {
  applicationId: string;
  onBack: () => void;
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

export const TeamContactPanel: React.FC<TeamContactPanelProps> = ({
  applicationId,
  onBack,
}) => {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [messageTarget, setMessageTarget] = useState<TeamMember | null>(null);
  const [messageText, setMessageText] = useState('');
  const [sending, setSending] = useState(false);
  const [sentConfirm, setSentConfirm] = useState(false);

  useEffect(() => {
    posApi.getTeam(applicationId)
      .then(resp => setMembers(resp.members))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [applicationId]);

  const handleSendMessage = useCallback(async () => {
    if (!messageText.trim() || !messageTarget) return;
    setSending(true);
    try {
      const prefixed = messageTarget
        ? `@${messageTarget.name}: ${messageText.trim()}`
        : messageText.trim();
      await posApi.sendMessage(applicationId, prefixed);
      setMessageText('');
      setMessageTarget(null);
      setSentConfirm(true);
      setTimeout(() => setSentConfirm(false), 3000);
    } catch {
      // keep the text so user can retry
    } finally {
      setSending(false);
    }
  }, [applicationId, messageText, messageTarget]);

  if (loading) {
    return (
      <div className="team-panel">
        <div className="team-panel__loading">
          <div className="pos-loading__spinner" />
          <p>Loading your team…</p>
        </div>
      </div>
    );
  }

  if (calendarOpen) {
    return (
      <div className="team-panel">
        <button type="button" className="team-panel__back" onClick={() => setCalendarOpen(false)}>
          <ChevronLeft />
          Back to team
        </button>
        <SmartCalendar
          applicationId={applicationId}
          onClose={() => setCalendarOpen(false)}
        />
      </div>
    );
  }

  return (
    <div className="team-panel">
      <button type="button" className="team-panel__back" onClick={onBack}>
        <ChevronLeft />
        Back to application
      </button>

      <div className="team-panel__header">
        <span className="team-chip">Your Team</span>
        <h1 className="team-panel__title">Your Lending Team</h1>
        <p className="team-panel__subtitle">
          Your dedicated team is here to help. Schedule a call, send a message,
          or dial directly.
        </p>
      </div>

      {members.length === 0 ? (
        <div className="team-empty">
          <h3>No team assigned yet</h3>
          <p>Your lending team will appear here once assigned.</p>
        </div>
      ) : (
        <div className="team-card-list">
          {members.map(member => (
            <TeamCard
              key={member.user_id}
              member={member}
              onSchedule={() => setCalendarOpen(true)}
              onMessage={() => {
                setMessageTarget(member);
                setTimeout(() => {
                  document.getElementById('team-msg-input')?.focus();
                }, 100);
              }}
            />
          ))}
        </div>
      )}

      {/* Message compose overlay */}
      {messageTarget && (
        <div className="team-compose">
          <div className="team-compose__header">
            <span className="team-compose__to">
              To: <strong>{messageTarget.name}</strong> · {messageTarget.role}
            </span>
            <button
              type="button"
              className="team-compose__close"
              onClick={() => { setMessageTarget(null); setMessageText(''); }}
              aria-label="Close"
            >
              <XIcon />
            </button>
          </div>
          <textarea
            id="team-msg-input"
            className="team-compose__input"
            placeholder="Type your message…"
            value={messageText}
            onChange={e => setMessageText(e.target.value)}
            rows={3}
            maxLength={2000}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
          />
          <div className="team-compose__actions">
            <span className="team-compose__hint">Press Enter to send</span>
            <button
              type="button"
              className="team-compose__send"
              onClick={handleSendMessage}
              disabled={sending || !messageText.trim()}
            >
              {sending ? 'Sending…' : 'Send'}
            </button>
          </div>
        </div>
      )}

      {sentConfirm && (
        <div className="team-toast">Message sent to your team</div>
      )}
    </div>
  );
};


const TeamCard: React.FC<{
  member: TeamMember;
  onSchedule: () => void;
  onMessage: () => void;
}> = ({ member, onSchedule, onMessage }) => {
  return (
    <div className="team-card">
      <div className="team-card__top">
        {member.avatar_url ? (
          <img src={member.avatar_url} alt="" className="team-card__avatar" />
        ) : (
          <div className="team-card__avatar team-card__avatar--initials">
            {getInitials(member.name)}
          </div>
        )}
        <div className="team-card__info">
          <span className="team-card__name">{member.name}</span>
          <span className="team-card__role">{member.role}</span>
          {member.nmls && (
            <span className="team-card__nmls">NMLS #{member.nmls}</span>
          )}
        </div>
      </div>

      <div className="team-card__actions">
        <button type="button" className="team-action team-action--schedule" onClick={onSchedule}>
          <CalendarIcon />
          Schedule
        </button>
        <button type="button" className="team-action team-action--message" onClick={onMessage}>
          <ChatIcon />
          Message
        </button>
        {member.phone && (
          <a
            href={`tel:${member.phone.replace(/\D/g, '')}`}
            className="team-action team-action--call"
          >
            <PhoneIcon />
            Call
          </a>
        )}
      </div>
    </div>
  );
};


// ---- Icons ----

const ChevronLeft: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="15 18 9 12 15 6" />
  </svg>
);

const XIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const CalendarIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);

const ChatIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const PhoneIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
  </svg>
);
