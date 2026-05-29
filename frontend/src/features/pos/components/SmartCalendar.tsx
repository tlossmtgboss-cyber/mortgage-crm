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

const MEETING_TYPE_DURATION: Record<MeetingType, number> = {
  checkin: 15,
  application_review: 30,
  full_consultation: 60,
};

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

  const [meetingType] = useState<MeetingType>(defaultMeetingType);
  const [selectedSlotStart, setSelectedSlotStart] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const minWeekOffset = useMemo(() => {
    const dow = new Date().getDay();
    return (dow === 0 || dow === 6) ? 1 : 0;
  }, []);
  const [weekOffset, setWeekOffset] = useState(minWeekOffset);

  useEffect(() => {
    loadLO();
    loadSlots();
  }, [loadLO, loadSlots]);

  useEffect(() => {
    if (booking && onBooked) onBooked(booking);
  }, [booking, onBooked]);

  // Auto-select the first weekday with available slots once data loads.
  useEffect(() => {
    if (selectedDate || !slots?.slots_by_date) return;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayKey = today.toISOString().slice(0, 10);

    const sortedDates = Object.keys(slots.slots_by_date).sort();
    const firstAvailable = sortedDates.find(dateKey => {
      if (dateKey < todayKey) return false;
      const dateSlots = slots.slots_by_date[dateKey];
      return dateSlots?.some(s => s.is_available);
    });

    if (firstAvailable) {
      setSelectedDate(firstAvailable);
      const firstDate = new Date(firstAvailable + 'T12:00:00');
      const diffDays = Math.floor((firstDate.getTime() - today.getTime()) / (24 * 60 * 60 * 1000));
      const neededWeekOffset = Math.floor(diffDays / 7) + minWeekOffset;
      setWeekOffset(w => w === neededWeekOffset ? w : neededWeekOffset);
    }
  }, [slots, selectedDate, minWeekOffset]);

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

  const timesForSelectedDate = useMemo(() => {
    if (!selectedDate) return [];
    return slots?.slots_by_date?.[selectedDate] ?? [];
  }, [selectedDate, slots]);

  const selectedSlot = useMemo(
    () => timesForSelectedDate.find(s => s.start === selectedSlotStart) ?? null,
    [timesForSelectedDate, selectedSlotStart],
  );

  // Dates that have at least one available slot. Declared before any early
  // return so hook order stays stable across renders (Rules of Hooks).
  const datesWithSlots = useMemo(() => {
    if (!slots?.slots_by_date) return new Set<string>();
    const result = new Set<string>();
    for (const [dateKey, dateSlots] of Object.entries(slots.slots_by_date)) {
      if (dateSlots.some(s => s.is_available)) result.add(dateKey);
    }
    return result;
  }, [slots]);

  const handleDateSelect = useCallback((date: Date) => {
    const key = date.toISOString().slice(0, 10);
    setSelectedDate(key);
    setSelectedSlotStart(null);
  }, []);

  const handleTimeSelect = useCallback((slot: TimeSlot) => {
    if (!slot.is_available) return;
    setSelectedSlotStart(slot.start);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!selectedSlot || !selectedSlot.is_available) return;
    const held = await holdSlot(selectedSlot);
    if (!held) return;
    await bookSlot(selectedSlot, meetingType);
  }, [selectedSlot, holdSlot, bookSlot, meetingType]);

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

  // ---------- summary line ----------

  const durationMin = MEETING_TYPE_DURATION[meetingType];
  const summaryParts: string[] = [];
  if (selectedDate) {
    const d = new Date(selectedDate + 'T12:00:00');
    summaryParts.push(d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }));
  }
  if (selectedSlot) {
    const tz = slots?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
    summaryParts.push('at ' + formatTime(selectedSlot.start, tz));
  }

  const loName = lo?.name ?? 'your loan officer';

  // ---------- main view ----------

  return (
    <div className="smart-cal">
      {/* LO card */}
      {loadingLO && !lo && (
        <div className="smart-cal__lo-card smart-cal__lo-card--loading">
          <div className="smart-cal__lo-avatar smart-cal__lo-avatar--skeleton" />
          <div className="smart-cal__lo-info">
            <span className="smart-cal__lo-name smart-cal__skeleton-text" style={{ width: 160 }} />
            <span className="smart-cal__lo-role smart-cal__skeleton-text" style={{ width: 200 }} />
          </div>
        </div>
      )}
      {lo && (
        <div className="smart-cal__lo-card">
          {lo.avatar_url ? (
            <img src={lo.avatar_url} alt="" className="smart-cal__lo-avatar" />
          ) : (
            <span className="smart-cal__lo-avatar smart-cal__lo-avatar--initials">
              {initials(lo.name)}
            </span>
          )}
          <div className="smart-cal__lo-info">
            <span className="smart-cal__lo-name">{lo.name}</span>
            <span className="smart-cal__lo-role">
              Loan Officer{lo.nmls ? ` · NMLS #${lo.nmls}` : ''} · {MEETING_TYPE_LABELS[meetingType]}
            </span>
          </div>
          {onClose && (
            <button type="button" className="smart-cal__close" onClick={onClose} aria-label="Close">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
        </div>
      )}

      {/* Date chips */}
      <div className="smart-cal__section">
        <div className="smart-cal__section-title">Pick a date & time</div>
        <div className="smart-cal__chips">
          {weekOffset > minWeekOffset && (
            <button
              type="button"
              className="smart-cal__chip smart-cal__chip--nav"
              onClick={() => setWeekOffset(w => w - 1)}
              aria-label="Previous week"
            >
              &#8249;
            </button>
          )}
          {weekDays.map(day => {
            const key = day.toISOString().slice(0, 10);
            const isSelected = selectedDate === key;
            const isPast = day < new Date(new Date().toDateString());
            const hasSlots = datesWithSlots.has(key);
            return (
              <button
                key={key}
                type="button"
                className={`smart-cal__chip${isSelected ? ' is-selected' : ''}${isPast || !hasSlots ? ' is-disabled' : ''}`}
                onClick={() => handleDateSelect(day)}
                disabled={isPast}
                aria-label={`${day.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}${!hasSlots && !isPast ? ' — no available times' : ''}`}
              >
                {day.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
              </button>
            );
          })}
          {weekOffset < 3 && (
            <button
              type="button"
              className="smart-cal__chip smart-cal__chip--nav"
              onClick={() => setWeekOffset(w => w + 1)}
              aria-label="Next week"
            >
              &#8250;
            </button>
          )}
        </div>
      </div>

      {/* Time chips */}
      {selectedDate && (
        <div className="smart-cal__section">
          {loadingSlots ? (
            <div className="smart-cal__loading-text">Loading times...</div>
          ) : timesForSelectedDate.length === 0 ? (
            <div className="smart-cal__empty-text">No available times for this date. Try another day.</div>
          ) : (
            <div className="smart-cal__chips">
              {timesForSelectedDate.map((slot) => {
                const isSelected = selectedSlotStart === slot.start;
                const tz = slots?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
                return (
                  <button
                    key={slot.start}
                    type="button"
                    className={`smart-cal__chip smart-cal__chip--time${isSelected ? ' is-selected' : ''}${!slot.is_available ? ' is-disabled' : ''}`}
                    onClick={() => handleTimeSelect(slot)}
                    disabled={!slot.is_available}
                    aria-label={`${formatTime(slot.start, tz)} to ${formatTime(slot.end, tz)}${slot.is_recommended ? ' — recommended' : ''}${!slot.is_available ? ' — unavailable' : ''}`}
                  >
                    {formatTime(slot.start, tz)}
                    {slot.is_recommended && <span className="smart-cal__chip-star">&#9733;</span>}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Summary line */}
      {selectedSlot && (
        <div className="smart-cal__summary">
          Phone call with {loName} · {summaryParts.join(' ')} · {durationMin} min
        </div>
      )}

      {/* Submit — only visible when a slot is selected */}
      {selectedSlot && (
        <button
          type="button"
          className="smart-cal__submit"
          onClick={handleSubmit}
          disabled={busy}
        >
          {busy ? 'Booking...' : 'Confirm & schedule'}
        </button>
      )}

      {error && (
        <div className="smart-cal__error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="smart-cal__error-retry"
            onClick={() => {
              loadSlots();
              setSelectedSlotStart(null);
            }}
          >
            Refresh times
          </button>
        </div>
      )}
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
