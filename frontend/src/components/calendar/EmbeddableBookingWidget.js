/**
 * Embeddable Booking Widget
 *
 * A self-contained booking component that can be:
 * 1. Embedded in the app directly
 * 2. Served as a standalone page for iframe embedding
 * 3. Used in the borrower portal
 *
 * WCAG 2.1 AA compliant:
 * - All interactive elements have aria-labels
 * - Keyboard navigation with arrow keys for slot grids
 * - Live regions for status updates
 * - Skip-to-content link
 * - Form inputs with associated labels
 * - Focus management across steps
 *
 * Usage: <EmbeddableBookingWidget slug="booking-slug" />
 * Or via URL: /embed/book/{slug}
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import {
  normalizeUTCDate,
  formatTimeWithZone,
  formatInUserTimezone,
  getBrowserTimezone,
  getTimezoneAbbreviation,
} from '../../utils/timezone';

// =============================================================================
// Skeleton Loader
// =============================================================================

const SKELETON_STYLES = `
  @keyframes ebw-skeleton-pulse {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  .ebw-skeleton-line {
    border-radius: 6px;
    background: linear-gradient(90deg, #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%);
    background-size: 200% 100%;
    animation: ebw-skeleton-pulse 1.5s infinite;
  }
  .ebw-skip-link {
    position: absolute;
    left: -9999px;
    top: auto;
    width: 1px;
    height: 1px;
    overflow: hidden;
    z-index: 100;
    padding: 8px 16px;
    background: #6366f1;
    color: #fff;
    font-size: 14px;
    text-decoration: none;
    border-radius: 4px;
  }
  .ebw-skip-link:focus {
    position: static;
    width: auto;
    height: auto;
    display: inline-block;
    margin-bottom: 8px;
  }
`;

function SkeletonDateGrid() {
  return (
    <div>
      <div className="ebw-skeleton-line" style={{ width: '120px', height: '18px', marginBottom: 12 }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        {[1, 2, 3, 4, 5, 6].map(i => (
          <div key={i} className="ebw-skeleton-line" style={{ height: '48px', borderRadius: 8 }} />
        ))}
      </div>
    </div>
  );
}

function SkeletonTimeGrid() {
  return (
    <div>
      <div className="ebw-skeleton-line" style={{ width: '100px', height: '16px', marginBottom: 12 }} />
      <div className="ebw-skeleton-line" style={{ width: '160px', height: '18px', marginBottom: 16 }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="ebw-skeleton-line" style={{ height: '42px', borderRadius: 8 }} />
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// Styles
// =============================================================================

const WIDGET_STYLES = {
  container: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    maxWidth: 'min(480px, 100%)',
    width: '100%',
    margin: '0 auto',
    padding: 16,
    background: '#fff',
    borderRadius: 12,
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    boxSizing: 'border-box',
    position: 'relative',
  },
  header: {
    textAlign: 'center',
    marginBottom: 24,
  },
  dateGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 8,
    marginBottom: 20,
  },
  dateBtn: (selected) => ({
    padding: '12px 8px',
    border: `2px solid ${selected ? '#6366f1' : '#e2e8f0'}`,
    borderRadius: 8,
    background: selected ? '#eef2ff' : '#fff',
    cursor: 'pointer',
    textAlign: 'center',
    fontSize: '0.85rem',
    outline: 'none',
  }),
  dateBtnFocus: {
    boxShadow: '0 0 0 2px #6366f1',
  },
  timeGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 8,
    marginBottom: 20,
  },
  timeBtn: (selected, unavailable) => ({
    padding: '10px',
    border: `2px solid ${selected ? '#6366f1' : unavailable ? '#f1f5f9' : '#e2e8f0'}`,
    borderRadius: 8,
    background: selected ? '#eef2ff' : unavailable ? '#f8fafc' : '#fff',
    cursor: unavailable ? 'not-allowed' : 'pointer',
    textAlign: 'center',
    fontSize: '0.9rem',
    fontWeight: selected ? 600 : 400,
    color: unavailable ? '#94a3b8' : '#1e293b',
    outline: 'none',
    opacity: unavailable ? 0.6 : 1,
  }),
  submitBtn: {
    width: '100%',
    padding: '14px',
    background: '#6366f1',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: '1rem',
    fontWeight: 600,
    cursor: 'pointer',
  },
  input: {
    width: '100%',
    padding: '10px 12px',
    border: '1px solid #e2e8f0',
    borderRadius: 6,
    fontSize: '0.9rem',
    marginBottom: 4,
    boxSizing: 'border-box',
  },
  label: {
    display: 'block',
    fontSize: '0.8rem',
    fontWeight: 500,
    color: '#475569',
    marginBottom: 4,
    marginTop: 8,
  },
  srOnly: {
    position: 'absolute',
    width: '1px',
    height: '1px',
    padding: 0,
    margin: '-1px',
    overflow: 'hidden',
    clip: 'rect(0, 0, 0, 0)',
    whiteSpace: 'nowrap',
    borderWidth: 0,
  },
  backBtn: {
    background: 'none',
    border: 'none',
    color: '#6366f1',
    cursor: 'pointer',
    marginBottom: 12,
    padding: '4px 0',
    fontSize: '0.9rem',
  },
};

// =============================================================================
// Keyboard navigation helpers
// =============================================================================

/**
 * Handle arrow-key grid navigation.
 * @param {KeyboardEvent} e
 * @param {number} currentIndex - index of the focused element in the flat list
 * @param {number} totalCount - total items
 * @param {number} columns - number of grid columns
 * @param {Function} onMove - callback(newIndex)
 */
