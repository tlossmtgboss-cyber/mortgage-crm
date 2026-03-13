import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import useOrgBranding from '../hooks/useOrgBranding';
import { LanguageProvider, useTranslation } from '../i18n';
import { useIsTablet, useScreenOrientation } from '../components/common/ResponsiveContainer';
import LanguageSelector from '../components/calendar/LanguageSelector';
import SEOHead from '../components/common/SEOHead';
import ScreenReaderOnly from '../components/common/ScreenReaderOnly';
import LiveRegion from '../components/common/LiveRegion';
import {
  generateBookingPageMeta,
  generateStructuredData,
  generateLocalBusinessData,
  generateCanonicalUrl,
  generateBreadcrumbs,
  injectJsonLd,
  cleanupJsonLd,
} from '../utils/seo';
import JoinWaitlist from '../components/calendar/JoinWaitlist';
import BookingConfirmation from '../components/calendar/BookingConfirmation';
import './PublicBooking.css';
import '../styles/tablet.css';

const TURNSTILE_SITE_KEY = process.env.REACT_APP_TURNSTILE_SITE_KEY;

// US phone: (XXX) XXX-XXXX, XXX-XXX-XXXX, or 10 digits with optional +1
const PHONE_REGEX = /^(\+1\s?)?(\(\d{3}\)|\d{3})[\s\-.]?\d{3}[\s\-.]?\d{4}$/;

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const PublicBookingInner = () => {
  const { t, locale } = useTranslation();
  const isTablet = useIsTablet();
  const orientation = useScreenOrientation();

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
  const [step, setStep] = useState('datetime'); // datetime, form, confirmation, manage, waitlist
  const [submitting, setSubmitting] = useState(false);
  const [confirmedAppointment, setConfirmedAppointment] = useState(null);
  const [showWaitlist, setShowWaitlist] = useState(false);

  const [cancelConfirm, setCancelConfirm] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState('');
  const [formErrors, setFormErrors] = useState({});
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

  // ========================================================================
  // SEO: Compute meta tags and structured data
  // ========================================================================

  // Derive SEO-relevant names from branding / booking link data
  const seoOrgName = branding?.org_name || null;
  const seoLoName = branding?.lo?.name || null;
  const seoAppointmentType = selectedType?.type_name || bookingLink?.custom_title || bookingLink?.title || null;
  const seoOgImage = branding?.logo_url || bookingLink?.logo_url || null;
  const seoCanonicalUrl = generateCanonicalUrl(slug);

  const seoMeta = generateBookingPageMeta(seoOrgName, seoAppointmentType, seoLoName, {
    image: seoOgImage,
    slug,
  });

  // Build LocalBusiness structured data for the page (injected on load via SEOHead)
  const typeNames = appointmentTypes.map((t) => t.type_name).filter(Boolean);
  const localBusinessData = generateLocalBusinessData(
    {
      name: seoLoName || seoOrgName || 'Perennia AI',
      description: bookingLink?.custom_description || bookingLink?.description || seoMeta.description,
      image: seoOgImage,
      orgName: seoOrgName,
      appointmentTypes: typeNames.length > 0 ? typeNames : undefined,
    },
    seoCanonicalUrl,
  );

  // Build breadcrumbs for SEOHead
  const breadcrumbData = generateBreadcrumbs([
    { name: 'Home', url: 'https://app.perenniaai.com' },
    ...(seoOrgName ? [{ name: seoOrgName, url: seoCanonicalUrl }] : []),
    { name: seoAppointmentType || 'Book an Appointment' },
  ]);

  // Combine all structured data for SEOHead
  const seoStructuredData = [localBusinessData, breadcrumbData].filter(Boolean);

  // Inject JSON-LD Event structured data when a time slot is selected
  useEffect(() => {
    if (!selectedType || !selectedTime) {
      return cleanupJsonLd;
    }

    const durationMs = (selectedType.default_duration_minutes || 30) * 60 * 1000;
    const startDate = new Date(selectedTime);
    const endDate = new Date(startDate.getTime() + durationMs);

    const eventData = generateStructuredData({
      name: selectedType.type_name || 'Appointment',
      description: selectedType.description || seoMeta.description,
      startTime: startDate.toISOString(),
      endTime: endDate.toISOString(),
      locationName: meetingMode === 'video' ? 'Video Call' : 'Phone Call',
      organizerName: seoOrgName || 'Perennia AI',
      url: seoCanonicalUrl,
      image: seoOgImage,
    });

    const cleanupEvent = injectJsonLd(eventData);

    return () => {
      cleanupEvent();
    };
  }, [selectedType, selectedTime, meetingMode, seoOrgName, seoOgImage, seoMeta.description, seoCanonicalUrl]);

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

    const newFormErrors = {};
    if (!form.first_name) newFormErrors.first_name = t('booking.errorRequiredFields');
    if (!form.last_name) newFormErrors.last_name = t('booking.errorRequiredFields');
    if (!form.email) newFormErrors.email = t('booking.errorRequiredFields');
    if (Object.keys(newFormErrors).length > 0) {
      setFormErrors(newFormErrors);
      setError(t('booking.errorRequiredFields'));
      return;
    }
    setFormErrors({});

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
        appointment_id: result.appointment_id,
        date: selectedDate,
        time: selectedTime,
        type: selectedType,
        meetingMode: meetingMode,
        // Rich data from API for BookingConfirmation component
        scheduled_start: result.scheduled_start,
        scheduled_end: result.scheduled_end,
        video_link: result.video_link,
        confirmation_token: result.confirmation_token,
        confirmation_url: result.confirmation_url,
        title: result.confirmation_details?.title,
        duration_minutes: selectedType.default_duration_minutes || 30,
        appointment_type_name: selectedType.type_name,
        meeting_mode: meetingMode,
        lo_name: result.confirmation_details?.team_member,
        attendee_name: `${form.first_name} ${form.last_name}`,
        attendee_email: form.email,
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
        <SEOHead {...seoMeta} />
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
        <SEOHead {...seoMeta} />
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

  // Confirmation state — uses the polished BookingConfirmation component
  if (step === 'confirmation' && confirmedAppointment) {
    return (
      <div className="redfin-booking" style={coverStyle}>
        <SEOHead {...seoMeta} />
        <div className="booking-container confirmation-container">
          <LanguageSelector />
          {renderBrandingHeader()}

          <BookingConfirmation
            appointmentData={confirmedAppointment}
            appointmentId={confirmedAppointment.id}
            token={confirmedAppointment.confirmation_token}
            onCancel={() => handleCancel()}
            onGoHome={() => window.location.href = '/'}
          />

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
        <SEOHead {...seoMeta} />
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

  // Step indicator definitions
  const BOOKING_STEPS = [
    { key: 'datetime', label: t('datetime.pickDate') || 'Select Date & Time' },
    { key: 'form', label: t('form.title') || 'Your Details' },
    { key: 'confirmation', label: t('confirmation.title') || 'Confirmed' },
  ];

  const currentStepIndex = BOOKING_STEPS.findIndex(s => s.key === step);
  const progressMessage = currentStepIndex >= 0
    ? `Step ${currentStepIndex + 1} of ${BOOKING_STEPS.length}: ${BOOKING_STEPS[currentStepIndex].label}`
    : '';

  return (
    <div className="redfin-booking" style={coverStyle}>
      <SEOHead {...seoMeta} structuredData={seoStructuredData.length > 0 ? seoStructuredData : undefined} />
      <main className="booking-container" role="main">
        {/* Language Selector */}
        <LanguageSelector />

        {/* Org Branding Header */}
        {renderBrandingHeader()}

        {/* Booking Link Header */}
        {bookingLink && (
          <header className="booking-header">
            <h1>{bookingLink.custom_title || bookingLink.title || bookingLink.link_name || t('booking.scheduleAppointment')}</h1>
            {bookingLink.custom_description || bookingLink.description ? (
              <p>{bookingLink.custom_description || bookingLink.description}</p>
            ) : null}
            {seoLoName && (
              <p className="booking-lo-name">with <strong>{seoLoName}</strong></p>
            )}
          </header>
        )}

        {/* Step indicator */}
        {step !== 'cancelled' && (
          <nav className="booking-step-indicator" aria-label="Booking progress">
            <ol className="step-list">
              {BOOKING_STEPS.map((s, idx) => {
                const isCurrent = s.key === step;
                const isCompleted = idx < currentStepIndex;
                return (
                  <li
                    key={s.key}
                    className={`step-item${isCurrent ? ' step-current' : ''}${isCompleted ? ' step-completed' : ''}`}
                    aria-current={isCurrent ? 'step' : undefined}
                  >
                    <span className="step-number" aria-hidden="true">{idx + 1}</span>
                    <span className="step-label">{s.label}</span>
                  </li>
                );
              })}
            </ol>
          </nav>
        )}

        {/* Progress announcement for screen readers */}
        <LiveRegion politeness="polite" message={progressMessage} debounceMs={200} />

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
              <section className="type-selector" aria-labelledby="type-selector-heading">
                <h2 id="type-selector-heading">{t('datetime.selectType')}</h2>
                <div className="type-pills" role="listbox" aria-label={t('datetime.selectType')}>
                  {appointmentTypes.map(type => (
                    <button
                      key={type.id}
                      className={`type-pill ${selectedType?.id === type.id ? 'active' : ''}`}
                      onClick={() => setSelectedType(type)}
                      role="option"
                      aria-selected={selectedType?.id === type.id}
                    >
                      {type.type_name}
                      <span className="duration">{type.default_duration_minutes} {t('datetime.min')}</span>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {/* Date Picker */}
            <section className="date-section" aria-labelledby="date-picker-heading">
              <h2 id="date-picker-heading">{t('datetime.pickDate')}</h2>
              <div className="week-picker">
                <button className="week-nav prev" onClick={prevWeek} disabled={isPast(weekDates[0])} aria-label={t('datetime.previousWeek')}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M15 19l-7-7 7-7" />
                  </svg>
                </button>

                <div className="week-dates" role="listbox" aria-label={t('datetime.pickDate')}>
                  {weekDates.map((date, idx) => {
                    const disabled = isPast(date);
                    const selected = selectedDate && date.toDateString() === selectedDate.toDateString();
                    const today = isToday(date);

                    return (
                      <button
                        key={idx}
                        className={`date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${today ? 'today' : ''}`}
                        onClick={() => !disabled && setSelectedDate(date)}
                        disabled={disabled}
                        role="option"
                        aria-selected={selected}
                        aria-current={today ? 'date' : undefined}
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
            </section>

            {/* Time Picker */}
            <section className="time-section" aria-labelledby="time-picker-heading">
              <h2 id="time-picker-heading">{t('datetime.pickTime')}</h2>
              <p className="time-subtitle">{t('datetime.timeSubtitle')}</p>

              <div className="time-dropdown-wrapper">
                <label htmlFor="pb-time-select" className="sr-only">
                  <ScreenReaderOnly>{t('datetime.pickTime')}</ScreenReaderOnly>
                </label>
                <select
                  id="pb-time-select"
                  className="time-dropdown"
                  value={selectedTime}
                  onChange={(e) => setSelectedTime(e.target.value)}
                  aria-label={t('datetime.pickTime')}
                >
                  {availableSlots.length === 0 ? (
                    <option value="">{t('datetime.noTimes')}</option>
                  ) : (
                    availableSlots.map((slot, idx) => {
                      const slotDate = new Date(slot.start_time);
                      const fullDateTimeLabel = selectedDate
                        ? `${formatDateAriaLabel(selectedDate)} at ${slot.display}`
                        : slot.display;
                      return (
                        <option key={idx} value={slot.start_time} aria-label={fullDateTimeLabel}>
                          {slot.display}
                        </option>
                      );
                    })
                  )}
                </select>
                <svg className="dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </div>

              {/* Meeting Mode Toggle */}
              <div className="meeting-mode-toggle" role="group" aria-label="Meeting format">
                <button
                  className={`mode-button ${meetingMode === 'phone' ? 'active' : ''}`}
                  onClick={() => setMeetingMode('phone')}
                  aria-pressed={meetingMode === 'phone'}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                  {t('datetime.phoneCall')}
                </button>
                <button
                  className={`mode-button ${meetingMode === 'video' ? 'active' : ''}`}
                  onClick={() => setMeetingMode('video')}
                  aria-pressed={meetingMode === 'video'}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <rect x="2" y="5" width="14" height="14" rx="2" />
                    <path d="M22 7l-6 4 6 4V7z" />
                  </svg>
                  {t('datetime.videoCall')}
                </button>
              </div>
            </section>

            <button
              className="primary-button next-button"
              onClick={() => setStep('form')}
              disabled={!selectedDate || !selectedTime}
            >
              {t('datetime.next')}
            </button>

            {/* Waitlist option when no slots are available */}
            {availableSlots.length === 0 && selectedDate && !showWaitlist && bookingLink && (
              <div style={{ textAlign: 'center', marginTop: '16px', padding: '16px', backgroundColor: '#f0f9ff', borderRadius: '12px' }}>
                <p style={{ margin: '0 0 12px 0', color: '#1e40af', fontSize: '14px' }}>
                  No times available for this date. Join the waitlist and we'll notify you when a slot opens up.
                </p>
                <button
                  className="secondary-button"
                  onClick={() => setShowWaitlist(true)}
                  style={{ padding: '10px 24px', borderRadius: '8px', border: '1px solid #2563eb', backgroundColor: '#fff', color: '#2563eb', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}
                >
                  Join Waitlist
                </button>
              </div>
            )}

            {showWaitlist && bookingLink && (
              <JoinWaitlist
                organizationId={bookingLink.organization_id}
                appointmentTypeId={selectedType?.id || bookingLink.appointment_type_id}
                appointmentTypeName={selectedType?.type_name || bookingLink.title}
                onClose={() => setShowWaitlist(false)}
              />
            )}
          </>
        )}

        {step === 'form' && (
          <section className={`form-step${isTablet && orientation === 'landscape' ? ' booking-two-column' : ''}`} aria-labelledby="form-step-heading">
            <button className="back-link" onClick={() => setStep('datetime')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 19l-7-7 7-7" />
              </svg>
              {t('form.back')}
            </button>

            <h2 id="form-step-heading">{t('form.title')}</h2>

            <form onSubmit={handleSubmit} noValidate>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-first-name">{t('form.firstName')} {t('form.required')}</label>
                  <input
                    id="pb-first-name"
                    type="text"
                    value={form.first_name}
                    onChange={(e) => {
                      setForm({ ...form, first_name: e.target.value });
                      if (formErrors.first_name && e.target.value) setFormErrors(prev => ({ ...prev, first_name: '' }));
                    }}
                    placeholder="Jane"
                    required
                    aria-required="true"
                    aria-invalid={!!formErrors.first_name || undefined}
                    aria-describedby={formErrors.first_name ? 'pb-first-name-error' : undefined}
                  />
                  {formErrors.first_name && (
                    <span id="pb-first-name-error" className="field-error" role="alert">{formErrors.first_name}</span>
                  )}
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-last-name">{t('form.lastName')} {t('form.required')}</label>
                  <input
                    id="pb-last-name"
                    type="text"
                    value={form.last_name}
                    onChange={(e) => {
                      setForm({ ...form, last_name: e.target.value });
                      if (formErrors.last_name && e.target.value) setFormErrors(prev => ({ ...prev, last_name: '' }));
                    }}
                    placeholder="Doe"
                    required
                    aria-required="true"
                    aria-invalid={!!formErrors.last_name || undefined}
                    aria-describedby={formErrors.last_name ? 'pb-last-name-error' : undefined}
                  />
                  {formErrors.last_name && (
                    <span id="pb-last-name-error" className="field-error" role="alert">{formErrors.last_name}</span>
                  )}
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-email">{t('form.email')} {t('form.required')}</label>
                  <input
                    id="pb-email"
                    type="email"
                    value={form.email}
                    onChange={(e) => {
                      setForm({ ...form, email: e.target.value });
                      if (formErrors.email && e.target.value) setFormErrors(prev => ({ ...prev, email: '' }));
                    }}
                    placeholder="jane@email.com"
                    required
                    aria-required="true"
                    aria-invalid={!!formErrors.email || undefined}
                    aria-describedby={formErrors.email ? 'pb-email-error' : undefined}
                  />
                  {formErrors.email && (
                    <span id="pb-email-error" className="field-error" role="alert">{formErrors.email}</span>
                  )}
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="pb-phone">{t('form.phone')}</label>
                  <input
                    id="pb-phone"
                    type="tel"
                    value={form.phone}
                    onChange={(e) => {
                      setForm({ ...form, phone: e.target.value });
                      if (phoneError) validatePhone(e.target.value);
                    }}
                    onBlur={(e) => validatePhone(e.target.value)}
                    placeholder={t('form.phonePlaceholder')}
                    aria-invalid={!!phoneError || undefined}
                    aria-describedby={phoneError ? 'pb-phone-error' : 'pb-phone-hint'}
                  />
                  <span id="pb-phone-hint" className="field-hint">{t('form.phoneHint')}</span>
                  {phoneError && (
                    <span id="pb-phone-error" className="field-error" role="alert">{phoneError}</span>
                  )}
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
                    aria-describedby="pb-notes-hint"
                  />
                  <ScreenReaderOnly as="span" id="pb-notes-hint">Maximum 500 characters</ScreenReaderOnly>
                </div>
              </div>

              {/* Custom Question Example */}
              <fieldset className="form-row">
                <legend className="form-group-legend">{t('form.workingWithLO')}</legend>
                <div className="form-group radio-group">
                  <div className="radio-options" role="radiogroup" aria-label={t('form.workingWithLO')}>
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
              </fieldset>

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
          </section>
        )}


        {/* Footer - always shown, not removable */}
        <footer className="booking-footer">
          <p>{t('booking.poweredBy')} <strong>Perennia AI</strong></p>
        </footer>
      </main>
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
