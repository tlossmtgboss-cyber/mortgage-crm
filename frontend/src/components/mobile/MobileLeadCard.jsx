/**
 * MobileLeadCard
 *
 * Touch-first lead card designed for the mobile pipeline view.
 * Features swipe gestures, tap-to-call/email, and quick action buttons.
 */
import React, { useRef, useCallback, useState } from 'react';
import { formatPhoneNumber } from '../../utils/phoneUtils';
import './MobileLeadCard.css';

// ── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(dateStr) {
  if (!dateStr) return 'No contact';
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  if (isNaN(then)) return 'No contact';
  const diffMs = now - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function scoreGrade(aiScore) {
  if (aiScore == null) return null;
  const s = Number(aiScore);
  if (s >= 80) return 'A';
  if (s >= 60) return 'B';
  if (s >= 40) return 'C';
  return 'D';
}

function sourceClass(src) {
  if (!src) return 'default';
  const lower = (src || '').toLowerCase();
  if (lower.includes('referral')) return 'referral';
  if (lower.includes('website') || lower.includes('web')) return 'website';
  if (lower.includes('zillow')) return 'zillow';
  if (lower.includes('realtor') || lower.includes('agent')) return 'realtor';
  if (lower.includes('social') || lower.includes('facebook') || lower.includes('instagram')) return 'social';
  return 'default';
}

