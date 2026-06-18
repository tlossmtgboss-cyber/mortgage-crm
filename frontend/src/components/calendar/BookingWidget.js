/**
 * BookingWidget - Self-contained, embeddable booking widget for LO websites.
 *
 * Compact design that fits in a sidebar, popup, or iframe embed.
 * Communicates with parent page via postMessage for height changes
 * and booking completion events.
 *
 * Props:
 *   orgSlug     - Organization slug (required)
 *   loSlug      - Loan officer slug (optional)
 *   accentColor - Primary brand color (optional, default #1a73e8)
 *   apiBase     - API base URL override (optional)
 *   onBooked    - Callback when booking is confirmed (optional)
 *   embedded    - Whether running inside an iframe (default false)
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import BookingTypeSelector from './booking/BookingTypeSelector';
import BookingSlotPicker from './booking/BookingSlotPicker';
import BookingForm from './booking/BookingForm';
import BookingWidgetConfirmation from './booking/BookingWidgetConfirmation';
import { getUserTimezone } from './calendarUtils';
import { buildStyles } from './bookingWidgetStyles';

const DEFAULT_COLOR = '#1a73e8';

const API_BASE_DEFAULT =
  typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
    : 'https://api.perenniaai.com';

// Accept US format (+1...) and basic international format (+XX...)
const PHONE_REGEX = /^(\+\d{1,3}\s?)?(\(?\d{1,4}\)?[\s\-.]?){1,4}\d{1,4}$/;

// ============================================================================
// Loading skeleton shown while widget initializes
// ============================================================================
function WidgetSkeleton({ color }) {
  const skeletonStyle = {
    background: `linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)`,
    backgroundSize: '200% 100%',
    animation: 'widget-shimmer 1.5s infinite',
    borderRadius: '6px',
  };

  return (
    <div style={{ padding: '20px' }}>
      <div style={{ ...skeletonStyle, height: '24px', width: '60%', marginBottom: '16px' }} />
      <div style={{ ...skeletonStyle, height: '16px', width: '80%', marginBottom: '24px' }} />
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        {[1, 2, 3].map(i => (
          <div key={i} style={{ ...skeletonStyle, height: '36px', flex: 1 }} />
        ))}
      </div>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '20px' }}>
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} style={{ ...skeletonStyle, height: '48px', width: '56px' }} />
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '16px' }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} style={{ ...skeletonStyle, height: '36px' }} />
        ))}
      </div>
      <div style={{ ...skeletonStyle, height: '42px', marginTop: '16px' }} />
    </div>
  );
}

// ============================================================================
// Main BookingWidget component
// ============================================================================
export default function BookingWidget({
  orgSlug,
  loSlug,
  accentColor: colorProp,
  apiBase: apiBaseProp,
  onBooked,
  embedded = false,
}) {
  const apiBase = apiBaseProp || API_BASE_DEFAULT;
  const containerRef = useRef(null);
  const stepContainerRef = useRef(null);

  // ---- State ----
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [config, setConfig] = useState(null);
  const [accentColor, setAccentColor] = useState(colorProp || DEFAULT_COLOR);

  // Booking flow
  const [step, setStep] = useState('datetime'); // datetime | form | confirmation
  const [appointmentTypes, setAppointmentTypes] = useState([]);
  const [selectedType, setSelectedType] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [weekStart, setWeekStart] = useState(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [availableSlots, setAvailableSlots] = useState([]);
  const [selectedTime, setSelectedTime] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [confirmedBooking, setConfirmedBooking] = useState(null);

  // Form fields
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    notes: '',
  });
  const [formErrors, setFormErrors] = useState({});

  // ---- postMessage helper for iframe embeds ----
  const postToParent = useCallback((type, data = {}) => {
    if (embedded && window.parent !== window) {
      window.parent.postMessage(
        { source: 'perennia-booking-widget', type, ...data },
        '*'
      );
    }
  }, [embedded]);

  // ---- Auto-resize: notify parent of height changes ----
  useEffect(() => {
    if (!embedded || !containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        postToParent('resize', { height: entry.contentRect.height + 24 });
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [embedded, postToParent]);

  // ---- Focus restoration when step changes ----
  useEffect(() => {
    if (stepContainerRef.current) {
      const focusTarget = stepContainerRef.current.querySelector('h2, h3, input, button');
      if (focusTarget) {
        focusTarget.focus();
      }
    }
  }, [step]);

  // ---- Fetch widget configuration ----
  useEffect(() => {
    if (!orgSlug) {
      setError('Organization slug is required.');
      setLoading(false);
      return;
    }

    const fetchConfig = async () => {
      try {
        setLoading(true);
        const url = loSlug
          ? `${apiBase}/api/v1/scheduler/widget/config/${orgSlug}/${loSlug}`
          : `${apiBase}/api/v1/scheduler/widget/config/${orgSlug}`;
        const response = await fetch(url);
        if (!response.ok) {
          if (response.status === 404) {
            setError('This booking page is not available.');
          } else {
            setError('Unable to load booking options. Please try again.');
          }
          return;
        }
        const data = await response.json();
        setConfig(data);

        // Apply branding color from server if no override prop
        if (!colorProp && data.branding?.primary_color) {
          setAccentColor(data.branding.primary_color);
        }

        // Set appointment types
        const types = data.appointment_types || [];
        setAppointmentTypes(types);
        if (types.length > 0) {
          setSelectedType(types[0]);
        }

        // Set initial date
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (today.getDay() === 0 || today.getDay() === 6) {
          const monday = new Date(today);
          monday.setDate(today.getDate() + ((8 - today.getDay()) % 7));
          setWeekStart(monday);
          setSelectedDate(monday);
        } else {
          setSelectedDate(today);
        }

        setError(null);
      } catch (err) {
        setError('Unable to connect to booking service.');
      } finally {
        setLoading(false);
      }
    };

    fetchConfig();
  }, [orgSlug, loSlug, apiBase, colorProp]);

  // ---- Fetch available slots when date/type changes ----
  const fetchSlots = useCallback(async () => {
    if (!selectedType || !selectedDate || !config?.booking_slug) return;
    try {
      const dateStr = selectedDate.toISOString().split('T')[0];
      const slug = config.booking_slug;
      const tz = getUserTimezone();
      const response = await fetch(
        `${apiBase}/api/v1/scheduler/public/book/${slug}/slots?date=${dateStr}&appointment_type_id=${selectedType.id}&duration_minutes=${selectedType.default_duration_minutes || 30}&timezone=${encodeURIComponent(tz)}`
      );
      if (response.ok) {
        const data = await response.json();
        const slots = (data.available_slots || []).map(slot => ({
          ...slot,
          start_time: slot.start,
          display: formatTime(slot.start),
        }));
        setAvailableSlots(slots);
        if (slots.length > 0) {
          setSelectedTime(slots[0].start_time);
        } else {
          setSelectedTime('');
        }
      } else {
        setAvailableSlots([]);
        setSelectedTime('');
      }
    } catch (err) {
      setAvailableSlots([]);
      setSelectedTime('');
    }
  }, [selectedType, selectedDate, config, apiBase]);

  useEffect(() => {
    if (selectedType && selectedDate) {
      fetchSlots();
    }
  }, [selectedType, selectedDate, fetchSlots]);

  // ---- Submit booking ----
  const handleSubmit = async (e) => {
    e.preventDefault();
    const errors = {};
    if (!form.first_name.trim()) errors.first_name = 'Required';
    if (!form.last_name.trim()) errors.last_name = 'Required';
    if (!form.email.trim()) errors.email = 'Required';
    if (form.phone && !PHONE_REGEX.test(form.phone.trim())) errors.phone = 'Enter a valid phone number';
    if (!selectedTime) errors.time = 'Please select a time';

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    setSubmitting(true);
    setError(null);

    try {
      const body = {
        appointment_type_id: selectedType.id,
        start_time: selectedTime,
        duration_minutes: selectedType.default_duration_minutes || 30,
        attendee_name: `${form.first_name} ${form.last_name}`,
        attendee_email: form.email,
        attendee_phone: form.phone,
        notes: form.notes,
        meeting_mode: 'phone',
      };

      const slug = config.booking_slug;
      const response = await fetch(`${apiBase}/api/v1/scheduler/public/book/${slug}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        throw new Error('Booking failed');
      }

      const result = await response.json();
      const booking = {
        id: result.appointment_id,
        date: selectedDate,
        time: selectedTime,
        type: selectedType,
      };
      setConfirmedBooking(booking);
      setStep('confirmation');

      // Notify parent page
      postToParent('booked', {
        appointmentId: result.appointment_id,
        date: selectedDate.toISOString().split('T')[0],
        time: selectedTime,
        type: selectedType.type_name,
      });

      if (onBooked) {
        onBooked(booking);
      }
    } catch (err) {
      setError('Unable to complete booking. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // ---- Date / week helpers ----
  function getWeekDates() {
    const dates = [];
    const start = new Date(weekStart);
    start.setHours(0, 0, 0, 0);
    for (let i = 0; i < 7; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      dates.push(d);
    }
    return dates;
  }

  function formatTime(timeStr) {
    const d = new Date(timeStr);
    const tz = getUserTimezone();
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: tz });
  }

  function formatFullDate(date) {
    const tz = getUserTimezone();
    return date.toLocaleDateString('en-US', {
      weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: tz,
    });
  }

  const prevWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(weekStart.getDate() - 7);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    if (newStart >= today) setWeekStart(newStart);
  };

  const nextWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(weekStart.getDate() + 7);
    setWeekStart(newStart);
  };

  const handleScheduleAnother = () => {
    setStep('datetime');
    setConfirmedBooking(null);
    setForm({ first_name: '', last_name: '', email: '', phone: '', notes: '' });
    setSelectedTime('');
  };

  const weekDates = getWeekDates();

  // ---- Dynamic styles ----
  const darken = (hex, amount = 25) => {
    const num = parseInt(hex.replace('#', ''), 16);
    const r = Math.max(0, (num >> 16) - amount);
    const g = Math.max(0, ((num >> 8) & 0x00ff) - amount);
    const b = Math.max(0, (num & 0x0000ff) - amount);
    return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
  };

  const styles = buildStyles(accentColor, darken);

  // ---- Render ----
  return (
    <div ref={containerRef} style={styles.container} role="region" aria-label="Appointment booking">
      <style>{`
        @keyframes widget-shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        .bw-sr-only {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
          border-width: 0;
        }
      `}</style>

      {/* Screen reader announcements for booking status */}
      <div aria-live="polite" className="bw-sr-only" role="status">
        {step === 'confirmation' && 'Your appointment has been confirmed.'}
        {error && `Error: ${error}`}
        {loading && 'Loading booking options, please wait.'}
      </div>

      {/* Loading */}
      {loading && (
        <div aria-busy="true">
          <WidgetSkeleton color={accentColor} />
        </div>
      )}

      {/* Error state (no config) */}
      {!loading && error && !config && (
        <div style={styles.errorContainer} role="alert">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <p style={styles.errorText}>{error}</p>
        </div>
      )}

      {/* Main widget content */}
      {!loading && config && (
        <>
          {/* Header */}
          <div style={styles.header}>
            {config.branding?.logo_url && (
              <img
                src={config.branding.logo_url}
                alt={config.branding?.org_name || 'Logo'}
                style={styles.logo}
              />
            )}
            {config.lo && (
              <div style={styles.loInfo}>
                {config.lo.headshot_url && (
                  <img src={config.lo.headshot_url} alt={`Photo of ${config.lo.name}`} style={styles.loPhoto} />
                )}
                <div>
                  <div style={styles.loName}>{config.lo.name}</div>
                  {config.lo.title && <div style={styles.loTitle}>{config.lo.title}</div>}
                  {config.lo.nmls && <div style={styles.loNmls}>NMLS# {config.lo.nmls}</div>}
                </div>
              </div>
            )}
            <h3 style={styles.title} id="bw-widget-title">Schedule a Meeting</h3>
          </div>

          {/* Inline error banner */}
          {error && (
            <div style={styles.errorBanner} role="alert">{error}</div>
          )}

          {/* Step content — ref used for focus restoration on step change */}
          <div ref={stepContainerRef}>
          {/* Step: Date/Time selection */}
          {step === 'datetime' && (
            <div>
              <BookingTypeSelector
                appointmentTypes={appointmentTypes}
                selectedType={selectedType}
                onSelect={setSelectedType}
                styles={styles}
                accentColor={accentColor}
              />

              <BookingSlotPicker
                weekDates={weekDates}
                selectedDate={selectedDate}
                onSelectDate={setSelectedDate}
                onPrevWeek={prevWeek}
                onNextWeek={nextWeek}
                availableSlots={availableSlots}
                selectedTime={selectedTime}
                onSelectTime={setSelectedTime}
                styles={styles}
                accentColor={accentColor}
              />

              <button
                onClick={() => setStep('form')}
                disabled={!selectedDate || !selectedTime}
                aria-label={
                  !selectedDate || !selectedTime
                    ? 'Continue (select a date and time first)'
                    : 'Continue to contact information'
                }
                style={{
                  ...styles.primaryBtn,
                  backgroundColor: accentColor,
                  ...((!selectedDate || !selectedTime) ? styles.primaryBtnDisabled : {}),
                }}
                onMouseOver={(e) => {
                  if (selectedDate && selectedTime) e.target.style.backgroundColor = darken(accentColor);
                }}
                onMouseOut={(e) => {
                  if (selectedDate && selectedTime) e.target.style.backgroundColor = accentColor;
                }}
              >
                Continue
              </button>
            </div>
          )}

          {/* Step: Contact form */}
          {step === 'form' && (
            <BookingForm
              form={form}
              onFormChange={setForm}
              formErrors={formErrors}
              onSubmit={handleSubmit}
              onBack={() => { setStep('datetime'); setError(null); }}
              submitting={submitting}
              selectedDate={selectedDate}
              selectedTime={selectedTime}
              selectedType={selectedType}
              formatTime={formatTime}
              styles={styles}
              accentColor={accentColor}
            />
          )}

          {/* Step: Confirmation */}
          {step === 'confirmation' && (
            <BookingWidgetConfirmation
              confirmedBooking={confirmedBooking}
              formatTime={formatTime}
              formatFullDate={formatFullDate}
              onScheduleAnother={handleScheduleAnother}
              styles={styles}
              accentColor={accentColor}
            />
          )}
          </div>

          {/* Footer */}
          <div style={styles.footer}>
            {config?.booking_page?.powered_by_text ? (
              <span style={styles.footerLink}>
                {config.booking_page.powered_by_text}
              </span>
            ) : (
              <a
                href="https://perenniaai.com"
                target="_blank"
                rel="noopener noreferrer"
                style={styles.footerLink}
              >
                Powered by <strong>Perennia AI</strong>
              </a>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export { BookingWidget, WidgetSkeleton };
