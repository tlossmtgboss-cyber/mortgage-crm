import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import useOrgBranding from '../hooks/useOrgBranding';
import { LanguageProvider, useTranslation } from '../i18n';
import LanguageSelector from '../components/calendar/LanguageSelector';
import './PublicBooking.css';

const TURNSTILE_SITE_KEY = process.env.REACT_APP_TURNSTILE_SITE_KEY;

// US phone: (XXX) XXX-XXXX, XXX-XXX-XXXX, or 10 digits with optional +1
const PHONE_REGEX = /^(\+1\s?)?(\(\d{3}\)|\d{3})[\s\-.]?\d{3}[\s\-.]?\d{4}$/;

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const PublicBookingInner = () => {
  const { t, locale } = useTranslation();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [slotsError, setSlotsError] = useState(false);
  const [phoneError, setPhoneError] = useState('');
  const [bookingLink, setBookingLink] = useState(null);
  const [appointmentTypes, setAppointmentTypes] = useState([]);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [selectedType, setSelectedType] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState('');
  const [meetingMode, setMeetingMode] = useState('video'); // 'video' or 'in_person'
  // Initialize weekStart to today with time set to midnight
  const [weekStart, setWeekStart] = useState(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [step, setStep] = useState('datetime'); // datetime, form, confirmation, manage
  const [submitting, setSubmitting] = useState(false);
  const [confirmedAppointment, setConfirmedAppointment] = useState(null);

  const [cancelConfirm, setCancelConfirm] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState('');
  const turnstileRef = useRef(null);
  const turnstileWidgetId = useRef(null);

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    notes: '',
    working_with_agent: null, // Custom question example
    custom_responses: {}
  });

  // Get slug from React Router params, with fallback for non-router contexts
  const routeParams = useParams();
  const slug = routeParams?.slug || window.location.pathname.split('/book/')[1]?.split('/')[0] || 'demo';

  // Extract org slug and LO slug from the URL path
  // Supports: /book/org/{orgSlug} and /book/org/{orgSlug}/lo/{loSlug}
  const pathParts = window.location.pathname.split('/');
  const orgIndex = pathParts.indexOf('org');
  const orgSlug = routeParams?.orgSlug || (orgIndex >= 0 ? pathParts[orgIndex + 1] : null);
  const loSlug = routeParams?.loSlug || (pathParts.indexOf('lo') >= 0 ? pathParts[pathParts.indexOf('lo') + 1] : null);

  // Fetch org branding via the hook (only active for org-branded booking URLs)
  const { branding, loading: brandingLoading } = useOrgBranding(orgSlug, loSlug);

  // Check if managing existing appointment
  const urlParams = new URLSearchParams(window.location.search);
  const appointmentId = urlParams.get('appointment');
  const action = urlParams.get('action'); // 'reschedule' or 'cancel'

  // Generate week dates starting from weekStart
  const getWeekDates = () => {
    const dates = [];
    const start = new Date(weekStart);
    start.setHours(0, 0, 0, 0);

    for (let i = 0; i < 7; i++) {
      const date = new Date(start);
      date.setDate(start.getDate() + i);
      dates.push(date);
    }
    return dates;
  };

  const weekDates = getWeekDates();

  // Format helpers — use locale from i18n context
  const formatDayName = (date) => {
    return date.toLocaleDateString(locale, { weekday: 'long' }).toUpperCase();
  };

  const formatDayNumber = (date) => {
    return date.getDate();
  };

  const formatMonth = (date) => {
    return date.toLocaleDateString(locale, { month: 'short' }).toUpperCase();
  };

  const formatFullDate = (date) => {
    return date.toLocaleDateString(locale, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  };

  // Accessible aria-label for date cards: "Monday, March 10"
  const formatDateAriaLabel = (date) => {
    return date.toLocaleDateString(locale, { weekday: 'long', month: 'long', day: 'numeric' });
  };

  // Phone validation helper
  const validatePhone = (value) => {
    if (!value || value.trim() === '') {
      setPhoneError('');
      return true; // Phone is optional
    }
    if (!PHONE_REGEX.test(value.trim())) {
      setPhoneError(t('booking.errorPhoneInvalid'));
      return false;
    }
    setPhoneError('');
    return true;
  };

  const formatTime = (timeStr) => {
    const date = new Date(timeStr);
    return date.toLocaleTimeString(locale, { hour: 'numeric', minute: '2-digit' });
  };

  const isToday = (date) => {
    const today = new Date();
    return date.toDateString() === today.toDateString();
  };

  const isPast = (date) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date < today;
  };

  // Fetch booking link info
  const fetchBookingLink = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/api/v1/scheduler/public/book/${slug}`);

      if (!response.ok) {
        if (response.status === 404) {
          setError(t('booking.errorLinkNotAvailable'));
        } else {
          setError(t('booking.errorLoadFailed'));
        }
        return;
      }

      const data = await response.json();
      setBookingLink(data.booking_page || data);
      const types = data.booking_page?.appointment_types || data.appointment_types || [];
      setAppointmentTypes(types);

      // Auto-select first type
      if (types.length > 0) {
        setSelectedType(types[0]);
      }

      // Set initial date to today or first available weekday
      const today = new Date();
      if (today.getDay() === 0 || today.getDay() === 6) {
        // If weekend, start from Monday
        const monday = new Date(today);
        monday.setDate(today.getDate() + (8 - today.getDay()) % 7);
        setWeekStart(monday);
        setSelectedDate(monday);
      } else {
        setSelectedDate(today);
      }

      setError(null);
    } catch (err) {
      setError(t('booking.errorConnectFailed'));
    } finally {
      setLoading(false);
    }
  }, [slug, t]);

  // Fetch available slots for selected date
  const fetchSlots = useCallback(async () => {
    if (!selectedType || !selectedDate) return;

    try {
      setSlotsError(false);
      const dateStr = selectedDate.toISOString().split('T')[0];
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/public/book/${slug}/slots?date=${dateStr}&appointment_type_id=${selectedType.id}&duration_minutes=${selectedType.default_duration_minutes || 30}`
      );

      if (response.ok) {
        const data = await response.json();
        const slots = (data.available_slots || []).map(slot => ({
          ...slot,
          start_time: slot.start,
          display: formatTime(slot.start)
        }));
        setAvailableSlots(slots);

        // Auto-select first available time for the new date
        if (slots.length > 0) {
          setSelectedTime(slots[0].start_time);
        } else {
          setSelectedTime('');
        }
      } else {
        setAvailableSlots([]);
        setSelectedTime('');
        setSlotsError(true);
      }
    } catch (err) {
      setAvailableSlots([]);
      setSelectedTime('');
      setSlotsError(true);
    }
  }, [slug, selectedType, selectedDate]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchBookingLink();
  }, [fetchBookingLink]);

  // Handle action URL parameter (e.g., ?appointment=123&action=cancel)
  useEffect(() => {
    if (appointmentId && action === 'cancel') {
      handleCancel(appointmentId);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selectedType && selectedDate) {
      fetchSlots();
    }
  }, [selectedType, selectedDate, fetchSlots]);

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!selectedType || !selectedTime) {
      setError(t('booking.errorSelectDateTime'));
      return;
    }

    if (!form.first_name || !form.last_name || !form.email) {
      setError(t('booking.errorRequiredFields'));
      return;
    }

    // Validate phone if provided
    if (form.phone && form.phone.trim() !== '' && !PHONE_REGEX.test(form.phone.trim())) {
      setPhoneError(t('booking.errorPhoneInvalid'));
      return;
    }

    if (TURNSTILE_SITE_KEY && !turnstileToken) {
      setError(t('booking.errorVerification'));
      return;
    }

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
        meeting_mode: meetingMode,
        custom_responses: {
          working_with_agent: form.working_with_agent,
          ...form.custom_responses
        }
      };

      if (TURNSTILE_SITE_KEY && turnstileToken) {
        body.cf_turnstile_token = turnstileToken;
      }

      const response = await fetch(`${API_BASE}/api/v1/scheduler/public/book/${slug}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        // Do not expose raw server error details to public users
        throw new Error('BOOKING_FAILED');
      }

      const result = await response.json();
      setConfirmedAppointment({
        id: result.appointment_id,
        date: selectedDate,
        time: selectedTime,
        type: selectedType,
        meetingMode: meetingMode
      });
      setStep('confirmation');
    } catch (err) {
      // Always show a safe, generic message to public users
      setError(t('booking.errorBookingFailed'));
      // Reset Turnstile widget so user can retry
      if (TURNSTILE_SITE_KEY && turnstileWidgetId.current !== null && window.turnstile) {
        try { window.turnstile.reset(turnstileWidgetId.current); } catch (e) { /* ignore */ }
        setTurnstileToken('');
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Cancel appointment
  const handleCancel = async (apptId) => {
    const idToCancel = apptId || confirmedAppointment?.id || appointmentId;
    if (!idToCancel) return;

    if (!cancelConfirm) {
      setCancelConfirm(true);
      return;
    }
    setCancelConfirm(false);

    try {
      setSubmitting(true);
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/appointments/${idToCancel}/cancel`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: 'Cancelled by attendee' })
        }
      );

      if (response.ok) {
        setStep('cancelled');
      } else {
        // Do not expose raw server error details to public users
        setError(t('booking.errorCancelFailed'));
      }
    } catch (err) {
      setError(t('booking.errorCancelRetry'));
    } finally {
      setSubmitting(false);
    }
  };

  // Navigate weeks
  const prevWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(weekStart.getDate() - 7);
    // Don't go before today
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    if (newStart >= today) {
      setWeekStart(newStart);
    }
  };

  const nextWeek = () => {
    const newStart = new Date(weekStart);
    newStart.setDate(weekStart.getDate() + 7);
    setWeekStart(newStart);
  };

  // Reset calendar to today when step changes to datetime (e.g., when going back)
  useEffect(() => {
    if (step === 'datetime') {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      setWeekStart(today);
    }
  }, [step]);

  // Load Cloudflare Turnstile script and render widget when form step is shown
  useEffect(() => {
    if (!TURNSTILE_SITE_KEY || step !== 'form') return;

    // Reset token when entering form step
    setTurnstileToken('');

    const renderWidget = () => {
      if (turnstileRef.current && window.turnstile) {
        // Remove previous widget if re-rendering
        if (turnstileWidgetId.current !== null) {
          try { window.turnstile.remove(turnstileWidgetId.current); } catch (e) { /* ignore */ }
        }
        turnstileWidgetId.current = window.turnstile.render(turnstileRef.current, {
          sitekey: TURNSTILE_SITE_KEY,
          callback: (token) => setTurnstileToken(token),
          'expired-callback': () => setTurnstileToken(''),
          'error-callback': () => setTurnstileToken(''),
        });
      }
    };

    // Check if script is already loaded
    if (window.turnstile) {
      renderWidget();
      return;
    }

    // Load the Turnstile API script
    const existingScript = document.querySelector('script[src*="challenges.cloudflare.com/turnstile"]');
    if (!existingScript) {
      const script = document.createElement('script');
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      script.onload = () => renderWidget();
      document.head.appendChild(script);
    } else {
      // Script tag exists but may still be loading
      existingScript.addEventListener('load', renderWidget);
    }

    return () => {
      if (turnstileWidgetId.current !== null && window.turnstile) {
        try { window.turnstile.remove(turnstileWidgetId.current); } catch (e) { /* ignore */ }
        turnstileWidgetId.current = null;
      }
    };
  }, [step]);

  // Branding-aware header: org logo, tagline, LO card
  const renderBrandingHeader = () => {
    if (!branding) return null;
    const hasOrgBranding = orgSlug && branding.org_name;

    return (
      <div className="booking-branding-header">
        {/* Org logo */}
        {hasOrgBranding && branding.logo_url && (
          <div className="booking-org-logo">
            <img src={branding.logo_url} alt={`${branding.org_name} logo`} />
          </div>
        )}

        {/* Org name (if no custom title from booking link) */}
        {hasOrgBranding && !bookingLink?.custom_title && (
          <div className="booking-org-name">{branding.org_name}</div>
        )}

        {/* Tagline */}
        {hasOrgBranding && branding.tagline && (
          <p className="booking-tagline">{branding.tagline}</p>
        )}

        {/* Welcome message */}
        {hasOrgBranding && branding.welcome_message && step === 'datetime' && (
          <p className="booking-welcome">{branding.welcome_message}</p>
        )}

        {/* LO card */}
        {branding.lo && (
          <div className="booking-lo-card">
            {branding.lo.photo_url && (
              <img
                src={branding.lo.photo_url}
                alt={branding.lo.name}
                className="booking-lo-photo"
              />
            )}
            <div className="booking-lo-info">
              <span className="booking-lo-name">{branding.lo.name}</span>
              {branding.lo.title && (
                <span className="booking-lo-title">{branding.lo.title}</span>
              )}
              {branding.lo.nmls && (
                <span className="booking-lo-nmls">NMLS# {branding.lo.nmls}</span>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  // Cover image background style
  const coverStyle = (orgSlug && branding?.cover_image_url)
    ? { backgroundImage: `linear-gradient(rgba(247,247,247,0.92), rgba(247,247,247,0.92)), url(${branding.cover_image_url})`, backgroundSize: 'cover', backgroundPosition: 'center' }
    : {};

  // Loading state
  if (loading || brandingLoading) {
    return (
      <div className="redfin-booking" style={coverStyle}>
        <div className="booking-container">
          <LanguageSelector />
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <p>{t('booking.loading')}</p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !bookingLink) {
    return (
      <div className="redfin-booking" style={coverStyle}>
        <div className="booking-container">
          <LanguageSelector />
          {renderBrandingHeader()}
          <div className="error-state">
            <h2>{t('booking.unavailable')}</h2>
            <p>{error}</p>
          </div>
          <div className="booking-footer">
            <p>{t('booking.poweredBy')} <strong>Perennia AI</strong></p>
          </div>
        </div>
      </div>
    );
  }

  // Confirmation state
  if (step === 'confirmation' && confirmedAppointment) {
    return (
      <div className="redfin-booking" style={coverStyle}>
        <div className="booking-container confirmation-container">
          <LanguageSelector />
          {renderBrandingHeader()}
          <div className="confirmation-header">
            <div className="success-checkmark">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" role="img" aria-label={t('confirmation.title')}>
                <path d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1>{t('confirmation.title')}</h1>
            <p>{t('confirmation.subtitle')}</p>
          </div>

          <div className="appointment-summary">
            <h3>{t('confirmation.details')}</h3>
            <div className="summary-row">
              <span className="label">{t('confirmation.date')}</span>
              <span className="value">{formatFullDate(confirmedAppointment.date)}</span>
            </div>
            <div className="summary-row">
              <span className="label">{t('confirmation.time')}</span>
              <span className="value">{formatTime(confirmedAppointment.time)}</span>
            </div>
            <div className="summary-row">
              <span className="label">{t('confirmation.type')}</span>
              <span className="value">{confirmedAppointment.type.type_name}</span>
            </div>
            <div className="summary-row">
              <span className="label">{t('confirmation.format')}</span>
              <span className="value">{confirmedAppointment.meetingMode === 'video' ? t('confirmation.videoCall') : t('confirmation.phoneCall')}</span>
            </div>
          </div>

          <div className="confirmation-actions">
            <button className="primary-button" onClick={() => window.location.href = '/'}>
              {t('confirmation.goHome')}
            </button>
            {cancelConfirm ? (
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                <button
                  className="secondary-button cancel-link"
                  onClick={() => handleCancel()}
                  disabled={submitting}
                  style={{ color: '#dc2626', borderColor: '#dc2626' }}
                >
                  {submitting ? t('confirmation.cancelling') : t('confirmation.yesCancel')}
                </button>
                <button
                  className="secondary-button"
                  onClick={() => setCancelConfirm(false)}
                >
                  {t('confirmation.nevermind')}
                </button>
              </div>
            ) : (
              <button
                className="secondary-button cancel-link"
                onClick={() => handleCancel()}
                disabled={submitting}
              >
                {t('confirmation.cancelAppointment')}
              </button>
            )}
          </div>

          {/* Footer - always shown */}
          <div className="booking-footer">
            <p>{t('booking.poweredBy')} <strong>Perennia AI</strong></p>
          </div>
        </div>
      </div>
    );
  }

  // Cancelled state
  if (step === 'cancelled') {
    return (
      <div className="redfin-booking" style={coverStyle}>
        <div className="booking-container confirmation-container">
          <LanguageSelector />
          {renderBrandingHeader()}
          <div className="confirmation-header">
            <div className="success-checkmark cancelled-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1>{t('cancelled.title')}</h1>
            <p>{t('cancelled.subtitle')}</p>
          </div>
          <button className="primary-button" onClick={() => { setStep('datetime'); setConfirmedAppointment(null); }}>
            {t('cancelled.bookNew')}
          </button>
          <div className="booking-footer">
            <p>{t('booking.poweredBy')} <strong>Perennia AI</strong></p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="redfin-booking" style={coverStyle}>
      <div className="booking-container">
        {/* Language Selector */}
        <LanguageSelector />

        {/* Org Branding Header */}
        {renderBrandingHeader()}

        {/* Booking Link Header */}
        {bookingLink && (
          <div className="booking-header">
            <h1>{bookingLink.custom_title || bookingLink.title || bookingLink.link_name || t('booking.scheduleAppointment')}</h1>
            {bookingLink.custom_description || bookingLink.description ? (
              <p>{bookingLink.custom_description || bookingLink.description}</p>
            ) : null}
          </div>
        )}

        {error && <div className="error-banner" role="alert">{error}</div>}

        {step === 'datetime' && (
          <>
            {/* Testimonials */}
            {branding?.show_testimonials && branding?.testimonials?.length > 0 && (
              <div className="booking-testimonials">
                {branding.testimonials.slice(0, 3).map((testimonial, i) => (
                  <div key={i} className="booking-testimonial">
                    <p className="testimonial-text">"{testimonial.text}"</p>
                    <p className="testimonial-author">
                      - {testimonial.name}{testimonial.role ? `, ${testimonial.role}` : ''}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {/* Appointment Type Selector (if multiple) */}
            {appointmentTypes.length > 1 && (
              <div className="type-selector">
                <h3>{t('datetime.selectType')}</h3>
                <div className="type-pills">
                  {appointmentTypes.map(type => (
                    <button
                      key={type.id}
                      className={`type-pill ${selectedType?.id === type.id ? 'active' : ''}`}
                      onClick={() => setSelectedType(type)}
                    >
                      {type.type_name}
                      <span className="duration">{type.default_duration_minutes} {t('datetime.min')}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Date Picker */}
            <div className="date-section">
              <h2>{t('datetime.pickDate')}</h2>
              <div className="week-picker">
                <button className="week-nav prev" onClick={prevWeek} disabled={isPast(weekDates[0])} aria-label={t('datetime.previousWeek')}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M15 19l-7-7 7-7" />
                  </svg>
                </button>

                <div className="week-dates">
                  {weekDates.map((date, idx) => {
                    const disabled = isPast(date);
                    const selected = selectedDate && date.toDateString() === selectedDate.toDateString();

                    return (
                      <button
                        key={idx}
                        className={`date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${isToday(date) ? 'today' : ''}`}
                        onClick={() => !disabled && setSelectedDate(date)}
                        disabled={disabled}
                        aria-label={formatDateAriaLabel(date)}
                      >
                        <span className="day-name">{formatDayName(date)}</span>
                        <span className="day-number">{formatDayNumber(date)}</span>
                        <span className="month">{formatMonth(date)}</span>
                      </button>
                    );
                  })}
                </div>

                <button className="week-nav next" onClick={nextWeek} aria-label={t('datetime.nextWeek')}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Time Picker */}
            <div className="time-section">
              <h2>{t('datetime.pickTime')}</h2>
              <p className="time-subtitle">{t('datetime.timeSubtitle')}</p>

              <div className="time-dropdown-wrapper">
                <select
                  className="time-dropdown"
                  value={selectedTime}
                  onChange={(e) => setSelectedTime(e.target.value)}
                >
                  {availableSlots.length === 0 ? (
                    <option value="">{t('datetime.noTimes')}</option>
                  ) : (
                    availableSlots.map((slot, idx) => (
                      <option key={idx} value={slot.start_time}>
                        {slot.display}
                      </option>
                    ))
                  )}
                </select>
                <svg className="dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </div>

              {/* Meeting Mode Toggle */}
              <div className="meeting-mode-toggle">
                <button
                  className={`mode-button ${meetingMode === 'phone' ? 'active' : ''}`}
                  onClick={() => setMeetingMode('phone')}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                  {t('datetime.phoneCall')}
                </button>
                <button
                  className={`mode-button ${meetingMode === 'video' ? 'active' : ''}`}
                  onClick={() => setMeetingMode('video')}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="2" y="5" width="14" height="14" rx="2" />
                    <path d="M22 7l-6 4 6 4V7z" />
                  </svg>
                  {t('datetime.videoCall')}
                </button>
              </div>
            </div>

            <button
              className="primary-button next-button"
              onClick={() => setStep('form')}
              disabled={!selectedDate || !selectedTime}
            >
              {t('datetime.next')}
            </button>
          </>
        )}

        {step === 'form' && (
          <div className="form-step">
            <button className="back-link" onClick={() => setStep('datetime')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 19l-7-7 7-7" />
              </svg>
              {t('form.back')}
            </button>

            <h2>{t('form.title')}</h2>

            <form onSubmit={handleSubmit}>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-first-name">{t('form.firstName')} {t('form.required')}</label>
                  <input
                    id="pb-first-name"
                    type="text"
                    value={form.first_name}
                    onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                    placeholder="Jane"
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-last-name">{t('form.lastName')} {t('form.required')}</label>
                  <input
                    id="pb-last-name"
                    type="text"
                    value={form.last_name}
                    onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                    placeholder="Doe"
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-email">{t('form.email')} {t('form.required')}</label>
                  <input
                    id="pb-email"
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    placeholder="jane@email.com"
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-phone">{t('form.phone')}</label>
                  <input
                    id="pb-phone"
                    type="tel"
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    placeholder={t('form.phonePlaceholder')}
                  />
                  <span className="field-hint">{t('form.phoneHint')}</span>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-notes">{t('form.notes')}</label>
                  <textarea
                    id="pb-notes"
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    placeholder={t('form.notesPlaceholder')}
                    rows={3}
                    maxLength={500}
                  />
                </div>
              </div>

              {/* Custom Question Example */}
              <div className="form-row">
                <div className="form-group radio-group">
                  <label>{t('form.workingWithLO')}</label>
                  <div className="radio-options">
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="working_with_agent"
                        value="no"
                        checked={form.working_with_agent === 'no'}
                        onChange={(e) => setForm({ ...form, working_with_agent: e.target.value })}
                      />
                      <span>{t('form.no')}</span>
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="working_with_agent"
                        value="yes"
                        checked={form.working_with_agent === 'yes'}
                        onChange={(e) => setForm({ ...form, working_with_agent: e.target.value })}
                      />
                      <span>{t('form.yes')}</span>
                    </label>
                  </div>
                </div>
              </div>

              <div className="form-summary">
                <div className="summary-badge">
                  {formatFullDate(selectedDate)} — {formatTime(selectedTime)}
                </div>
              </div>

              {TURNSTILE_SITE_KEY && (
                <div className="turnstile-wrapper" style={{ display: 'flex', justifyContent: 'center', margin: '16px 0' }}>
                  <div ref={turnstileRef}></div>
                </div>
              )}

              <button
                type="submit"
                className="primary-button submit-button"
                disabled={submitting || (TURNSTILE_SITE_KEY && !turnstileToken)}
              >
                {submitting ? t('form.scheduling') : t('form.scheduleAppointment')}
              </button>
            </form>
          </div>
        )}


        {/* Footer - always shown, not removable */}
        <div className="booking-footer">
          <p>{t('booking.poweredBy')} <strong>Perennia AI</strong></p>
        </div>
      </div>
    </div>
  );
};

/**
 * PublicBooking wraps the inner component with LanguageProvider
 * so that useTranslation() is available throughout the booking flow.
 */
const PublicBooking = () => {
  return (
    <LanguageProvider>
      <PublicBookingInner />
    </LanguageProvider>
  );
};

export default PublicBooking;
