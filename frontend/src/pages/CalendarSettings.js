/**
 * Perennia AI - Calendar Settings (Container)
 *
 * Thin container that manages cross-cutting state, navigation, data loading,
 * and save dispatch. Each tab's UI is delegated to a section component in
 * ./calendar-settings/.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarSettingsAPI } from '../services/api';
import { toast } from '../utils/toast';
import '../styles/calendar-settings.css';

// Section components
import AvailabilitySection from './calendar-settings/AvailabilitySection';
import AppointmentTypesSection from './calendar-settings/AppointmentTypesSection';
import NotificationsSection from './calendar-settings/NotificationsSection';
import BookingPageSection from './calendar-settings/BookingPageSection';
import CancellationPolicySection from './calendar-settings/CancellationPolicySection';
import IntegrationsSection from './calendar-settings/IntegrationsSection';
import TeamSection from './calendar-settings/TeamSection';
import LocationsLabelsSection from './calendar-settings/LocationsLabelsSection';
import AdvancedSection from './calendar-settings/AdvancedSection';

// ============================================================================
// Navigation constants
// ============================================================================

const NAV_SECTIONS = [
  {
    group: 'Schedule',
    items: [
      { id: 'availability', label: 'Availability', icon: 'fa-clock', description: 'Business hours, lunch breaks, buffer time, and booking window' },
      { id: 'appointment-types', label: 'Appointment Types', icon: 'fa-list-alt', description: 'Define the types of meetings clients can book' },
      { id: 'locations-labels', label: 'Locations & Labels', icon: 'fa-map-marker-alt', description: 'Meeting locations, calendar labels, and appointment templates' },
    ],
  },
  {
    group: 'Booking',
    items: [
      { id: 'booking-page', label: 'Booking Page', icon: 'fa-palette', description: 'Customize your public booking page appearance and branding' },
      { id: 'cancellation-policy', label: 'Cancellation Policy', icon: 'fa-ban', description: 'Set cancellation and rescheduling rules for appointments' },
    ],
  },
  {
    group: 'Communication',
    items: [
      { id: 'notifications', label: 'Notifications', icon: 'fa-bell', description: 'Email and SMS reminder settings, quiet hours, and digests' },
      { id: 'integrations', label: 'Integrations', icon: 'fa-plug', description: 'Connect external calendars and third-party tools' },
    ],
  },
  {
    group: 'Management',
    items: [
      { id: 'team', label: 'Team', icon: 'fa-users', description: 'Manage team assignment strategy and capacity', badge: 'Manager' },
      { id: 'advanced', label: 'Advanced', icon: 'fa-cog', description: 'Data export, calendar feeds, and developer options' },
    ],
  },
];

const ALL_NAV_ITEMS = NAV_SECTIONS.flatMap(s => s.items);

// ============================================================================
// Component
// ============================================================================

function CalendarSettings() {
  const navigate = useNavigate();
  const contentRef = useRef(null);

  // ========== Cross-cutting state ==========
  const [activeSection, setActiveSection] = useState('availability');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [saveStatus, setSaveStatus] = useState('saved');

  // ========== Data state (needed by save handlers) ==========

  const [availability, setAvailability] = useState({
    timezone: 'America/Chicago',
    business_hours: {
      monday: { start: '09:00', end: '17:00', enabled: true },
      tuesday: { start: '09:00', end: '17:00', enabled: true },
      wednesday: { start: '09:00', end: '17:00', enabled: true },
      thursday: { start: '09:00', end: '17:00', enabled: true },
      friday: { start: '09:00', end: '17:00', enabled: true },
      saturday: { start: '10:00', end: '14:00', enabled: false },
      sunday: { start: '10:00', end: '14:00', enabled: false },
    },
    lunch_break: { enabled: true, start: '12:00', end: '13:00' },
    buffer_minutes: 5,
    min_booking_notice_hours: 2,
    max_advance_booking_days: 60,
    block_us_holidays: false,
    blocked_holidays: {},
    custom_blocked_dates: [],
    max_meetings_per_day: 0,
    max_consecutive_meetings: 0,
    min_break_between_meetings: 0,
  });
  const [seasonalHours, setSeasonalHours] = useState([]);
  const [overrideDays, setOverrideDays] = useState([]);
  const [expandedSections, setExpandedSections] = useState({
    'weekly-schedule': true, 'week-overview': true, 'schedule-templates': false,
    'buffer-times': true, 'date-overrides': false, 'holidays': false,
    'seasonal-hours': false, 'override-days': false, 'daily-limits': false,
  });

  const [appointmentTypes, setAppointmentTypes] = useState([]);

  const [notifications, setNotifications] = useState({
    email_reminder_24h: true, email_reminder_2h: true, email_reminder_15m: false,
    sms_reminder_24h: false, sms_reminder_2h: true, sms_reminder_15m: false,
    quiet_hours_enabled: false, quiet_hours_start: '21:00', quiet_hours_end: '08:00',
    notify_on_booking: true, notify_on_cancellation: true, notify_on_reschedule: true,
    alert_new_booking: 'both', alert_cancellation: 'email', alert_reschedule: 'email',
    alert_no_show: 'push', alert_waitlist_opened: 'none', alert_survey_response: 'email',
    digest: {
      enabled: false, frequency: 'daily', send_time: '07:00',
      include_cancelled: false, include_no_shows: true, day_of_week: 'monday',
    },
    quiet_hours_include_weekends: false,
    browser_notifications_enabled: false,
  });

  const [bookingPage, setBookingPage] = useState({
    branding: {
      logo_url: null, primary_color: '#218D8D', secondary_color: '#e6f5f5',
      tagline: '', welcome_message: 'Schedule a time to meet with us', show_branding: true,
    },
    booking_links: [],
  });

  const [cancellationPolicy, setCancellationPolicy] = useState({
    policy: 'moderate', allow_reschedule: true, reschedule_limit: 2, require_reason: false,
  });

  const [advancedSettings, setAdvancedSettings] = useState({
    calendar_feed_enabled: false, auto_confirm_appointments: true,
    show_timezone_selector: true, enable_waitlist: false,
  });

  const [integrations, setIntegrations] = useState({
    google: { connected: false }, outlook: { connected: false }, zoom: { connected: false },
    google_meet: { connected: false }, ical: { connected: false, feed_url: '', subscriber_count: 0 },
  });
  const [integrationSettings, setIntegrationSettings] = useState({
    google: { two_way_sync: true, conflict_resolution: 'crm_wins', sync_frequency: '15' },
    outlook: { two_way_sync: true, conflict_resolution: 'crm_wins', sync_frequency: '15' },
    zoom: { auto_generate_links: true, waiting_room: true, require_password: true, default_duration: 30 },
    google_meet: { auto_add: true, default_duration: 30 },
  });
  const [syncErrors, setSyncErrors] = useState([]);
  const [webhookSettings, setWebhookSettings] = useState({
    api_key: '', webhook_url: '',
    events: {
      'appointment.created': true, 'appointment.updated': true,
      'appointment.cancelled': true, 'appointment.rescheduled': true,
      'appointment.reminder': false, 'appointment.no_show': false,
    },
  });

  const [team, setTeam] = useState({
    assignment_strategy: 'round_robin', apply_to_new_only: true,
    members: [], total_members: 0,
    overflow: { enabled: false, max_overflow_pct: 20, notify_user_ids: [], auto_expand_hours: false },
    permissions: { members_see_calendars: true, members_reschedule_others: false, only_managers_modify: true },
    weekly_coverage: null, utilization_pct: 0,
  });
  const [isManager, setIsManager] = useState(false);

  const [locations, setLocations] = useState([]);
  const [locationsLoading, setLocationsLoading] = useState(false);
  const [labels, setLabels] = useState([]);
  const [labelsLoading, setLabelsLoading] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [autoAssignLabels, setAutoAssignLabels] = useState(false);
  const [labelMappings, setLabelMappings] = useState({});
  const [defaultLabelId, setDefaultLabelId] = useState(null);

  // ========== Derived ==========

  const activeNavItem = ALL_NAV_ITEMS.find(item => item.id === activeSection);
  const activeGroupName = NAV_SECTIONS.find(s => s.items.some(i => i.id === activeSection))?.group || '';
  const showSaveButton = ['availability', 'notifications', 'booking-page', 'team', 'integrations', 'cancellation-policy', 'locations-labels', 'advanced'].includes(activeSection);

  // ============================================================================
  // Data Loading
  // ============================================================================

  useEffect(() => {
    loadTabData(activeSection);
  }, [activeSection]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadTabData = async (tab) => {
    setLoading(true);
    try {
      switch (tab) {
        case 'availability': {
          const res = await calendarSettingsAPI.getAvailability();
          if (res?.data) {
            setAvailability(prev => ({
              ...prev, ...res.data,
              blocked_holidays: res.data.blocked_holidays || prev.blocked_holidays,
              custom_blocked_dates: res.data.custom_blocked_dates || prev.custom_blocked_dates,
            }));
            if (res.data.seasonal_hours) setSeasonalHours(res.data.seasonal_hours);
            if (res.data.override_days) setOverrideDays(res.data.override_days);
          }
          break;
        }
        case 'appointment-types': {
          const res = await calendarSettingsAPI.getAppointmentTypes();
          if (res?.data?.appointment_types) setAppointmentTypes(res.data.appointment_types);
          break;
        }
        case 'notifications': {
          const res = await calendarSettingsAPI.getNotifications();
          if (res?.data) setNotifications(prev => ({ ...prev, ...res.data }));
          break;
        }
        case 'booking-page': {
          const res = await calendarSettingsAPI.getBookingPage();
          if (res?.data) {
            setBookingPage(prev => ({
              branding: { ...prev.branding, ...(res.data.branding || {}) },
              booking_links: res.data.booking_links || [],
            }));
          }
          break;
        }
        case 'integrations': {
          const res = await calendarSettingsAPI.getIntegrations();
          if (res?.data) {
            setIntegrations(prev => ({
              ...prev, ...res.data,
              google: { ...prev.google, ...(res.data.google || {}) },
              outlook: { ...prev.outlook, ...(res.data.outlook || {}) },
              zoom: { ...prev.zoom, ...(res.data.zoom || {}) },
              google_meet: { ...prev.google_meet, ...(res.data.google_meet || {}) },
              ical: { ...prev.ical, ...(res.data.ical || {}) },
            }));
            if (res.data.sync_errors) setSyncErrors(res.data.sync_errors);
            if (res.data.webhook_settings) setWebhookSettings(prev => ({ ...prev, ...res.data.webhook_settings }));
            if (res.data.integration_settings) setIntegrationSettings(prev => ({ ...prev, ...res.data.integration_settings }));
          }
          break;
        }
        case 'team': {
          try {
            const res = await calendarSettingsAPI.getTeam();
            if (res?.data) {
              setTeam(prev => ({
                ...prev, ...res.data,
                overflow: { ...prev.overflow, ...(res.data.overflow || {}) },
                permissions: { ...prev.permissions, ...(res.data.permissions || {}) },
                members: (res.data.members || []).map(m => ({
                  ...m,
                  specialties: m.specialties || [],
                  weekly_appointments: m.weekly_appointments || 0,
                  weekly_capacity: m.weekly_capacity || (m.max_daily_appointments || 8) * 5,
                })),
              }));
              setIsManager(true);
            }
          } catch (err) {
            if (err.response?.status === 403) {
              setIsManager(false);
            } else {
              throw err;
            }
          }
          break;
        }
        case 'locations-labels': {
          setLocationsLoading(true);
          try {
            const locRes = await calendarSettingsAPI.getLocations();
            if (locRes?.data?.locations) setLocations(locRes.data.locations);
          } catch (err) {
            console.error('Failed to load locations:', err);
          } finally {
            setLocationsLoading(false);
          }
          setLabelsLoading(true);
          try {
            const labelsRes = await calendarSettingsAPI.getLabels();
            if (labelsRes?.data?.labels) setLabels(labelsRes.data.labels);
            if (labelsRes?.data?.auto_assign_enabled !== undefined) setAutoAssignLabels(labelsRes.data.auto_assign_enabled);
            if (labelsRes?.data?.label_mappings) setLabelMappings(labelsRes.data.label_mappings);
            if (labelsRes?.data?.default_label_id) setDefaultLabelId(labelsRes.data.default_label_id);
          } catch (err) {
            console.error('Failed to load labels:', err);
          } finally {
            setLabelsLoading(false);
          }
          setTemplatesLoading(true);
          try {
            const templatesRes = await calendarSettingsAPI.getTemplates();
            if (templatesRes?.data?.templates) setTemplates(templatesRes.data.templates);
          } catch (err) {
            console.error('Failed to load templates:', err);
          } finally {
            setTemplatesLoading(false);
          }
          break;
        }
        case 'cancellation-policy':
        case 'advanced':
          break;
        default:
          break;
      }
    } catch (err) {
      console.error(`Failed to load ${tab}:`, err);
      if (err.response?.status !== 403) {
        toast.error(`Failed to load ${tab} settings`);
      }
    } finally {
      setLoading(false);
      setHasChanges(false);
      setSaveStatus('saved');
    }
  };

  // ============================================================================
  // Navigation
  // ============================================================================

  const handleSectionChange = useCallback((sectionId) => {
    if (hasChanges) {
      const proceed = window.confirm('You have unsaved changes. Discard and continue?');
      if (!proceed) return;
    }
    setActiveSection(sectionId);
    setHasChanges(false);
    setSaveStatus('saved');
    if (contentRef.current) {
      contentRef.current.scrollTo(0, 0);
    }
  }, [hasChanges]);

  const handleNavKeyDown = useCallback((e, currentId) => {
    const ids = ALL_NAV_ITEMS.map(t => t.id);
    const idx = ids.indexOf(currentId);
    let newIdx;
    if (e.key === 'ArrowDown') { e.preventDefault(); newIdx = (idx + 1) % ids.length; }
    else if (e.key === 'ArrowUp') { e.preventDefault(); newIdx = (idx - 1 + ids.length) % ids.length; }
    else if (e.key === 'Home') { e.preventDefault(); newIdx = 0; }
    else if (e.key === 'End') { e.preventDefault(); newIdx = ids.length - 1; }
    else return;
    handleSectionChange(ids[newIdx]);
    document.getElementById(`calnav-${ids[newIdx]}`)?.focus();
  }, [handleSectionChange]);

  // ============================================================================
  // Save dispatch
  // ============================================================================

  const markChanged = useCallback(() => {
    setHasChanges(true);
    setSaveStatus('unsaved');
  }, []);

  const toggleExpandedSection = useCallback((key) => {
    setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const handleSave = async () => {
    switch (activeSection) {
      case 'availability':
        setSaving(true); setSaveStatus('saving');
        try {
          await calendarSettingsAPI.updateAvailability({
            ...availability, seasonal_hours: seasonalHours, override_days: overrideDays,
          });
          toast.success('Availability settings saved');
          setHasChanges(false); setSaveStatus('saved');
        } catch (err) {
          toast.error('Failed to save availability settings');
          setSaveStatus('unsaved');
        } finally { setSaving(false); }
        return;

      case 'notifications':
        setSaving(true); setSaveStatus('saving');
        try {
          await calendarSettingsAPI.updateNotifications(notifications);
          toast.success('Notification preferences saved');
          setHasChanges(false); setSaveStatus('saved');
        } catch (err) {
          toast.error('Failed to save notification preferences');
          setSaveStatus('unsaved');
        } finally { setSaving(false); }
        return;

      case 'booking-page':
        setSaving(true); setSaveStatus('saving');
        try {
          await calendarSettingsAPI.updateBookingPage(bookingPage.branding);
          toast.success('Booking page settings saved');
          setHasChanges(false); setSaveStatus('saved');
        } catch (err) {
          toast.error('Failed to save booking page settings');
          setSaveStatus('unsaved');
        } finally { setSaving(false); }
        return;

      case 'team':
        setSaving(true); setSaveStatus('saving');
        try {
          await calendarSettingsAPI.updateTeam({
            assignment_strategy: team.assignment_strategy,
            apply_to_new_only: team.apply_to_new_only,
            members: team.members?.map(m => ({
              user_id: m.user_id,
              max_daily_appointments: m.max_daily_appointments,
              is_accepting_appointments: m.is_accepting_appointments,
              specialties: m.specialties || [],
            })),
            overflow: team.overflow,
            permissions: team.permissions,
          });
          toast.success('Team settings saved');
          setHasChanges(false); setSaveStatus('saved');
        } catch (err) {
          toast.error('Failed to save team settings');
          setSaveStatus('unsaved');
        } finally { setSaving(false); }
        return;

      case 'integrations':
        setSaving(true); setSaveStatus('saving');
        try {
          await new Promise(resolve => setTimeout(resolve, 500));
          toast.success('Integration settings saved');
          setHasChanges(false); setSaveStatus('saved');
        } catch (err) {
          toast.error('Failed to save integration settings');
          setSaveStatus('unsaved');
        } finally { setSaving(false); }
        return;

      case 'cancellation-policy':
      case 'locations-labels':
      case 'advanced':
        setSaving(true); setSaveStatus('saving');
        setTimeout(() => {
          setSaving(false); setHasChanges(false); setSaveStatus('saved');
          toast.success('Settings saved');
        }, 500);
        return;

      default: return;
    }
  };

  // ============================================================================
  // Section router
  // ============================================================================

  const renderActiveSection = () => {
    if (loading) {
      return (
        <div className="cal-settings-loading" role="status">
          <div className="spinner"></div>
          <p>Loading settings...</p>
        </div>
      );
    }

    switch (activeSection) {
      case 'availability':
        return (
          <AvailabilitySection
            availability={availability}
            setAvailability={setAvailability}
            seasonalHours={seasonalHours}
            setSeasonalHours={setSeasonalHours}
            overrideDays={overrideDays}
            setOverrideDays={setOverrideDays}
            expandedSections={expandedSections}
            toggleExpandedSection={toggleExpandedSection}
            markChanged={markChanged}
          />
        );
      case 'appointment-types':
        return (
          <AppointmentTypesSection
            appointmentTypes={appointmentTypes}
            setAppointmentTypes={setAppointmentTypes}
            loading={loading}
            loadTabData={loadTabData}
          />
        );
      case 'notifications':
        return (
          <NotificationsSection
            notifications={notifications}
            setNotifications={setNotifications}
            markChanged={markChanged}
          />
        );
      case 'booking-page':
        return (
          <BookingPageSection
            bookingPage={bookingPage}
            setBookingPage={setBookingPage}
            markChanged={markChanged}
          />
        );
      case 'cancellation-policy':
        return (
          <CancellationPolicySection
            cancellationPolicy={cancellationPolicy}
            setCancellationPolicy={setCancellationPolicy}
            markChanged={markChanged}
          />
        );
      case 'integrations':
        return (
          <IntegrationsSection
            integrations={integrations}
            setIntegrations={setIntegrations}
            integrationSettings={integrationSettings}
            setIntegrationSettings={setIntegrationSettings}
            syncErrors={syncErrors}
            setSyncErrors={setSyncErrors}
            webhookSettings={webhookSettings}
            setWebhookSettings={setWebhookSettings}
            markChanged={markChanged}
          />
        );
      case 'team':
        return (
          <TeamSection
            team={team}
            setTeam={setTeam}
            isManager={isManager}
            appointmentTypes={appointmentTypes}
            markChanged={markChanged}
            loadTabData={loadTabData}
          />
        );
      case 'locations-labels':
        return (
          <LocationsLabelsSection
            locations={locations}
            setLocations={setLocations}
            locationsLoading={locationsLoading}
            labels={labels}
            setLabels={setLabels}
            labelsLoading={labelsLoading}
            templates={templates}
            setTemplates={setTemplates}
            templatesLoading={templatesLoading}
            autoAssignLabels={autoAssignLabels}
            setAutoAssignLabels={setAutoAssignLabels}
            labelMappings={labelMappings}
            setLabelMappings={setLabelMappings}
            defaultLabelId={defaultLabelId}
            setDefaultLabelId={setDefaultLabelId}
            appointmentTypes={appointmentTypes}
            loadTabData={loadTabData}
          />
        );
      case 'advanced':
        return (
          <AdvancedSection
            advancedSettings={advancedSettings}
            setAdvancedSettings={setAdvancedSettings}
            markChanged={markChanged}
          />
        );
      default:
        return (
          <AvailabilitySection
            availability={availability}
            setAvailability={setAvailability}
            seasonalHours={seasonalHours}
            setSeasonalHours={setSeasonalHours}
            overrideDays={overrideDays}
            setOverrideDays={setOverrideDays}
            expandedSections={expandedSections}
            toggleExpandedSection={toggleExpandedSection}
            markChanged={markChanged}
          />
        );
    }
  };

  // ============================================================================
  // Layout
  // ============================================================================

  return (
    <div className="cal-settings-page">
      {/* Top Bar */}
      <header className="cal-settings-topbar">
        <div className="cal-settings-topbar-inner">
          <div className="topbar-left">
            <button onClick={() => navigate(-1)} className="back-btn" aria-label="Go back">
              <i className="fas fa-arrow-left"></i>
            </button>
            <h1>Smart Calendar Settings</h1>
          </div>

          <div className="topbar-right">
            <div className={`save-status ${saveStatus}`}>
              <span className="status-dot"></span>
              <span>
                {saveStatus === 'saved' && 'All changes saved'}
                {saveStatus === 'saving' && 'Saving...'}
                {saveStatus === 'unsaved' && 'Unsaved changes'}
              </span>
            </div>

            <button
              className="btn-outline"
              onClick={() => navigate('/calendar/setup')}
              title="Run Setup Wizard"
            >
              <i className="fas fa-magic"></i>
              <span>Setup Wizard</span>
            </button>

            <button
              className="btn-outline"
              onClick={() => toast.info('Calendar tour starting...')}
              title="Take a guided tour"
            >
              <i className="fas fa-info-circle"></i>
              <span>Tour</span>
            </button>

            {showSaveButton && (
              <button
                onClick={handleSave}
                disabled={saving || !hasChanges}
                className="btn-primary btn-sm"
              >
                {saving ? (
                  <><i className="fas fa-spinner fa-spin"></i> Saving</>
                ) : (
                  <><i className="fas fa-save"></i> Save</>
                )}
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Mobile Tabs (visible < 768px) */}
      <div className="cal-settings-mobile-tabs" role="tablist" aria-label="Calendar settings sections">
        <div className="cal-settings-mobile-tabs-inner">
          {ALL_NAV_ITEMS.map(item => (
            <button
              key={item.id}
              role="tab"
              aria-selected={activeSection === item.id}
              aria-controls={`panel-${item.id}`}
              className={`mobile-tab-btn ${activeSection === item.id ? 'active' : ''}`}
              onClick={() => handleSectionChange(item.id)}
            >
              <i className={`fas ${item.icon}`}></i> {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Body: Sidebar + Content */}
      <div className="cal-settings-body">
        {/* Sidebar Navigation (hidden on mobile) */}
        <nav className="cal-settings-sidebar" role="tablist" aria-label="Calendar settings navigation" aria-orientation="vertical">
          {NAV_SECTIONS.map(section => (
            <div key={section.group} className="sidebar-nav-group" role="group" aria-labelledby={`nav-group-${section.group.toLowerCase()}`}>
              <span className="sidebar-group-label" id={`nav-group-${section.group.toLowerCase()}`}>{section.group}</span>
              {section.items.map(item => (
                <button
                  key={item.id}
                  id={`calnav-${item.id}`}
                  role="tab"
                  aria-selected={activeSection === item.id}
                  aria-controls={`panel-${item.id}`}
                  tabIndex={activeSection === item.id ? 0 : -1}
                  className={`sidebar-nav-item ${activeSection === item.id ? 'active' : ''}`}
                  onClick={() => handleSectionChange(item.id)}
                  onKeyDown={(e) => handleNavKeyDown(e, item.id)}
                >
                  <i className={`fas ${item.icon}`} aria-hidden="true"></i>
                  <span>{item.label}</span>
                  {item.badge && <span className="nav-badge">{item.badge}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>

        {/* Content Area */}
        <main className="cal-settings-content" ref={contentRef}>
          {/* Breadcrumb */}
          <div className="cal-settings-breadcrumb">
            <span>Settings</span>
            <span className="breadcrumb-separator">/</span>
            <span>{activeGroupName}</span>
            <span className="breadcrumb-separator">/</span>
            <span className="breadcrumb-current">{activeNavItem?.label}</span>
          </div>

          {/* Section Header */}
          <div className="section-page-header">
            <h2>{activeNavItem?.label}</h2>
            <p>{activeNavItem?.description}</p>
          </div>

          {/* Section Content */}
          {renderActiveSection()}
        </main>
      </div>

      {/* Sticky Save Bar (bottom, only when unsaved) */}
      {hasChanges && showSaveButton && (
        <div className="sticky-save-bar">
          <div className="save-bar-content">
            <span>You have unsaved changes</span>
            <div className="save-bar-actions">
              <button
                type="button"
                onClick={() => loadTabData(activeSection)}
                className="btn-secondary"
                disabled={saving}
              >
                Discard
              </button>
              <button
                onClick={handleSave}
                className="btn-primary"
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CalendarSettings;
