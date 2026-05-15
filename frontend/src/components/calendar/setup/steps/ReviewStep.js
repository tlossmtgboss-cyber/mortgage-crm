/**
 * ReviewStep - Smart Calendar Guided Setup, Step 10: Review & Activate
 *
 * Final step that summarizes all configured settings in a visual dashboard,
 * shows a readiness checklist, and lets the user activate their calendar.
 *
 * Cards displayed:
 *   1. Timezone & Hours - timezone, enabled days, hours range
 *   2. Appointment Types - list of enabled types with colors
 *   3. Booking Page - mini preview, booking link
 *   4. Notifications - active reminders, digest status
 *   5. Integrations - connected services
 *   6. Cancellation Policy - policy name
 *   7. Team - assignment strategy or "Individual"
 *   8. Advanced Features - count of enabled features
 *
 * Each card has an "Edit" link that navigates back to the corresponding step.
 * Activation calls PUT /api/v1/calendar-settings/availability with is_active: true
 * and marks setup as complete in localStorage.
 *
 * Props:
 *   stepData         - aggregated data from all prior steps
 *   completedSteps   - array of completed step numbers
 *   onGoToStep(n)    - navigate back to step n for editing
 *   onActivate()     - trigger activation (handled by parent wizard)
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarSettingsAPI } from '../../../../services/api';
import { toast } from '../../../../utils/toast';
import './ReviewStep.css';

// ============================================================================
// Constants
// ============================================================================

const STORAGE_KEY = 'perennia_calendar_setup_progress';
const SETUP_COMPLETE_KEY = 'perennia_calendar_setup_complete';

const DAY_LABELS = {
  monday: 'Mon', tuesday: 'Tue', wednesday: 'Wed',
  thursday: 'Thu', friday: 'Fri', saturday: 'Sat', sunday: 'Sun',
};

const DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

const STEP_MAP = {
  'timezone-hours': 2,
  'appointment-types': 3,
  'booking-page': 4,
  'notifications': 5,
  'integrations': 6,
  'cancellation-policy': 7,
  'team-setup': 8,
  'advanced-features': 9,
};

const POLICY_NAMES = {
  flexible: 'Flexible',
  moderate: 'Moderate',
  strict: 'Strict',
  custom: 'Custom',
};

const STRATEGY_LABELS = {
  round_robin: 'Round Robin',
  load_balanced: 'Load Balanced',
  ai_optimized: 'AI Optimized',
  manual: 'Manual',
  priority: 'Priority',
};

// ============================================================================
// Helper: format time string
// ============================================================================

function formatTime(timeStr) {
  if (!timeStr) return '';
  const [h, m] = timeStr.split(':').map(Number);
  const period = h >= 12 ? 'PM' : 'AM';
  const hour = h % 12 || 12;
  return `${hour}:${String(m).padStart(2, '0')} ${period}`;
}

// ============================================================================
// Sub-components: Summary Cards
// ============================================================================

function SummaryCard({ icon, title, stepId, onEdit, status, children }) {
  const statusClass = status === 'complete' ? 'rvs-card--complete'
    : status === 'warning' ? 'rvs-card--warning'
    : status === 'error' ? 'rvs-card--error'
    : '';

  return (
    <div className={`rvs-card ${statusClass}`}>
      <div className="rvs-card__header">
        <div className="rvs-card__title-row">
          <div className="rvs-card__icon" aria-hidden="true">
            <i className={`fas ${icon}`} />
          </div>
          <h3 className="rvs-card__title">{title}</h3>
        </div>
        {onEdit && (
          <button
            type="button"
            className="rvs-card__edit"
            onClick={onEdit}
            aria-label={`Edit ${title}`}
          >
            <i className="fas fa-pen" aria-hidden="true" />
            <span>Edit</span>
          </button>
        )}
      </div>
      <div className="rvs-card__body">
        {children}
      </div>
      <div className={`rvs-card__status-bar`} aria-hidden="true" />
    </div>
  );
}

function ChecklistItem({ status, label, detail }) {
  const iconClass = status === 'complete' ? 'fa-check-circle'
    : status === 'warning' ? 'fa-exclamation-circle'
    : 'fa-times-circle';

  const statusClass = status === 'complete' ? 'rvs-checklist__item--complete'
    : status === 'warning' ? 'rvs-checklist__item--warning'
    : 'rvs-checklist__item--error';

  return (
    <li className={`rvs-checklist__item ${statusClass}`}>
      <i className={`fas ${iconClass}`} aria-hidden="true" />
      <div className="rvs-checklist__text">
        <span className="rvs-checklist__label">{label}</span>
        {detail && <span className="rvs-checklist__detail">{detail}</span>}
      </div>
    </li>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function ReviewStep({
  stepData = {},
  completedSteps = [],
  onGoToStep,
  onActivate,
}) {
  const navigate = useNavigate();

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const [liveData, setLiveData] = useState({
    availability: null,
    appointmentTypes: null,
    bookingPage: null,
    notifications: null,
    integrations: null,
    team: null,
  });
  const [loading, setLoading] = useState(true);
  const [activating, setActivating] = useState(false);
  const [activated, setActivated] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);

  // ---------------------------------------------------------------------------
  // Load live data from API for each section
  // ---------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;

    async function loadAllSettings() {
      setLoading(true);
      const results = {};

      // Load all sections in parallel, tolerating individual failures
      const loads = [
        calendarSettingsAPI.getAvailability().then(r => { results.availability = r?.data || null; }).catch(() => {}),
        calendarSettingsAPI.getAppointmentTypes().then(r => { results.appointmentTypes = r?.data?.appointment_types || []; }).catch(() => { results.appointmentTypes = []; }),
        calendarSettingsAPI.getBookingPage().then(r => { results.bookingPage = r?.data || null; }).catch(() => {}),
        calendarSettingsAPI.getNotifications().then(r => { results.notifications = r?.data || null; }).catch(() => {}),
        calendarSettingsAPI.getIntegrations().then(r => { results.integrations = r?.data || null; }).catch(() => {}),
        calendarSettingsAPI.getTeam().then(r => { results.team = r?.data || null; }).catch(() => { results.team = null; }),
      ];

      await Promise.all(loads);

      if (!cancelled) {
        setLiveData(results);
        setLoading(false);
      }
    }

    loadAllSettings();
    return () => { cancelled = true; };
  }, []);

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------
  const availability = liveData.availability || stepData['timezone-hours'] || {};
  const appointmentTypes = liveData.appointmentTypes || stepData['appointment-types']?.types || [];
  const bookingPage = liveData.bookingPage || stepData['booking-page'] || {};
  const notifications = liveData.notifications || stepData['notifications'] || {};
  const integrations = liveData.integrations || stepData['integrations'] || {};
  const teamData = liveData.team || stepData['team-setup'] || {};
  const cancellationData = stepData['cancellation-policy'] || {};
  const advancedData = stepData['advanced-features'] || {};

  // Timezone & hours summary
  const timezone = availability.timezone || 'America/Chicago';
  const businessHours = availability.business_hours || {};
  const enabledDays = DAY_ORDER.filter(d => businessHours[d]?.enabled);
  const firstEnabledDay = enabledDays[0];
  const hoursRange = firstEnabledDay && businessHours[firstEnabledDay]
    ? `${formatTime(businessHours[firstEnabledDay].start)} - ${formatTime(businessHours[firstEnabledDay].end)}`
    : '9:00 AM - 5:00 PM';

  // Appointment types summary
  const enabledTypes = Array.isArray(appointmentTypes) ? appointmentTypes : [];

  // Booking page summary
  const branding = bookingPage.branding || {};
  const bookingLinks = bookingPage.booking_links || [];
  const primaryBookingLink = bookingLinks.length > 0 ? bookingLinks[0] : null;

  // Notifications summary
  const activeReminders = [];
  if (notifications.email_reminder_24h) activeReminders.push('Email 24h');
  if (notifications.email_reminder_2h) activeReminders.push('Email 2h');
  if (notifications.email_reminder_15m) activeReminders.push('Email 15m');
  if (notifications.sms_reminder_24h) activeReminders.push('SMS 24h');
  if (notifications.sms_reminder_2h) activeReminders.push('SMS 2h');
  if (notifications.sms_reminder_15m) activeReminders.push('SMS 15m');

  // Integrations summary
  const connectedServices = [];
  if (integrations.google?.connected) connectedServices.push('Google Calendar');
  if (integrations.outlook?.connected) connectedServices.push('Outlook');

  // Cancellation policy
  const policyType = cancellationData.policy_type || cancellationData.cancellationPolicy || null;
  const policyLabel = policyType ? (POLICY_NAMES[policyType] || policyType) : null;

  // Team
  const isTeamSetup = teamData.members && teamData.members.length > 0;
  const strategyLabel = teamData.assignment_strategy
    ? (STRATEGY_LABELS[teamData.assignment_strategy] || teamData.assignment_strategy)
    : null;

  // Advanced features count
  const advancedFeatureCount = useMemo(() => {
    let count = 0;
    if (advancedData.waitlist_enabled) count++;
    if (advancedData.recurring_enabled) count++;
    if (advancedData.buffer_enabled || (availability.buffer_minutes && availability.buffer_minutes > 0)) count++;
    if (advancedData.group_booking_enabled) count++;
    if (advancedData.smart_scheduling_enabled) count++;
    return count;
  }, [advancedData, availability.buffer_minutes]);

  // ---------------------------------------------------------------------------
  // Readiness checklist
  // ---------------------------------------------------------------------------
  const checklist = useMemo(() => {
    const items = [];

    // Timezone (critical)
    items.push({
      status: completedSteps.includes(2) || availability.timezone ? 'complete' : 'warning',
      label: 'Timezone & business hours',
      detail: completedSteps.includes(2) ? `${timezone} configured` : 'Using defaults',
    });

    // Appointment types (critical)
    items.push({
      status: enabledTypes.length > 0 ? 'complete' : 'error',
      label: 'Appointment types',
      detail: enabledTypes.length > 0
        ? `${enabledTypes.length} type${enabledTypes.length !== 1 ? 's' : ''} created`
        : 'No appointment types -- clients cannot book',
    });

    // Booking page (optional)
    items.push({
      status: completedSteps.includes(4) || branding.primary_color ? 'complete' : 'warning',
      label: 'Booking page branding',
      detail: completedSteps.includes(4) ? 'Customized' : 'Using default branding',
    });

    // Notifications (optional)
    items.push({
      status: activeReminders.length > 0 ? 'complete' : 'warning',
      label: 'Reminders configured',
      detail: activeReminders.length > 0
        ? `${activeReminders.length} reminder${activeReminders.length !== 1 ? 's' : ''} active`
        : 'No reminders set -- clients may forget',
    });

    // Integrations (optional)
    items.push({
      status: connectedServices.length > 0 ? 'complete' : 'warning',
      label: 'Calendar integrations',
      detail: connectedServices.length > 0
        ? connectedServices.join(', ')
        : 'No calendar connected -- risk of double-booking',
    });

    // Cancellation policy (optional)
    items.push({
      status: policyLabel ? 'complete' : 'warning',
      label: 'Cancellation policy',
      detail: policyLabel ? `${policyLabel} policy` : 'No policy set -- using defaults',
    });

    return items;
  }, [completedSteps, availability.timezone, timezone, enabledTypes, branding.primary_color, activeReminders, connectedServices, policyLabel]);

  const hasCriticalIssues = checklist.some(c => c.status === 'error');
  const warningCount = checklist.filter(c => c.status === 'warning').length;
  const completeCount = checklist.filter(c => c.status === 'complete').length;

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------
  const handleEditStep = useCallback((stepId) => {
    const stepNumber = STEP_MAP[stepId];
    if (stepNumber && onGoToStep) {
      onGoToStep(stepNumber);
    }
  }, [onGoToStep]);

  const handleActivate = useCallback(async () => {
    setActivating(true);
    try {
      // Save is_active = true
      await calendarSettingsAPI.updateAvailability({ is_active: true });

      // Mark setup as complete in localStorage
      localStorage.setItem(SETUP_COMPLETE_KEY, JSON.stringify({
        completedAt: new Date().toISOString(),
        stepsCompleted: completedSteps.length,
      }));

      // Clear setup progress
      localStorage.removeItem(STORAGE_KEY);

      setActivated(true);

      // Notify parent wizard
      if (onActivate) {
        onActivate();
      }
    } catch (err) {
      console.error('Failed to activate calendar:', err);
      toast.error('Failed to activate calendar. Please try again.');
      setActivating(false);
    }
  }, [completedSteps, onActivate]);

  const handleCopyLink = useCallback(() => {
    const link = primaryBookingLink
      ? `${window.location.origin}${primaryBookingLink.url}`
      : `${window.location.origin}/book`;

    navigator.clipboard.writeText(link).then(() => {
      setCopiedLink(true);
      toast.success('Booking link copied to clipboard');
      setTimeout(() => setCopiedLink(false), 3000);
    }).catch(() => {
      toast.error('Failed to copy link');
    });
  }, [primaryBookingLink]);

  const handleGoToCalendar = useCallback(() => {
    navigate('/calendar');
  }, [navigate]);

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------
  if (loading) {
    return (
      <div className="rvs-step">
        <div className="rvs-loading">
          <div className="rvs-spinner" />
          <p>Loading your configuration...</p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Activated state
  // ---------------------------------------------------------------------------
  if (activated) {
    return (
      <div className="rvs-step">
        <div className="rvs-activated" role="alert">
          <div className="rvs-confetti-container" aria-hidden="true">
            {Array.from({ length: 40 }).map((_, i) => (
              <span
                key={i}
                className="rvs-confetti-piece"
                style={{
                  '--x': `${Math.random() * 100}%`,
                  '--delay': `${Math.random() * 0.6}s`,
                  '--drift': `${(Math.random() - 0.5) * 200}px`,
                  '--fall': `${600 + Math.random() * 400}px`,
                  '--color': ['#1F3D2E', '#3b82f6', '#2D7A52', '#f59e0b', '#ec4899', '#B8924A'][i % 6],
                }}
              />
            ))}
          </div>

          <div className="rvs-activated__icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" strokeLinecap="round" strokeLinejoin="round" />
              <polyline points="22 4 12 14.01 9 11.01" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>

          <h2 className="rvs-activated__title">Your Smart Calendar is Live!</h2>
          <p className="rvs-activated__subtitle">
            Clients can now book appointments with you online. Share your booking link to start filling your calendar.
          </p>

          {/* Share section */}
          <div className="rvs-share-section">
            <label className="rvs-share-label">Your booking link</label>
            <div className="rvs-share-link-row">
              <code className="rvs-share-link-url">
                {primaryBookingLink
                  ? `${window.location.origin}${primaryBookingLink.url}`
                  : `${window.location.origin}/book`
                }
              </code>
              <button
                type="button"
                className="rvs-share-copy-btn"
                onClick={handleCopyLink}
              >
                <i className={`fas ${copiedLink ? 'fa-check' : 'fa-copy'}`} aria-hidden="true" />
                {copiedLink ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>

          {/* Quick actions */}
          <div className="rvs-quick-actions">
            <h3 className="rvs-quick-actions__title">Quick Actions</h3>
            <div className="rvs-quick-actions__grid">
              <button
                type="button"
                className="rvs-quick-action"
                onClick={handleCopyLink}
              >
                <i className="fas fa-link" aria-hidden="true" />
                <span>Send booking link to a borrower</span>
              </button>
              <button
                type="button"
                className="rvs-quick-action"
                onClick={handleGoToCalendar}
              >
                <i className="fas fa-calendar-plus" aria-hidden="true" />
                <span>Schedule your first appointment</span>
              </button>
              {isTeamSetup && (
                <button
                  type="button"
                  className="rvs-quick-action"
                  onClick={() => handleEditStep('team-setup')}
                >
                  <i className="fas fa-user-plus" aria-hidden="true" />
                  <span>Invite team members</span>
                </button>
              )}
            </div>
          </div>

          {/* Primary CTA */}
          <div className="rvs-activated__actions">
            <button
              type="button"
              className="btn-primary rvs-goto-calendar-btn"
              onClick={handleGoToCalendar}
            >
              <i className="fas fa-calendar-alt" aria-hidden="true" />
              Continue to Calendar
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Review state (main view)
  // ---------------------------------------------------------------------------
  return (
    <div className="rvs-step">
      {/* Header */}
      <div className="rvs-header">
        <div className="rvs-header__badge">Step 10 of 10</div>
        <h2 className="rvs-header__title">Review Your Configuration</h2>
        <p className="rvs-header__subtitle">
          Take a final look at everything before going live.
          You can always adjust settings from Calendar Settings.
        </p>
      </div>

      {/* Readiness Checklist */}
      <section className="rvs-readiness" aria-label="Readiness checklist">
        <h3 className="rvs-readiness__title">
          <i className="fas fa-clipboard-check" aria-hidden="true" />
          Readiness Checklist
        </h3>
        <div className="rvs-readiness__summary">
          <span className="rvs-readiness__stat rvs-readiness__stat--complete">
            <i className="fas fa-check-circle" aria-hidden="true" />
            {completeCount} complete
          </span>
          {warningCount > 0 && (
            <span className="rvs-readiness__stat rvs-readiness__stat--warning">
              <i className="fas fa-exclamation-circle" aria-hidden="true" />
              {warningCount} skipped
            </span>
          )}
          {hasCriticalIssues && (
            <span className="rvs-readiness__stat rvs-readiness__stat--error">
              <i className="fas fa-times-circle" aria-hidden="true" />
              Action needed
            </span>
          )}
        </div>
        <ul className="rvs-checklist" role="list">
          {checklist.map((item, idx) => (
            <ChecklistItem key={idx} {...item} />
          ))}
        </ul>
      </section>

      {/* Summary Dashboard */}
      <section className="rvs-summary" aria-label="Configuration summary">
        <h3 className="rvs-summary__title">
          <i className="fas fa-th-large" aria-hidden="true" />
          Configuration Summary
        </h3>

        <div className="rvs-summary__grid">
          {/* Timezone & Hours */}
          <SummaryCard
            icon="fa-clock"
            title="Timezone & Hours"
            stepId="timezone-hours"
            onEdit={() => handleEditStep('timezone-hours')}
            status={completedSteps.includes(2) ? 'complete' : 'warning'}
          >
            <div className="rvs-detail-row">
              <span className="rvs-detail-label">Timezone</span>
              <span className="rvs-detail-value">{timezone.replace(/_/g, ' ')}</span>
            </div>
            <div className="rvs-detail-row">
              <span className="rvs-detail-label">Days</span>
              <div className="rvs-day-pills">
                {DAY_ORDER.map(day => (
                  <span
                    key={day}
                    className={`rvs-day-pill ${enabledDays.includes(day) ? 'rvs-day-pill--active' : ''}`}
                  >
                    {DAY_LABELS[day]}
                  </span>
                ))}
              </div>
            </div>
            <div className="rvs-detail-row">
              <span className="rvs-detail-label">Hours</span>
              <span className="rvs-detail-value">{hoursRange}</span>
            </div>
          </SummaryCard>

          {/* Appointment Types */}
          <SummaryCard
            icon="fa-list-alt"
            title="Appointment Types"
            stepId="appointment-types"
            onEdit={() => handleEditStep('appointment-types')}
            status={enabledTypes.length > 0 ? 'complete' : 'error'}
          >
            {enabledTypes.length === 0 ? (
              <p className="rvs-empty-hint">
                No appointment types created. Clients will not be able to book.
              </p>
            ) : (
              <div className="rvs-type-list">
                {enabledTypes.slice(0, 4).map((type, idx) => (
                  <div key={type.id || idx} className="rvs-type-item">
                    <span
                      className="rvs-type-dot"
                      style={{ backgroundColor: type.color || '#1F3D2E' }}
                      aria-hidden="true"
                    />
                    <span className="rvs-type-name">{type.type_name}</span>
                    <span className="rvs-type-duration">{type.duration_minutes} min</span>
                  </div>
                ))}
                {enabledTypes.length > 4 && (
                  <p className="rvs-type-more">+{enabledTypes.length - 4} more</p>
                )}
              </div>
            )}
          </SummaryCard>

          {/* Booking Page */}
          <SummaryCard
            icon="fa-palette"
            title="Booking Page"
            stepId="booking-page"
            onEdit={() => handleEditStep('booking-page')}
            status={completedSteps.includes(4) ? 'complete' : 'warning'}
          >
            <div className="rvs-booking-preview-mini">
              <div
                className="rvs-booking-preview-bar"
                style={{ backgroundColor: branding.primary_color || '#1F3D2E' }}
              >
                {branding.logo_url && (
                  <img
                    src={branding.logo_url}
                    alt="Logo"
                    className="rvs-booking-preview-logo"
                  />
                )}
                <span className="rvs-booking-preview-tagline">
                  {branding.tagline || 'Your booking page'}
                </span>
              </div>
            </div>
            {primaryBookingLink && (
              <div className="rvs-detail-row">
                <span className="rvs-detail-label">Link</span>
                <code className="rvs-detail-code">{primaryBookingLink.url}</code>
              </div>
            )}
          </SummaryCard>

          {/* Notifications */}
          <SummaryCard
            icon="fa-bell"
            title="Notifications"
            stepId="notifications"
            onEdit={() => handleEditStep('notifications')}
            status={activeReminders.length > 0 ? 'complete' : 'warning'}
          >
            {activeReminders.length > 0 ? (
              <div className="rvs-reminder-tags">
                {activeReminders.map((r, i) => (
                  <span key={i} className="rvs-reminder-tag">{r}</span>
                ))}
              </div>
            ) : (
              <p className="rvs-empty-hint">No reminders configured</p>
            )}
            <div className="rvs-detail-row">
              <span className="rvs-detail-label">Booking alerts</span>
              <span className="rvs-detail-value">
                {notifications.notify_on_booking ? 'On' : 'Off'}
              </span>
            </div>
          </SummaryCard>

          {/* Integrations */}
          <SummaryCard
            icon="fa-plug"
            title="Integrations"
            stepId="integrations"
            onEdit={() => handleEditStep('integrations')}
            status={connectedServices.length > 0 ? 'complete' : 'warning'}
          >
            {connectedServices.length > 0 ? (
              <div className="rvs-integration-list">
                {connectedServices.map((svc, i) => (
                  <div key={i} className="rvs-integration-item">
                    <i className={`fab ${svc.includes('Google') ? 'fa-google' : 'fa-microsoft'}`} aria-hidden="true" />
                    <span>{svc}</span>
                    <i className="fas fa-check-circle rvs-integration-check" aria-hidden="true" />
                  </div>
                ))}
              </div>
            ) : (
              <p className="rvs-empty-hint">No calendars connected</p>
            )}
          </SummaryCard>

          {/* Cancellation Policy */}
          <SummaryCard
            icon="fa-shield-alt"
            title="Cancellation Policy"
            stepId="cancellation-policy"
            onEdit={() => handleEditStep('cancellation-policy')}
            status={policyLabel ? 'complete' : 'warning'}
          >
            {policyLabel ? (
              <div className="rvs-policy-badge-container">
                <span className="rvs-policy-badge">{policyLabel}</span>
              </div>
            ) : (
              <p className="rvs-empty-hint">No policy configured -- using defaults</p>
            )}
          </SummaryCard>

          {/* Team */}
          <SummaryCard
            icon="fa-users"
            title="Team"
            stepId="team-setup"
            onEdit={() => handleEditStep('team-setup')}
            status={completedSteps.includes(8) ? 'complete' : 'warning'}
          >
            {isTeamSetup ? (
              <>
                <div className="rvs-detail-row">
                  <span className="rvs-detail-label">Strategy</span>
                  <span className="rvs-detail-value">{strategyLabel || 'Round Robin'}</span>
                </div>
                <div className="rvs-detail-row">
                  <span className="rvs-detail-label">Members</span>
                  <span className="rvs-detail-value">{teamData.members?.length || 0}</span>
                </div>
              </>
            ) : (
              <p className="rvs-empty-hint">Individual calendar (no team)</p>
            )}
          </SummaryCard>

          {/* Advanced Features */}
          <SummaryCard
            icon="fa-cogs"
            title="Advanced Features"
            stepId="advanced-features"
            onEdit={() => handleEditStep('advanced-features')}
            status={completedSteps.includes(9) ? 'complete' : 'warning'}
          >
            <div className="rvs-detail-row">
              <span className="rvs-detail-label">Enabled features</span>
              <span className="rvs-detail-value">
                {advancedFeatureCount > 0 ? `${advancedFeatureCount} feature${advancedFeatureCount !== 1 ? 's' : ''}` : 'None'}
              </span>
            </div>
            {availability.buffer_minutes > 0 && (
              <div className="rvs-detail-row">
                <span className="rvs-detail-label">Buffer time</span>
                <span className="rvs-detail-value">{availability.buffer_minutes} min</span>
              </div>
            )}
          </SummaryCard>
        </div>
      </section>

      {/* Activation Section */}
      <section className="rvs-activation" aria-label="Activate calendar">
        <div className="rvs-activation__inner">
          <div className="rvs-activation__icon" aria-hidden="true">
            <i className="fas fa-rocket" />
          </div>
          <h3 className="rvs-activation__title">
            {hasCriticalIssues
              ? 'Almost ready...'
              : 'Your Smart Calendar is ready!'
            }
          </h3>
          <p className="rvs-activation__text">
            {hasCriticalIssues
              ? 'Fix the items marked in red above before activating. You need at least one appointment type.'
              : 'Everything looks good. Activate your calendar to start accepting bookings from clients.'
            }
          </p>

          <button
            type="button"
            className="btn-primary rvs-activate-btn"
            onClick={handleActivate}
            disabled={activating || hasCriticalIssues}
          >
            {activating ? (
              <>
                <i className="fas fa-spinner fa-spin" aria-hidden="true" />
                Activating...
              </>
            ) : (
              <>
                <i className="fas fa-rocket" aria-hidden="true" />
                Activate Calendar
              </>
            )}
          </button>

          {hasCriticalIssues && (
            <p className="rvs-activation__hint">
              <i className="fas fa-info-circle" aria-hidden="true" />
              Create at least one appointment type to activate.
            </p>
          )}

          {!hasCriticalIssues && warningCount > 0 && (
            <p className="rvs-activation__hint">
              <i className="fas fa-info-circle" aria-hidden="true" />
              {warningCount} optional step{warningCount !== 1 ? 's' : ''} skipped.
              You can configure them later from Calendar Settings.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
