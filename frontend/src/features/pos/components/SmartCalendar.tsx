/**
 * SmartCalendar — Step 9 booking widget.
 *
 * Redesigned to match the scheduler booking UI: horizontal week date picker,
 * time dropdown, phone/video toggle, appointment-with info, and submit button.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { useSmartCalendar } from '../hooks/useSmartCalendar';
import type { BookingResponse, MeetingType, TimeSlot } from '../types';

export interface SmartCalendarProps {
  applicationId: string;
  onBooked?: (booking: BookingResponse) => void;
  onClose?: () => void;
  defaultMeetingType?: MeetingType;
}

const MEETING_TYPE_LABELS: Record<MeetingType, string> = {
  checkin: 'Quick check-in (15 min)',
  application_review: 'Application review (30 min)',
  full_consultation: 'Full consultation (60 min)',
};

type CallMode = 'phone' | 'video';

export const SmartCalendar: React.FC<SmartCalendarProps> = ({
  applicationId,
  onBooked,
  onClose,
  defaultMeetingType = 'application_review',
}) => {
  const {
    lo,
    slots,
    hold,
    booking,
    loadingLO,
    loadingSlots,
    busy,
    error,
    loadLO,
    loadSlots,
    holdSlot,
    bookSlot,
    releaseHold,
  } = useSmartCalendar(applicationId);

  const [meetingType, setMeetingType] = useState<MeetingType>(defaultMeetingType);
  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null);
  const [callMode, setCallMode] = useState<CallMode>('phone');
  const [weekOffset, setWeekOffset] = useState(0);

  useEffect(() => {
    loadLO();
    loadSlots();
  }, [loadLO, loadSlots]);

  useEffect(() => {
    if (booking && onBooked) onBooked(booking);
  }, [booking, onBooked]);

  const weekDays = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dayOfWeek = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((dayOfWeek === 0 ? 7 : dayOfWeek) - 1) + weekOffset * 7);

    const days: Date[] = [];
    for (let i = 0; i < 5; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      days.push(d);
    }
    return days;
  }, [weekOffset]);

  const selectedDateKey = useMemo(() => {
    if (!selectedSlot) return null;
    return new Date(selectedSlot.start).toISOString().slice(0, 10);
  }, [selectedSlot]);

  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const timesForSelectedDate = useMemo(() => {
    if (!selectedDate || !slots?.slots_by_date) return [];
    return slots.slots_by_date[selectedDate] ?? [];
  }, [selectedDate, slots]);

  const handleDateSelect = useCallback((date: Date) => {
    const key = date.toISOString().slice(0, 10);
    setSelectedDate(key);
    setSelectedSlot(null);
  }, []);

  const handleTimeChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const idx = parseInt(e.target.value, 10);
    if (isNaN(idx) || idx < 0) {
      setSelectedSlot(null);
      return;
    }
    setSelectedSlot(timesForSelectedDate[idx] ?? null);
  }, [timesForSelectedDate]);

  const handleSubmit = useCallback(async () => {
    if (!selectedSlot) return;
    if (!hold) await holdSlot(selectedSlot);
    const notes = callMode === 'video' ? 'Video call preferred' : undefined;
    await bookSlot(selectedSlot, meetingType, notes);
  }, [selectedSlot, hold, holdSlot, bookSlot, meetingType, callMode]);

  // ---------- confirmation view ----------

  if (booking) {
    return (
      <div className="smart-cal smart-cal--confirmed">
        <div className="smart-cal__confirm-icon" aria-hidden>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <polyline points="9 12 11 14 16 9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h3>You're all set</h3>
        <p>
          Your {MEETING_TYPE_LABELS[booking.meeting_type]} with{' '}
          <strong>{booking.loan_officer_name}</strong> is confirmed for:
        </p>
        <p className="smart-cal__confirmed-time">
          {formatDateTime(booking.scheduled_start, booking.timezone)}
        </p>
        <ul className="smart-cal__confirmed-actions">
          {booking.email_sent && <li>Confirmation email sent</li>}
          {booking.calendar_event_created && <li>Calendar invite delivered</li>}
          {booking.ics_link && (
            <li>
              <a href={booking.ics_link} download>Download .ics</a>
            </li>
          )}
        </ul>
      </div>
    );
  }

  // ---------- loading ----------

  if (loadingLO) {
    return <div className="smart-cal smart-cal--loading">Finding your loan officer…</div>;
  }

  if (!lo) {
    return (
      <div className="smart-cal smart-cal--error">
        <p>{error ?? 'No loan officer assigned yet.'}</p>
        <button onClick={() => loadLO()}>Try again</button>
      </div>
    );
  }

  // ---------- main view ----------

  return (
    <div className="smart-cal">
      <header className="smart-cal__header">
        <h2 className="smart-cal__title">Pick a date</h2>
        {onClose && (
          <button type="button" className="smart-cal__close" onClick={onClose} aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
      </header>

      {/* Week date picker */}
      <div className="smart-cal__week">
        <button
          type="button"
          className="smart-cal__week-nav"
          onClick={() => setWeekOffset(w => w - 1)}
          disabled={weekOffset <= 0}
          aria-label="Previous week"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        <div className="smart-cal__week-days">
          {weekDays.map(day => {
            const key = day.toISOString().slice(0, 10);
            const isSelected = selectedDate === key;
            const hasSlots = slots?.slots_by_date?.[key]?.length > 0;
            const isPast = day < new Date(new Date().toDateString());
            return (
              <button
                key={key}
                type="button"
                className={`smart-cal__day${isSelected ? ' is-selected' : ''}${!hasSlots || isPast ? ' is-disabled' : ''}`}
                onClick={() => handleDateSelect(day)}
                disabled={!hasSlots || isPast}
              >
                <span className="smart-cal__day-name">
                  {day.toLocaleDateString(undefined, { weekday: 'short' })}
                </span>
                <span className="smart-cal__day-num">{day.getDate()}</span>
                <span className="smart-cal__day-month">
                  {day.toLocaleDateString(undefined, { month: 'short' })}
                </span>
              </button>
            );
          })}
        </div>

        <button
          type="button"
          className="smart-cal__week-nav"
          onClick={() => setWeekOffset(w => w + 1)}
          disabled={weekOffset >= 3}
          aria-label="Next week"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <polyline points="9 6 15 12 9 18" />
          </svg>
        </button>
      </div>

      {/* Pick a time */}
      <div className="smart-cal__section">
        <label className="smart-cal__label">Pick a time</label>
        <select
          className="smart-cal__select"
          value={selectedSlot ? String(timesForSelectedDate.indexOf(selectedSlot)) : '-1'}
          onChange={handleTimeChange}
          disabled={!selectedDate || loadingSlots}
        >
          <option value="-1">
            {loadingSlots ? 'Loading…' : !selectedDate ? 'Select a date first' : timesForSelectedDate.length === 0 ? 'No times available' : 'Select a time'}
          </option>
          {timesForSelectedDate.map((slot, idx) => (
            <option key={idx} value={String(idx)}>
              {formatTime(slot.start, slots!.timezone)}
              {slot.is_recommended ? ' ★' : ''}
            </option>
          ))}
        </select>
      </div>

      {/* Phone / Video toggle */}
      <div className="smart-cal__section">
        <div className="smart-cal__mode-toggle">
          <button
            type="button"
            className={`smart-cal__mode-btn${callMode === 'phone' ? ' is-active' : ''}`}
            onClick={() => setCallMode('phone')}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
            </svg>
            Phone call
          </button>
          <button
            type="button"
            className={`smart-cal__mode-btn${callMode === 'video' ? ' is-active' : ''}`}
            onClick={() => setCallMode('video')}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="23 7 16 12 23 17 23 7" />
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            Video call
          </button>
        </div>
      </div>

      {/* Appointment with */}
      <div className="smart-cal__section">
        <label className="smart-cal__label">Appointment with</label>
        <div className="smart-cal__lo-display">
          {lo.avatar_url ? (
            <img src={lo.avatar_url} alt="" className="smart-cal__lo-avatar" />
          ) : (
            <span className="smart-cal__lo-avatar smart-cal__lo-avatar--initials">
              {initials(lo.name)}
            </span>
          )}
          <span className="smart-cal__lo-text">
            {lo.name}{lo.nmls ? ` · NMLS #${lo.nmls}` : ''}
          </span>
        </div>
      </div>

      {/* Info card */}
      <div className="smart-cal__info-card">
        <p className="smart-cal__info-line">
          <span className="smart-cal__info-label">Scheduling for:</span>{' '}
          <span className="smart-cal__info-value">{lo.name}</span>
        </p>
        <p className="smart-cal__info-line">
          <span className="smart-cal__info-label">Meeting type:</span>{' '}
          <span className="smart-cal__info-value">{MEETING_TYPE_LABELS[meetingType]}</span>
        </p>
      </div>

      {/* Submit */}
      <button
        type="button"
        className="smart-cal__submit"
        onClick={handleSubmit}
        disabled={!selectedSlot || busy}
      >
        {busy ? 'Booking…' : 'Submit'}
      </button>

      {error && <p className="smart-cal__error">{error}</p>}
    </div>
  );
};

// ---------- helpers ----------

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(p => p[0]?.toUpperCase() ?? '')
    .join('');
}

function formatDateTime(iso: string, timezone: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: timezone,
    timeZoneName: 'short',
  });
}

function formatTime(iso: string, timezone: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: timezone,
  });
}
