/**
 * Perennia AI - Smart Calendar Setup: Step 1 - Welcome & Timezone
 *
 * First step of the guided calendar setup flow:
 *   - Welcome message with setup overview
 *   - Auto-detected timezone with manual override
 *   - Live clock preview in selected timezone
 *   - Quick work-schedule preset picker (pre-fills Step 2)
 *   - Current user personalization (name/photo)
 *
 * Saves timezone via PUT /api/v1/calendar-settings/availability
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { calendarSettingsAPI } from '../../../../services/api';
import { toast } from '../../../../utils/toast';
import './WelcomeStep.css';
import { getUserData } from '../../../../utils/tokenStore';

// ============================================================================
// Constants
// ============================================================================

const US_TIMEZONE_GROUPS = [
  {
    label: 'Eastern',
    timezones: [
      { value: 'America/New_York', label: 'Eastern Time (ET)', cities: 'New York, Miami, Atlanta' },
      { value: 'America/Detroit', label: 'Eastern - Detroit', cities: 'Detroit' },
      { value: 'America/Indiana/Indianapolis', label: 'Eastern - Indiana', cities: 'Indianapolis' },
    ],
  },
  {
    label: 'Central',
    timezones: [
      { value: 'America/Chicago', label: 'Central Time (CT)', cities: 'Chicago, Dallas, Houston' },
      { value: 'America/Menominee', label: 'Central - Menominee', cities: 'Menominee' },
    ],
  },
  {
    label: 'Mountain',
    timezones: [
      { value: 'America/Denver', label: 'Mountain Time (MT)', cities: 'Denver, Phoenix, Salt Lake City' },
      { value: 'America/Phoenix', label: 'Arizona (no DST)', cities: 'Phoenix, Tucson' },
      { value: 'America/Boise', label: 'Mountain - Boise', cities: 'Boise' },
    ],
  },
  {
    label: 'Pacific',
    timezones: [
      { value: 'America/Los_Angeles', label: 'Pacific Time (PT)', cities: 'Los Angeles, San Francisco, Seattle' },
    ],
  },
  {
    label: 'Alaska & Hawaii',
    timezones: [
      { value: 'America/Anchorage', label: 'Alaska Time (AKT)', cities: 'Anchorage, Fairbanks' },
      { value: 'Pacific/Honolulu', label: 'Hawaii Time (HST)', cities: 'Honolulu' },
    ],
  },
];

const SCHEDULE_PRESETS = [
  {
    id: 'standard',
    label: 'Standard',
    hours: '9 AM - 5 PM',
    icon: 'fa-briefcase',
    description: 'Traditional business hours',
    start: '09:00',
    end: '17:00',
  },
  {
    id: 'extended',
    label: 'Extended',
    hours: '8 AM - 6 PM',
    icon: 'fa-clock',
    description: 'Longer day for more availability',
    start: '08:00',
    end: '18:00',
  },
  {
    id: 'early_bird',
    label: 'Early Bird',
    hours: '7 AM - 4 PM',
    icon: 'fa-sun',
    description: 'Start early, finish early',
    start: '07:00',
    end: '16:00',
  },
  {
    id: 'custom',
    label: 'Custom',
    hours: 'Set your own',
    icon: 'fa-sliders-h',
    description: 'Fully customize in the next step',
    start: null,
    end: null,
  },
];

const SETUP_FEATURES = [
  { icon: 'fa-clock', text: 'Your availability and working hours' },
  { icon: 'fa-calendar-check', text: 'Appointment types clients can book' },
  { icon: 'fa-bell', text: 'Reminder and notification preferences' },
  { icon: 'fa-palette', text: 'Your booking page look and feel' },
];

// ============================================================================
// Helpers
// ============================================================================

/**
 * Detect the user's timezone from the browser.
 */
function detectTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return 'America/Chicago';
  }
}

/**
 * Check if a detected timezone is in our known list.
 */
function isKnownTimezone(tz) {
  return US_TIMEZONE_GROUPS.some(group =>
    group.timezones.some(t => t.value === tz)
  );
}

/**
 * Format the current time in a given timezone.
 */