function formatAmount(val) {
  if (!val) return null;
  const n = Number(val);
  if (isNaN(n) || n === 0) return null;
  if (n >= 1000000) return `$${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `$${Math.round(n / 1000)}K`;
  return `$${n.toLocaleString()}`;
}

// ── Swipe threshold ──
const SWIPE_THRESHOLD = 70;

// ── Component ────────────────────────────────────────────────────────────────

export default function MobileLeadCard({
  lead,
  aiSuggestion,
  onCall,
  onText,
  onEmail,
  onNote,
  onArchive,
  onSchedule,
  onAskAria,
  onClick,
}) {
  const bodyRef = useRef(null);
  const startX = useRef(0);
  const currentX = useRef(0);
  const [swiping, setSwiping] = useState(false);

  const name = [lead.first_name, lead.last_name].filter(Boolean).join(' ') || 'Unknown';
  const phone = lead.phone;
  const email = lead.email;
  const grade = scoreGrade(lead.ai_score);
  const src = lead.source;
  const lastContact = lead.last_contact || lead.updated_at;
  const purpose = lead.loan_purpose;
  const amount = formatAmount(lead.loan_amount || lead.preapproval_amount);

  // ── Touch handlers for swipe ──
  const handleTouchStart = useCallback((e) => {
    startX.current = e.touches[0].clientX;
    currentX.current = 0;
    setSwiping(true);
  }, []);

  const handleTouchMove = useCallback((e) => {
    const dx = e.touches[0].clientX - startX.current;
    // Clamp between -90 and 90
    const clamped = Math.max(-90, Math.min(90, dx));
    currentX.current = clamped;
    if (bodyRef.current) {
      bodyRef.current.style.transform = `translateX(${clamped}px)`;
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    setSwiping(false);
    const dx = currentX.current;
    if (bodyRef.current) {
      bodyRef.current.style.transform = 'translateX(0)';
    }
    if (dx > SWIPE_THRESHOLD && onArchive) {
      onArchive(lead);
    } else if (dx < -SWIPE_THRESHOLD && onSchedule) {
      onSchedule(lead);
    }
    currentX.current = 0;
  }, [lead, onArchive, onSchedule]);

  const handleCardClick = useCallback((e) => {
    // Only fire if it wasn't a swipe or button press
    if (Math.abs(currentX.current) > 10) return;
    if (e.target.closest('a') || e.target.closest('button')) return;
    if (onClick) onClick(lead);
  }, [lead, onClick]);

  return (
    <div className="mlc" role="article" aria-label={`Lead: ${name}`}>
      {/* Swipe reveal backgrounds */}
      <div className="mlc__action-left" aria-hidden="true">
        <span className="mlc__action-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M10 11v6" /><path d="M14 11v6" />
          </svg>
        </span>
        Archive
      </div>
      <div className="mlc__action-right" aria-hidden="true">
        <span className="mlc__action-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
          </svg>
        </span>
        Follow-up
      </div>

      {/* Card body (slides on swipe) */}
      <div
        ref={bodyRef}
        className={`mlc__body${swiping ? ' mlc__body--swiping' : ''}`}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onClick={handleCardClick}
      >
        {/* Header */}
        <div className="mlc__header">
          <span className="mlc__name">{name}</span>
          {lead.stage && <span className="mlc__stage">{lead.stage}</span>}
          {src && (
            <span className={`mlc__source mlc__source--${sourceClass(src)}`}>
              {src}
            </span>
          )}
          {grade && (
            <span className={`mlc__score mlc__score--${grade}`} title={`Score: ${lead.ai_score}`}>
              {grade}
            </span>
          )}
        </div>

        {/* Contact links */}
        <div className="mlc__contact">
          {phone && (
            <a href={`tel:${phone.replace(/\D/g, '')}`} aria-label={`Call ${name}`}>
              <svg className="mlc__contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
              </svg>
              {formatPhoneNumber(phone)}
            </a>
          )}
          {email && (
            <a href={`mailto:${email}`} aria-label={`Email ${name}`}>
              <svg className="mlc__contact-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="4" width="20" height="16" rx="2" /><polyline points="22 7 12 13 2 7" />
              </svg>
              {email}
            </a>
          )}
        </div>

        {/* Meta row */}
        <div className="mlc__meta">
          <span className="mlc__last-contact">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
            </svg>
            {relativeTime(lastContact)}
          </span>
          {(purpose || amount) && (
            <span className="mlc__loan-interest">
              {[purpose, amount].filter(Boolean).join(' - ')}
            </span>
          )}
        </div>

        {/* AI suggestion */}
        {(aiSuggestion || grade === 'A' || grade === 'B') && (
          <div className="mlc__ai-hint">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" className="mlc__ai-hint-icon">
              <path d="M12 2 L13.5 8.5 L20 10 L13.5 11.5 L12 18 L10.5 11.5 L4 10 L10.5 8.5 Z" />
            </svg>
            {aiSuggestion || (grade === 'A' ? 'AI suggests: Call today' : 'AI suggests: Follow up soon')}
          </div>
        )}

        {/* Quick actions */}
        <div className="mlc__actions">
          <button
            className="mlc__action-btn mlc__action-btn--call"
            onClick={(e) => { e.stopPropagation(); if (onCall) onCall(lead); else if (phone) window.location.href = `tel:${phone.replace(/\D/g, '')}`; }}
            aria-label="Call"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
            </svg>
            Call
          </button>
          <button
            className="mlc__action-btn mlc__action-btn--text"
            onClick={(e) => { e.stopPropagation(); if (onText) onText(lead); else if (phone) window.location.href = `sms:${phone.replace(/\D/g, '')}`; }}
            aria-label="Text"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            Text
          </button>
          <button
            className="mlc__action-btn mlc__action-btn--email"
            onClick={(e) => { e.stopPropagation(); if (onEmail) onEmail(lead); else if (email) window.location.href = `mailto:${encodeURIComponent(email)}`; }}
            aria-label="Email"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="4" width="20" height="16" rx="2" /><polyline points="22 7 12 13 2 7" />
            </svg>
            Email
          </button>
          <button
            className="mlc__action-btn mlc__action-btn--note"
            onClick={(e) => { e.stopPropagation(); if (onNote) onNote(lead); }}
            aria-label="Add note"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            Note
          </button>
          {onAskAria && (
            <button
              className="mlc__action-btn mlc__action-btn--aria"
              onClick={(e) => { e.stopPropagation(); onAskAria(lead); }}
              aria-label="Ask Aria"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
                <path d="M12 2 L13.5 8.5 L20 10 L13.5 11.5 L12 18 L10.5 11.5 L4 10 L10.5 8.5 Z" />
              </svg>
              Aria
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Skeleton placeholder ─────────────────────────────────────────────────────

export function MobileLeadCardSkeleton() {
  return (
    <div className="mlc-skeleton" aria-hidden="true">
      <div className="mlc-skeleton__bar mlc-skeleton__bar--name" />
      <div className="mlc-skeleton__bar mlc-skeleton__bar--contact" />
      <div className="mlc-skeleton__bar mlc-skeleton__bar--meta" />
      <div className="mlc-skeleton__bar mlc-skeleton__bar--actions" />
    </div>
  );
}
