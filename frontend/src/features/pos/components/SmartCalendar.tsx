/**
 * SmartCalendar — Step 9 booking widget.
 *
 * Mounted by the ReviewPanel. Lets the borrower pick a slot from the
 * assigned LO's calendar, hold it for 5 minutes, then confirm the booking.
 * On success, the confirmation dialog displays `next_steps` from the
 * BookingResponse and emits an `onBooked` callback so the parent can
 * stash the appointment_id for the submit call.
 */
import React, { useEffect, useMemo, useState } from 'react';

import { useSmartCalendar } from '../hooks/useSmartCalendar';
import type { BookingResponse, MeetingType, TimeSlot } from '../types';

export interface SmartCalendarProps {
  applicationId: string;
  onBooked?: (booking: BookingResponse) => void;
  defaultMeetingType?: MeetingType;
}

const MEETING_TYPE_LABELS: Record<MeetingType, string> = {
  checkin: 'Quick check-in (15 min)',
  application_review: 'Application review (30 min)',
  full_consultation: 'Full consultation (60 min)',
};

export const SmartCalendar: React.FC<SmartCalendarProps> = ({
  applicationId,
  onBooked,
  defaultMeetingType = 'application_review',
}) => {
  const {
    lo,
    slots,
    hold,
    holdSecondsRemaining,
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
  const [notes, setNotes] = useState('');

  // Initial load.
  useEffect(() => {
    loadLO();
    loadSlots();
  }, [loadLO, loadSlots]);

  // Auto-select recommended slot once slots arrive.
  useEffect(() => {
    if (slots?.recommended_slot && !selectedSlot) {
      setSelectedSlot(slots.recommended_slot);
    }
  }, [slots, selectedSlot]);

  // Bubble up the booking once it's confirmed.
  useEffect(() => {
    if (booking && onBooked) onBooked(booking);
  }, [booking, onBooked]);

  const orderedDates = useMemo(() => {
    if (!slots) return [];
    return Object.keys(slots.slots_by_date).sort();
  }, [slots]);

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
              <a href={booking.ics_link} download>
                Download .ics
              </a>
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
        <div className="smart-cal__lo">
          {lo.avatar_url ? (
            <img src={lo.avatar_url} alt="" className="smart-cal__avatar" />
          ) : (
            <div className="smart-cal__avatar smart-cal__avatar--initials" aria-hidden>
              {initials(lo.name)}
            </div>
          )}
          <div>
            <p className="smart-cal__lo-label">Booking with</p>
            <p className="smart-cal__lo-name">
              <strong>{lo.name}</strong>
              {lo.nmls && <span className="smart-cal__nmls"> · NMLS #{lo.nmls}</span>}
            </p>
          </div>
        </div>

        <select
          className="smart-cal__meeting-type"
          value={meetingType}
          onChange={e => {
            setMeetingType(e.target.value as MeetingType);
            const dur = e.target.value === 'checkin' ? 15 : e.target.value === 'full_consultation' ? 60 : 30;
            loadSlots(undefined, dur);
            setSelectedSlot(null);
          }}
        >
          {Object.entries(MEETING_TYPE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      </header>

      {loadingSlots ? (
        <div className="smart-cal__loading">Loading available times…</div>
      ) : orderedDates.length === 0 ? (
        <div className="smart-cal__empty">
          No times available in the next two weeks. Please reach out to{' '}
          {lo.name.split(' ')[0]} directly.
        </div>
      ) : (
        <div className="smart-cal__grid">
          {orderedDates.map(dateKey => (
            <DateColumn
              key={dateKey}
              dateKey={dateKey}
              slots={slots!.slots_by_date[dateKey]}
              timezone={slots!.timezone}
              selectedSlot={selectedSlot}
              onPick={setSelectedSlot}
            />
          ))}
        </div>
      )}

      {selectedSlot && (
        <div className="smart-cal__commit">
          <p className="smart-cal__selected">
            <strong>{formatDateTime(selectedSlot.start, slots!.timezone)}</strong>
            {hold && holdSecondsRemaining !== null && (
              <span className="smart-cal__hold-timer">
                {' '}· Held for {formatCountdown(holdSecondsRemaining)}
              </span>
            )}
          </p>

          <textarea
            className="smart-cal__notes"
            placeholder={`Anything you'd like ${lo.name.split(' ')[0]} to know ahead of the meeting? (optional)`}
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={2}
            maxLength={2000}
          />

          <div className="smart-cal__actions">
            <button
              type="button"
              className="smart-cal__btn smart-cal__btn--secondary"
              onClick={() => {
                releaseHold();
                setSelectedSlot(null);
              }}
              disabled={busy}
            >
              Pick a different time
            </button>
            <button
              type="button"
              className="smart-cal__btn smart-cal__btn--primary"
              onClick={async () => {
                if (!hold) await holdSlot(selectedSlot);
                await bookSlot(selectedSlot, meetingType, notes);
              }}
              disabled={busy}
            >
              {busy ? 'Booking…' : 'Confirm booking'}
            </button>
          </div>
        </div>
      )}

      {error && <p className="smart-cal__error">{error}</p>}
    </div>
  );
};

// ---------- DateColumn ----------

const DateColumn: React.FC<{
  dateKey: string;
  slots: TimeSlot[];
  timezone: string;
  selectedSlot: TimeSlot | null;
  onPick: (slot: TimeSlot) => void;
}> = ({ dateKey, slots, timezone, selectedSlot, onPick }) => {
  const date = new Date(dateKey + 'T12:00:00');
  return (
    <div className="smart-cal__col">
      <div className="smart-cal__col-header">
        <p className="smart-cal__col-day">
          {date.toLocaleDateString(undefined, { weekday: 'short' })}
        </p>
        <p className="smart-cal__col-date">
          {date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
        </p>
      </div>
      <ul className="smart-cal__col-slots">
        {slots.map((slot, i) => {
          const isSelected =
            selectedSlot !== null && selectedSlot.start === slot.start;
          const cls = [
            'smart-cal__slot',
            isSelected ? 'is-selected' : '',
            slot.is_recommended ? 'is-recommended' : '',
          ]
            .filter(Boolean)
            .join(' ');
          return (
            <li key={i}>
              <button type="button" className={cls} onClick={() => onPick(slot)}>
                {formatTime(slot.start, timezone)}
                {slot.is_recommended && <span className="smart-cal__rec-dot" aria-label="Recommended" />}
              </button>
            </li>
          );
        })}
      </ul>
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

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}