function formatTimeInTimezone(tz) {
  try {
    return new Date().toLocaleTimeString('en-US', {
      timeZone: tz,
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  } catch {
    return '--:--:-- --';
  }
}

/**
 * Get the short timezone abbreviation (e.g., "EST", "CST").
 */
function getTimezoneAbbr(tz) {
  try {
    const parts = new Date().toLocaleTimeString('en-US', {
      timeZone: tz,
      timeZoneName: 'short',
    });
    // Extract the timezone abbreviation from the formatted string
    const match = parts.match(/[A-Z]{2,5}$/);
    return match ? match[0] : '';
  } catch {
    return '';
  }
}

/**
 * Get the user's initials from their name.
 */
function getInitials(name) {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return parts[0][0].toUpperCase();
}

// ============================================================================
// Component
// ============================================================================

/**
 * Props:
 *   - Wizard integration mode: stepData, onChange, allStepData
 *     (passed by CalendarSetupWizard when used as stepComponents['welcome'])
 *   - Standalone mode: onNext, onDataChange
 *     (for use outside the wizard)
 */
export default function WelcomeStep({ stepData = {}, onChange, allStepData, onNext, onDataChange }) {
  // Current user from localStorage (same pattern as MarketDashboard, Settings)
  const currentUser = useMemo(() => {
    try {
      return JSON.parse(getUserData() || '{}');
    } catch {
      return {};
    }
  }, []);

  const userName = currentUser.name || currentUser.first_name ||
    currentUser.email?.split('@')[0] || 'there';
  const userPhoto = currentUser.photo_url || currentUser.avatar_url || null;

  // State — initialize from stepData if resuming wizard progress
  const detectedTz = useRef(detectTimezone());
  const [timezone, setTimezone] = useState(stepData.timezone || detectedTz.current);
  const [currentTime, setCurrentTime] = useState('');
  const [selectedPreset, setSelectedPreset] = useState(stepData.schedulePreset || 'standard');
  const [saving, setSaving] = useState(false);
  const [tzDropdownOpen, setTzDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Live clock
  useEffect(() => {
    const updateClock = () => {
      setCurrentTime(formatTimeInTimezone(timezone));
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, [timezone]);

  // Close dropdown on outside click or Escape key
  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setTzDropdownOpen(false);
      }
    }
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        setTzDropdownOpen(false);
        // Return focus to the trigger button
        const trigger = dropdownRef.current?.querySelector('.welcome-timezone__trigger');
        if (trigger) trigger.focus();
      }
    }
    if (tzDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
        document.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [tzDropdownOpen]);

  // Build data payload for parent notification
  const buildPayload = useCallback((tz, presetId) => {
    const preset = SCHEDULE_PRESETS.find(p => p.id === presetId);
    return {
      timezone: tz,
      schedulePreset: presetId,
      workingHours: preset && preset.start ? { start: preset.start, end: preset.end } : null,
    };
  }, []);

  // Notify parent of data changes (supports both wizard and standalone modes)
  useEffect(() => {
    const payload = buildPayload(timezone, selectedPreset);
    if (onChange) onChange(payload);
    if (onDataChange) onDataChange(payload);
  }, [timezone, selectedPreset, onChange, onDataChange, buildPayload]);

  // Find the label for the currently selected timezone
  const selectedTzInfo = useMemo(() => {
    for (const group of US_TIMEZONE_GROUPS) {
      const found = group.timezones.find(t => t.value === timezone);
      if (found) return found;
    }
    // If the detected timezone isn't in our list, show it raw
    return { value: timezone, label: timezone.replace(/_/g, ' ').replace(/\//g, ' / '), cities: '' };
  }, [timezone]);

  const tzAbbr = getTimezoneAbbr(timezone);
  const isDetectedTz = timezone === detectedTz.current;

  // Handle timezone selection
  const handleTimezoneSelect = useCallback((tz) => {
    setTimezone(tz);
    setTzDropdownOpen(false);
  }, []);

  // Handle "Let's get started" — saves timezone then advances
  const handleGetStarted = useCallback(async () => {
    setSaving(true);
    try {
      await calendarSettingsAPI.updateAvailability({ timezone });
      toast.success('Timezone saved');
      if (onNext) {
        onNext(buildPayload(timezone, selectedPreset));
      }
    } catch (err) {
      console.error('Failed to save timezone:', err);
      toast.error('Failed to save timezone. Please try again.');
    } finally {
      setSaving(false);
    }
  }, [timezone, selectedPreset, onNext, buildPayload]);

  // Keyboard support for preset cards
  const handlePresetKeyDown = useCallback((e, presetId) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setSelectedPreset(presetId);
    }
  }, []);

  // ============================================================================
  // Render
  // ============================================================================

  return (
    <div className="welcome-step">
      {/* Hero section */}
      <div className="welcome-hero">
        <div className="welcome-hero__content">
          {/* User avatar */}
          <div className="welcome-hero__avatar">
            {userPhoto ? (
              <img
                src={userPhoto}
                alt={userName}
                className="welcome-hero__photo"
                onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }}
              />
            ) : null}
            <div
              className="welcome-hero__initials"
              style={{ display: userPhoto ? 'none' : 'flex' }}
              aria-hidden="true"
            >
              {getInitials(userName)}
            </div>
          </div>

          <div className="welcome-hero__text">
            <h2 className="welcome-hero__title">
              <i className="fas fa-calendar-alt welcome-hero__icon" aria-hidden="true"></i>
              Let's set up your Smart Calendar
            </h2>
            <p className="welcome-hero__greeting">
              Hi {userName}! We'll walk you through a few quick settings to get your
              calendar ready for client bookings.
            </p>
          </div>
        </div>

        {/* Estimated time */}
        <div className="welcome-hero__time-badge">
          <i className="far fa-clock" aria-hidden="true"></i>
          This takes about 5 minutes
        </div>
      </div>

      {/* What we'll set up */}
      <section className="welcome-features" aria-label="Setup overview">
        <h3 className="welcome-features__title">What we'll configure</h3>
        <ul className="welcome-features__list">
          {SETUP_FEATURES.map((feature, idx) => (
            <li key={idx} className="welcome-features__item">
              <span className="welcome-features__icon-wrap" aria-hidden="true">
                <i className={`fas ${feature.icon}`}></i>
              </span>
              <span>{feature.text}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Timezone selector */}
      <section className="welcome-timezone" aria-label="Timezone settings">
        <h3 className="welcome-timezone__title">Your timezone</h3>
        <p className="welcome-timezone__subtitle">
          All appointment times will be shown in this timezone.
        </p>

        <div className="welcome-timezone__row">
          {/* Timezone dropdown */}
          <div className="welcome-timezone__selector" ref={dropdownRef}>
            <button
              className="welcome-timezone__trigger"
              onClick={() => setTzDropdownOpen(prev => !prev)}
              aria-expanded={tzDropdownOpen}
              aria-haspopup="listbox"
              aria-label={`Timezone: ${selectedTzInfo.label}. Click to change.`}
              id="tz-selector-trigger"
              type="button"
            >
              <div className="welcome-timezone__trigger-content">
                <i className="fas fa-globe-americas" aria-hidden="true"></i>
                <div className="welcome-timezone__trigger-text">
                  <span className="welcome-timezone__trigger-label">{selectedTzInfo.label}</span>
                  {selectedTzInfo.cities && (
                    <span className="welcome-timezone__trigger-cities">{selectedTzInfo.cities}</span>
                  )}
                </div>
              </div>
              <i className={`fas fa-chevron-${tzDropdownOpen ? 'up' : 'down'}`} aria-hidden="true"></i>
            </button>

            {tzDropdownOpen && (
              <div className="welcome-timezone__dropdown" role="listbox" aria-label="Select timezone">
                {US_TIMEZONE_GROUPS.map(group => (
                  <div key={group.label} className="welcome-timezone__group">
                    <div className="welcome-timezone__group-label">{group.label}</div>
                    {group.timezones.map(tz => (
                      <button
                        key={tz.value}
                        className={`welcome-timezone__option ${timezone === tz.value ? 'selected' : ''}`}
                        onClick={() => handleTimezoneSelect(tz.value)}
                        role="option"
                        aria-selected={timezone === tz.value}
                        type="button"
                      >
                        <span className="welcome-timezone__option-label">{tz.label}</span>
                        <span className="welcome-timezone__option-cities">{tz.cities}</span>
                        {timezone === tz.value && (
                          <i className="fas fa-check welcome-timezone__option-check" aria-hidden="true"></i>
                        )}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Live clock preview card */}
          <div className="welcome-timezone__preview" aria-hidden="true">
            <div className="welcome-timezone__clock">{currentTime}</div>
            <div className="welcome-timezone__abbr">{tzAbbr}</div>
            {isDetectedTz && isKnownTimezone(timezone) && (
              <div className="welcome-timezone__auto-badge">
                <i className="fas fa-magic" aria-hidden="true"></i> Auto-detected
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Work schedule quick picker */}
      <section className="welcome-schedule" aria-label="Work schedule">
        <h3 className="welcome-schedule__title">What's your typical work schedule?</h3>
        <p className="welcome-schedule__subtitle">
          Pick a starting point. You can fine-tune individual days in the next step.
        </p>

        <div className="welcome-schedule__grid" role="radiogroup" aria-label="Schedule presets">
          {SCHEDULE_PRESETS.map(preset => (
            <div
              key={preset.id}
              className={`welcome-schedule__card ${selectedPreset === preset.id ? 'selected' : ''}`}
              onClick={() => setSelectedPreset(preset.id)}
              onKeyDown={(e) => handlePresetKeyDown(e, preset.id)}
              role="radio"
              aria-checked={selectedPreset === preset.id}
              tabIndex={0}
            >
              <div className="welcome-schedule__card-icon">
                <i className={`fas ${preset.icon}`} aria-hidden="true"></i>
              </div>
              <div className="welcome-schedule__card-content">
                <h3 className="welcome-schedule__card-label">{preset.label}</h3>
                <span className="welcome-schedule__card-hours">{preset.hours}</span>
                <span className="welcome-schedule__card-desc">{preset.description}</span>
              </div>
              {selectedPreset === preset.id && (
                <div className="welcome-schedule__card-check" aria-hidden="true">
                  <i className="fas fa-check-circle"></i>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <div className="welcome-cta">
        <button
          className="welcome-cta__button"
          onClick={handleGetStarted}
          disabled={saving}
          type="button"
        >
          {saving ? (
            <>
              <span className="welcome-cta__spinner" aria-hidden="true"></span>
              Saving...
            </>
          ) : (
            <>
              Let's get started
              <i className="fas fa-arrow-right" aria-hidden="true"></i>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