function handleGridKeyDown(e, currentIndex, totalCount, columns, onMove) {
  let nextIndex = currentIndex;

  switch (e.key) {
    case 'ArrowRight':
      nextIndex = currentIndex + 1;
      break;
    case 'ArrowLeft':
      nextIndex = currentIndex - 1;
      break;
    case 'ArrowDown':
      nextIndex = currentIndex + columns;
      break;
    case 'ArrowUp':
      nextIndex = currentIndex - columns;
      break;
    case 'Home':
      nextIndex = 0;
      break;
    case 'End':
      nextIndex = totalCount - 1;
      break;
    default:
      return; // Don't prevent default for other keys
  }

  if (nextIndex >= 0 && nextIndex < totalCount) {
    e.preventDefault();
    onMove(nextIndex);
  }
}

// =============================================================================
// Main component
// =============================================================================

export default function EmbeddableBookingWidget({ slug, onBooked, theme = {} }) {
  const [step, setStep] = useState('loading'); // loading, dates, times, form, confirm, success, error
  const [bookingLink, setBookingLink] = useState(null);
  const [dates, setDates] = useState([]);
  const [slots, setSlots] = useState([]);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [form, setForm] = useState({ name: '', email: '', phone: '' });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [focusedDateIndex, setFocusedDateIndex] = useState(0);
  const [focusedTimeIndex, setFocusedTimeIndex] = useState(0);

  // Refs for focus management
  const dateGridRef = useRef(null);
  const timeGridRef = useRef(null);
  const statusRef = useRef(null);
  const mainContentRef = useRef(null);

  const apiBase = '/api/v1/scheduler/public/book';

  useEffect(() => { loadBookingLink(); }, [slug]);

  // Focus the correct button when focusedDateIndex changes
  useEffect(() => {
    if (step === 'dates' && dateGridRef.current) {
      const buttons = dateGridRef.current.querySelectorAll('button');
      if (buttons[focusedDateIndex]) {
        buttons[focusedDateIndex].focus();
      }
    }
  }, [focusedDateIndex, step]);

  // Focus the correct button when focusedTimeIndex changes
  useEffect(() => {
    if (step === 'times' && timeGridRef.current) {
      const buttons = timeGridRef.current.querySelectorAll('button');
      if (buttons[focusedTimeIndex]) {
        buttons[focusedTimeIndex].focus();
      }
    }
  }, [focusedTimeIndex, step]);

  const loadBookingLink = async () => {
    try {
      const res = await fetch(`${apiBase}/${slug}`);
      if (!res.ok) throw new Error('Booking link not found');
      const data = await res.json();
      setBookingLink(data);
      await loadSlots();
      setStep('dates');
    } catch (err) {
      setError(err.message);
      setStep('error');
    }
  };

  const loadSlots = async () => {
    try {
      const today = new Date();
      const end = new Date(today);
      end.setDate(end.getDate() + 14);
      const res = await fetch(
        `${apiBase}/${slug}/slots?start_date=${today.toISOString().split('T')[0]}&end_date=${end.toISOString().split('T')[0]}`
      );
      if (res.ok) {
        const data = await res.json();
        const slotList = data.slots || data.available_slots || [];
        // Group by date, normalizing UTC strings from the backend
        const byDate = {};
        slotList.forEach(s => {
          const raw = s.start || s.start_time;
          const d = new Date(normalizeUTCDate(raw)).toISOString().split('T')[0];
          if (!byDate[d]) byDate[d] = [];
          byDate[d].push(s);
        });
        setDates(Object.keys(byDate).sort());
        setSlots(byDate);
      }
    } catch (err) {
      console.error('Failed to load slots:', err);
    }
  };

  const selectDate = (date) => {
    setSelectedDate(date);
    setSelectedSlot(null);
    setFocusedTimeIndex(0);
    setStep('times');
  };

  const selectSlot = (slot) => {
    setSelectedSlot(slot);
    setStep('form');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/${slug}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_time: selectedSlot.start || selectedSlot.start_time,
          duration_minutes: selectedSlot.duration_minutes || 30,
          attendee_name: form.name,
          attendee_email: form.email,
          attendee_phone: form.phone || undefined,
        }),
      });
      if (res.ok) {
        setStep('success');
        if (onBooked) onBooked(await res.json());
      } else {
        const data = await res.json();
        setError(data.detail || 'Booking failed. Please try again.');
      }
    } catch (err) {
      setError('Connection error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const formatDate = (dateStr) => {
    // dateStr is YYYY-MM-DD; add noon UTC to avoid date-boundary shifts
    return formatInUserTimezone(dateStr + 'T12:00:00Z', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatDateFull = (dateStr) => {
    return formatInUserTimezone(dateStr + 'T12:00:00Z', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    });
  };

  const formatTime = (slot) => {
    const raw = slot.start || slot.start_time;
    return formatTimeWithZone(raw);
  };

  const formatSlotAriaLabel = useCallback((slot) => {
    const time = formatTime(slot);
    const dur = slot.duration_minutes || 30;
    return `Book ${time}, ${dur} minute appointment`;
  }, []);

  const tzLabel = getTimezoneAbbreviation() || getBrowserTimezone();

  // -------------------------------------------------------------------------
  // Error view
  // -------------------------------------------------------------------------
  if (step === 'error') {
    return (
      <div style={WIDGET_STYLES.container} role="alert">
        <style>{SKELETON_STYLES}</style>
        <p style={{ color: '#ef4444' }}>{error}</p>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Loading skeleton view
  // -------------------------------------------------------------------------
  if (step === 'loading') {
    return (
      <div style={WIDGET_STYLES.container} aria-busy="true" aria-label="Loading available booking times">
        <style>{SKELETON_STYLES}</style>
        <div role="status" aria-live="polite">
          <span style={WIDGET_STYLES.srOnly}>Loading available times</span>
        </div>
        {/* Skeleton header */}
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div className="ebw-skeleton-line" style={{ width: '200px', height: '24px', margin: '0 auto 8px' }} />
          <div className="ebw-skeleton-line" style={{ width: '260px', height: '14px', margin: '0 auto 4px' }} />
          <div className="ebw-skeleton-line" style={{ width: '140px', height: '12px', margin: '0 auto' }} />
        </div>
        {/* Skeleton date grid */}
        <SkeletonDateGrid />
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Success view
  // -------------------------------------------------------------------------
  if (step === 'success') {
    return (
      <div style={WIDGET_STYLES.container} role="status" aria-live="polite">
        <style>{SKELETON_STYLES}</style>
        <div style={{ textAlign: 'center', padding: 20 }}>
          <div style={{ fontSize: 48, marginBottom: 12 }} aria-hidden="true">&#10003;</div>
          <h2 style={{ color: '#22c55e', marginBottom: 8 }}>Booked!</h2>
          <p style={{ color: '#64748b' }}>You will receive a confirmation email shortly.</p>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Main interactive view
  // -------------------------------------------------------------------------
  return (
    <div style={{ ...WIDGET_STYLES.container, ...theme }}>
      <style>{SKELETON_STYLES}</style>

      {/* Skip to main content link for keyboard users */}
      <a href="#ebw-main-content" className="ebw-skip-link">
        Skip to booking content
      </a>

      <div style={WIDGET_STYLES.header}>
        <h2 style={{ margin: '0 0 4px', fontSize: '1.3rem' }} id="ebw-widget-title">
          {bookingLink?.title || 'Schedule a Meeting'}
        </h2>
        <p style={{ margin: 0, color: '#64748b', fontSize: '0.9rem' }}>
          {bookingLink?.description || 'Select a date and time that works for you'}
        </p>
        <p style={{ margin: '4px 0 0', color: '#94a3b8', fontSize: '0.8rem' }}>
          Times shown in {tzLabel}
        </p>
      </div>

      {/* Live region for errors and confirmations */}
      <div ref={statusRef} aria-live="polite" aria-atomic="true" role="status">
        {error && (
          <div
            style={{
              background: '#fef2f2',
              color: '#dc2626',
              padding: 12,
              borderRadius: 8,
              marginBottom: 16,
              fontSize: '0.85rem',
            }}
            role="alert"
          >
            {error}
          </div>
        )}
      </div>

      <div id="ebw-main-content" ref={mainContentRef}>
        {/* ---- DATE SELECTION ---- */}
        {step === 'dates' && (
          <>
            <h3 style={{ fontSize: '0.95rem', marginBottom: 12 }} id="ebw-date-heading">
              Select a Date
            </h3>
            <div
              ref={dateGridRef}
              style={WIDGET_STYLES.dateGrid}
              role="group"
              aria-labelledby="ebw-date-heading"
            >
              {dates.slice(0, 9).map((date, index) => {
                const isSelected = selectedDate === date;
                const dateLabel = formatDateFull(date);
                return (
                  <button
                    key={date}
                    style={WIDGET_STYLES.dateBtn(isSelected)}
                    onClick={() => selectDate(date)}
                    aria-label={`${dateLabel}${isSelected ? ', selected' : ''}`}
                    aria-selected={isSelected}
                    tabIndex={index === focusedDateIndex ? 0 : -1}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        selectDate(date);
                        return;
                      }
                      handleGridKeyDown(e, index, Math.min(dates.length, 9), 3, (newIdx) => {
                        setFocusedDateIndex(newIdx);
                      });
                    }}
                    onFocus={() => setFocusedDateIndex(index)}
                  >
                    {formatDate(date)}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {/* ---- TIME SELECTION ---- */}
        {step === 'times' && selectedDate && (
          <>
            <button
              onClick={() => { setStep('dates'); setFocusedDateIndex(dates.indexOf(selectedDate) || 0); }}
              style={WIDGET_STYLES.backBtn}
              aria-label="Go back to date selection"
            >
              &larr; Back to dates
            </button>
            <h3 style={{ fontSize: '0.95rem', marginBottom: 12 }} id="ebw-time-heading">
              {formatDate(selectedDate)}
            </h3>
            <div
              ref={timeGridRef}
              style={WIDGET_STYLES.timeGrid}
              role="group"
              aria-label={`Available time slots for ${formatDateFull(selectedDate)}`}
            >
              {(slots[selectedDate] || []).map((slot, i) => {
                const isSelected = selectedSlot === slot;
                const isUnavailable = slot.unavailable === true;
                return (
                  <button
                    key={i}
                    style={WIDGET_STYLES.timeBtn(isSelected, isUnavailable)}
                    onClick={() => { if (!isUnavailable) selectSlot(slot); }}
                    aria-label={formatSlotAriaLabel(slot)}
                    aria-selected={isSelected}
                    aria-disabled={isUnavailable || undefined}
                    disabled={isUnavailable}
                    tabIndex={i === focusedTimeIndex ? 0 : -1}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        if (!isUnavailable) selectSlot(slot);
                        return;
                      }
                      const totalSlots = (slots[selectedDate] || []).length;
                      handleGridKeyDown(e, i, totalSlots, 3, (newIdx) => {
                        setFocusedTimeIndex(newIdx);
                      });
                    }}
                    onFocus={() => setFocusedTimeIndex(i)}
                  >
                    {formatTime(slot)}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {/* ---- BOOKING FORM ---- */}
        {step === 'form' && (
          <>
            <button
              onClick={() => setStep('times')}
              style={WIDGET_STYLES.backBtn}
              aria-label="Go back to time selection"
            >
              &larr; Back to times
            </button>
            <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: 16 }} aria-live="polite">
              {formatDate(selectedDate)} at {formatTime(selectedSlot)}
            </p>
            <form onSubmit={handleSubmit} aria-label="Booking details form" noValidate>
              <label htmlFor="ebw-name" style={WIDGET_STYLES.label}>
                Full Name <span aria-hidden="true">*</span>
                <span style={WIDGET_STYLES.srOnly}>(required)</span>
              </label>
              <input
                id="ebw-name"
                style={WIDGET_STYLES.input}
                type="text"
                autoComplete="name"
                value={form.name}
                onChange={e => setForm(f => ({...f, name: e.target.value}))}
                required
                aria-required="true"
              />

              <label htmlFor="ebw-email" style={WIDGET_STYLES.label}>
                Email Address <span aria-hidden="true">*</span>
                <span style={WIDGET_STYLES.srOnly}>(required)</span>
              </label>
              <input
                id="ebw-email"
                style={WIDGET_STYLES.input}
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={e => setForm(f => ({...f, email: e.target.value}))}
                required
                aria-required="true"
              />

              <label htmlFor="ebw-phone" style={WIDGET_STYLES.label}>
                Phone Number <span style={{ color: '#94a3b8', fontWeight: 400 }}>(optional)</span>
              </label>
              <input
                id="ebw-phone"
                style={{ ...WIDGET_STYLES.input, marginBottom: 16 }}
                type="tel"
                autoComplete="tel"
                value={form.phone}
                onChange={e => setForm(f => ({...f, phone: e.target.value}))}
              />

              <button
                type="submit"
                style={{...WIDGET_STYLES.submitBtn, opacity: submitting ? 0.7 : 1}}
                disabled={submitting}
                aria-busy={submitting}
                aria-label={submitting ? 'Booking in progress' : 'Confirm booking'}
              >
                {submitting ? 'Booking...' : 'Confirm Booking'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
