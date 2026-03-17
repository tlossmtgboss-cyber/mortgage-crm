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

const DEFAULT_COLOR = '#1a73e8';

const API_BASE_DEFAULT =
  typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
    : 'https://api.perenniaai.com';

// US phone regex
const PHONE_REGEX = /^(\+1\s?)?(\(\d{3}\)|\d{3})[\s\-.]?\d{3}[\s\-.]?\d{4}$/;

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
      const response = await fetch(
        `${apiBase}/api/v1/scheduler/public/book/${slug}/slots?date=${dateStr}&appointment_type_id=${selectedType.id}&duration_minutes=${selectedType.default_duration_minutes || 30}`
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
    if (form.phone && !PHONE_REGEX.test(form.phone.trim())) errors.phone = 'Invalid phone';
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

  // ---- Date helpers ----
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
    return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  }

  function formatDayShort(date) {
    return date.toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase();
  }

  function formatFullDate(date) {
    return date.toLocaleDateString(undefined, {
      weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    });
  }

  function isPast(date) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date < today;
  }

  function isToday(date) {
    return date.toDateString() === new Date().toDateString();
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
    <div ref={containerRef} style={styles.container}>
      <style>{`
        @keyframes widget-shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>

      {/* Loading */}
      {loading && <WidgetSkeleton color={accentColor} />}

      {/* Error state (no config) */}
      {!loading && error && !config && (
        <div style={styles.errorContainer}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2">
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
                  <img src={config.lo.headshot_url} alt={config.lo.name} style={styles.loPhoto} />
                )}
                <div>
                  <div style={styles.loName}>{config.lo.name}</div>
                  {config.lo.title && <div style={styles.loTitle}>{config.lo.title}</div>}
                  {config.lo.nmls && <div style={styles.loNmls}>NMLS# {config.lo.nmls}</div>}
                </div>
              </div>
            )}
            <h3 style={styles.title}>Schedule a Meeting</h3>
          </div>

          {/* Inline error banner */}
          {error && (
            <div style={styles.errorBanner}>{error}</div>
          )}

          {/* Step: Date/Time selection */}
          {step === 'datetime' && (
            <div>
              {/* Appointment type selector */}
              {appointmentTypes.length > 1 && (
                <div style={styles.section}>
                  <label style={styles.label}>Appointment Type</label>
                  <div style={styles.typePills}>
                    {appointmentTypes.map(t => (
                      <button
                        key={t.id}
                        onClick={() => setSelectedType(t)}
                        style={{
                          ...styles.typePill,
                          ...(selectedType?.id === t.id ? styles.typePillActive : {}),
                        }}
                      >
                        {t.type_name}
                        <span style={styles.typeDuration}>{t.default_duration_minutes}m</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Date picker */}
              <div style={styles.section}>
                <label style={styles.label}>Select a Date</label>
                <div style={styles.weekNav}>
                  <button
                    onClick={prevWeek}
                    disabled={isPast(weekDates[0])}
                    style={styles.navBtn}
                    aria-label="Previous week"
                  >
                    &lsaquo;
                  </button>
                  <div style={styles.weekDates}>
                    {weekDates.map((date, idx) => {
                      const disabled = isPast(date);
                      const selected = selectedDate && date.toDateString() === selectedDate.toDateString();
                      return (
                        <button
                          key={idx}
                          onClick={() => !disabled && setSelectedDate(date)}
                          disabled={disabled}
                          style={{
                            ...styles.dateCard,
                            ...(selected ? { ...styles.dateCardSelected, backgroundColor: accentColor, borderColor: accentColor } : {}),
                            ...(disabled ? styles.dateCardDisabled : {}),
                            ...(isToday(date) && !selected ? styles.dateCardToday : {}),
                          }}
                          aria-label={date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
                        >
                          <span style={styles.dayName}>{formatDayShort(date)}</span>
                          <span style={{
                            ...styles.dayNumber,
                            ...(selected ? { color: '#fff' } : {}),
                          }}>{date.getDate()}</span>
                        </button>
                      );
                    })}
                  </div>
                  <button onClick={nextWeek} style={styles.navBtn} aria-label="Next week">
                    &rsaquo;
                  </button>
                </div>
              </div>

              {/* Time slot picker */}
              <div style={styles.section}>
                <label style={styles.label}>Select a Time</label>
                {availableSlots.length === 0 ? (
                  <p style={styles.noSlots}>No available times for this date.</p>
                ) : (
                  <div style={styles.timeGrid}>
                    {availableSlots.map((slot, idx) => {
                      const selected = selectedTime === slot.start_time;
                      return (
                        <button
                          key={idx}
                          onClick={() => setSelectedTime(slot.start_time)}
                          style={{
                            ...styles.timeSlot,
                            ...(selected ? { ...styles.timeSlotSelected, backgroundColor: accentColor, borderColor: accentColor } : {}),
                          }}
                        >
                          {slot.display}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <button
                onClick={() => setStep('form')}
                disabled={!selectedDate || !selectedTime}
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
            <div>
              <button
                onClick={() => { setStep('datetime'); setError(null); }}
                style={styles.backLink}
              >
                &lsaquo; Back
              </button>

              {selectedDate && selectedTime && (
                <div style={styles.summaryBadge}>
                  {selectedDate.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                  {' at '}
                  {formatTime(selectedTime)}
                  {selectedType ? ` - ${selectedType.type_name}` : ''}
                </div>
              )}

              <form onSubmit={handleSubmit} style={styles.form}>
                <div style={styles.formRow}>
                  <div style={styles.formGroup}>
                    <label style={styles.formLabel}>First Name *</label>
                    <input
                      type="text"
                      value={form.first_name}
                      onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                      placeholder="Jane"
                      style={{
                        ...styles.input,
                        ...(formErrors.first_name ? styles.inputError : {}),
                      }}
                      required
                    />
                    {formErrors.first_name && <span style={styles.fieldError}>{formErrors.first_name}</span>}
                  </div>
                  <div style={styles.formGroup}>
                    <label style={styles.formLabel}>Last Name *</label>
                    <input
                      type="text"
                      value={form.last_name}
                      onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                      placeholder="Doe"
                      style={{
                        ...styles.input,
                        ...(formErrors.last_name ? styles.inputError : {}),
                      }}
                      required
                    />
                    {formErrors.last_name && <span style={styles.fieldError}>{formErrors.last_name}</span>}
                  </div>
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.formLabel}>Email *</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    placeholder="jane@email.com"
                    style={{
                      ...styles.input,
                      ...(formErrors.email ? styles.inputError : {}),
                    }}
                    required
                  />
                  {formErrors.email && <span style={styles.fieldError}>{formErrors.email}</span>}
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.formLabel}>Phone</label>
                  <input
                    type="tel"
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    placeholder="(555) 555-5555"
                    style={{
                      ...styles.input,
                      ...(formErrors.phone ? styles.inputError : {}),
                    }}
                  />
                  {formErrors.phone && <span style={styles.fieldError}>{formErrors.phone}</span>}
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.formLabel}>Notes</label>
                  <textarea
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    placeholder="Anything we should know?"
                    rows={2}
                    maxLength={500}
                    style={styles.textarea}
                  />
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  style={{
                    ...styles.primaryBtn,
                    backgroundColor: submitting ? '#ccc' : accentColor,
                    cursor: submitting ? 'wait' : 'pointer',
                  }}
                >
                  {submitting ? 'Scheduling...' : 'Schedule Appointment'}
                </button>
              </form>
            </div>
          )}

          {/* Step: Confirmation */}
          {step === 'confirmation' && confirmedBooking && (
            <div style={styles.confirmContainer}>
              <div style={{ ...styles.checkCircle, borderColor: accentColor }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={accentColor} strokeWidth="3">
                  <path d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 style={styles.confirmTitle}>Appointment Confirmed</h3>
              <p style={styles.confirmSubtitle}>A confirmation email has been sent.</p>

              <div style={styles.confirmDetails}>
                <div style={styles.confirmRow}>
                  <span style={styles.confirmLabel}>Date</span>
                  <span style={styles.confirmValue}>{formatFullDate(confirmedBooking.date)}</span>
                </div>
                <div style={styles.confirmRow}>
                  <span style={styles.confirmLabel}>Time</span>
                  <span style={styles.confirmValue}>{formatTime(confirmedBooking.time)}</span>
                </div>
                {confirmedBooking.type && (
                  <div style={styles.confirmRow}>
                    <span style={styles.confirmLabel}>Type</span>
                    <span style={styles.confirmValue}>{confirmedBooking.type.type_name}</span>
                  </div>
                )}
              </div>

              <button
                onClick={() => {
                  setStep('datetime');
                  setConfirmedBooking(null);
                  setForm({ first_name: '', last_name: '', email: '', phone: '', notes: '' });
                  setSelectedTime('');
                }}
                style={{
                  ...styles.secondaryBtn,
                  borderColor: accentColor,
                  color: accentColor,
                }}
              >
                Schedule Another
              </button>
            </div>
          )}

          {/* Footer */}
          <div style={styles.footer}>
            <a
              href="https://perenniaai.com"
              target="_blank"
              rel="noopener noreferrer"
              style={styles.footerLink}
            >
              Powered by <strong>Perennia AI</strong>
            </a>
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================================
// Inline styles (no external CSS dependency for embeddability)
// ============================================================================
function buildStyles(color, darken) {
  return {
    container: {
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      maxWidth: '420px',
      width: '100%',
      background: '#ffffff',
      borderRadius: '12px',
      boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
      overflow: 'hidden',
      fontSize: '14px',
      lineHeight: '1.5',
      color: '#1a1a1a',
      boxSizing: 'border-box',
    },
    header: {
      padding: '20px 20px 16px',
      borderBottom: '1px solid #f0f0f0',
      textAlign: 'center',
    },
    logo: {
      maxHeight: '40px',
      maxWidth: '160px',
      objectFit: 'contain',
      marginBottom: '12px',
    },
    loInfo: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      justifyContent: 'center',
      marginBottom: '12px',
    },
    loPhoto: {
      width: '48px',
      height: '48px',
      borderRadius: '50%',
      objectFit: 'cover',
    },
    loName: {
      fontWeight: '600',
      fontSize: '15px',
      textAlign: 'left',
    },
    loTitle: {
      fontSize: '12px',
      color: '#666',
      textAlign: 'left',
    },
    loNmls: {
      fontSize: '11px',
      color: '#999',
      textAlign: 'left',
    },
    title: {
      margin: '0',
      fontSize: '18px',
      fontWeight: '600',
      color: '#1a1a1a',
    },
    section: {
      padding: '0 20px',
      marginBottom: '16px',
    },
    label: {
      display: 'block',
      fontSize: '13px',
      fontWeight: '600',
      color: '#555',
      marginBottom: '8px',
    },
    // Appointment type pills
    typePills: {
      display: 'flex',
      gap: '8px',
      flexWrap: 'wrap',
    },
    typePill: {
      padding: '8px 14px',
      borderRadius: '20px',
      border: '1px solid #ddd',
      background: '#fff',
      cursor: 'pointer',
      fontSize: '13px',
      fontWeight: '500',
      color: '#333',
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      transition: 'all 0.15s ease',
    },
    typePillActive: {
      borderColor: color,
      background: `${color}12`,
      color: color,
    },
    typeDuration: {
      fontSize: '11px',
      color: '#999',
    },
    // Week date picker
    weekNav: {
      display: 'flex',
      alignItems: 'center',
      gap: '4px',
    },
    navBtn: {
      background: 'none',
      border: 'none',
      fontSize: '24px',
      cursor: 'pointer',
      color: '#666',
      padding: '4px 8px',
      borderRadius: '6px',
      lineHeight: '1',
    },
    weekDates: {
      display: 'flex',
      gap: '4px',
      flex: 1,
      justifyContent: 'center',
    },
    dateCard: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '8px 4px',
      borderRadius: '8px',
      border: '1px solid #e5e5e5',
      background: '#fff',
      cursor: 'pointer',
      minWidth: '44px',
      transition: 'all 0.15s ease',
    },
    dateCardSelected: {
      color: '#fff',
      border: '1px solid',
    },
    dateCardDisabled: {
      opacity: 0.35,
      cursor: 'default',
    },
    dateCardToday: {
      borderColor: color,
    },
    dayName: {
      fontSize: '10px',
      fontWeight: '600',
      color: 'inherit',
      letterSpacing: '0.5px',
    },
    dayNumber: {
      fontSize: '16px',
      fontWeight: '700',
      color: 'inherit',
    },
    // Time grid
    timeGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: '6px',
    },
    timeSlot: {
      padding: '10px 4px',
      borderRadius: '8px',
      border: '1px solid #e5e5e5',
      background: '#fff',
      cursor: 'pointer',
      fontSize: '13px',
      fontWeight: '500',
      textAlign: 'center',
      transition: 'all 0.15s ease',
      color: '#333',
    },
    timeSlotSelected: {
      color: '#fff',
    },
    noSlots: {
      textAlign: 'center',
      color: '#999',
      fontSize: '13px',
      padding: '16px 0',
    },
    // Primary button
    primaryBtn: {
      display: 'block',
      width: 'calc(100% - 40px)',
      margin: '16px 20px 0',
      padding: '12px',
      borderRadius: '8px',
      border: 'none',
      color: '#fff',
      fontSize: '15px',
      fontWeight: '600',
      cursor: 'pointer',
      transition: 'background-color 0.15s ease',
    },
    primaryBtnDisabled: {
      opacity: 0.5,
      cursor: 'default',
    },
    secondaryBtn: {
      display: 'block',
      width: 'calc(100% - 40px)',
      margin: '12px 20px 0',
      padding: '10px',
      borderRadius: '8px',
      border: '2px solid',
      background: '#fff',
      fontSize: '14px',
      fontWeight: '600',
      cursor: 'pointer',
      textAlign: 'center',
    },
    // Back link
    backLink: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      padding: '8px 20px',
      background: 'none',
      border: 'none',
      cursor: 'pointer',
      fontSize: '13px',
      color: '#666',
      fontWeight: '500',
    },
    // Summary badge
    summaryBadge: {
      margin: '0 20px 16px',
      padding: '10px 14px',
      borderRadius: '8px',
      background: '#f8f9fa',
      fontSize: '13px',
      fontWeight: '500',
      color: '#333',
      textAlign: 'center',
    },
    // Form
    form: {
      padding: '0 20px',
    },
    formRow: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '10px',
      marginBottom: '10px',
    },
    formGroup: {
      marginBottom: '10px',
    },
    formLabel: {
      display: 'block',
      fontSize: '12px',
      fontWeight: '600',
      color: '#555',
      marginBottom: '4px',
    },
    input: {
      width: '100%',
      padding: '10px 12px',
      borderRadius: '8px',
      border: '1px solid #ddd',
      fontSize: '14px',
      outline: 'none',
      transition: 'border-color 0.15s',
      boxSizing: 'border-box',
    },
    inputError: {
      borderColor: '#dc2626',
    },
    textarea: {
      width: '100%',
      padding: '10px 12px',
      borderRadius: '8px',
      border: '1px solid #ddd',
      fontSize: '14px',
      outline: 'none',
      resize: 'vertical',
      fontFamily: 'inherit',
      boxSizing: 'border-box',
    },
    fieldError: {
      fontSize: '11px',
      color: '#dc2626',
      marginTop: '2px',
    },
    // Confirmation
    confirmContainer: {
      padding: '24px 20px',
      textAlign: 'center',
    },
    checkCircle: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: '56px',
      height: '56px',
      borderRadius: '50%',
      border: '3px solid',
      marginBottom: '12px',
    },
    confirmTitle: {
      margin: '0 0 4px',
      fontSize: '18px',
      fontWeight: '700',
    },
    confirmSubtitle: {
      margin: '0 0 16px',
      fontSize: '13px',
      color: '#666',
    },
    confirmDetails: {
      background: '#f8f9fa',
      borderRadius: '8px',
      padding: '14px 16px',
      marginBottom: '4px',
      textAlign: 'left',
    },
    confirmRow: {
      display: 'flex',
      justifyContent: 'space-between',
      padding: '4px 0',
      fontSize: '13px',
    },
    confirmLabel: {
      color: '#666',
      fontWeight: '500',
    },
    confirmValue: {
      fontWeight: '600',
      color: '#1a1a1a',
    },
    // Error
    errorContainer: {
      padding: '40px 20px',
      textAlign: 'center',
    },
    errorText: {
      color: '#666',
      marginTop: '12px',
      fontSize: '14px',
    },
    errorBanner: {
      margin: '8px 20px',
      padding: '10px 14px',
      borderRadius: '8px',
      background: '#fef2f2',
      color: '#dc2626',
      fontSize: '13px',
    },
    // Footer
    footer: {
      padding: '12px 20px 16px',
      textAlign: 'center',
      borderTop: '1px solid #f0f0f0',
      marginTop: '16px',
    },
    footerLink: {
      fontSize: '11px',
      color: '#999',
      textDecoration: 'none',
    },
  };
}

export { BookingWidget, WidgetSkeleton };
