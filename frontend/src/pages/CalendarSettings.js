/**
 * Perennia AI - Calendar Settings (Container)
 *
 * Thin container that manages cross-cutting state, navigation, data loading,
 * and save dispatch. Each tab's UI is delegated to a section component in
 * ./calendar-settings/.
 *
 * State is centralized via useReducer (settingsReducer).
 */

import { useReducer, useEffect, useCallback, useRef } from 'react';
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
import AISchedulingSection from './calendar-settings/AISchedulingSection';
import FollowUpCadenceSection from './calendar-settings/FollowUpCadenceSection';

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
    group: 'AI & Automation',
    items: [
      { id: 'ai-scheduling', label: 'AI Scheduling', icon: 'fa-robot', description: 'Configure how AI agents schedule appointments on your calendar' },
      { id: 'follow-up-cadence', label: 'Follow-Up Cadence', icon: 'fa-sync-alt', description: 'Automated outreach sequences for document collection and borrower follow-up' },
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
// Action types
// ============================================================================

const SET_TAB = 'SET_TAB';
const LOAD_SECTION_START = 'LOAD_SECTION_START';
const LOAD_SECTION_SUCCESS = 'LOAD_SECTION_SUCCESS';
const LOAD_SECTION_ERROR = 'LOAD_SECTION_ERROR';
const UPDATE_FIELD = 'UPDATE_FIELD';
const SAVE_START = 'SAVE_START';
const SAVE_SUCCESS = 'SAVE_SUCCESS';
const SAVE_ERROR = 'SAVE_ERROR';
const RESET_SECTION = 'RESET_SECTION';

// ============================================================================
// Default data for each section
// ============================================================================

const DEFAULT_AVAILABILITY = {
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
};

const DEFAULT_NOTIFICATIONS = {
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
};

const DEFAULT_BOOKING_PAGE = {
  branding: {
    logo_url: null, primary_color: '#218D8D', secondary_color: '#e6f5f5',
    tagline: '', welcome_message: 'Schedule a time to meet with us', show_branding: true,
  },
  booking_links: [],
};

const DEFAULT_CANCELLATION_POLICY = {
  policy: 'moderate', allow_reschedule: true, reschedule_limit: 2, require_reason: false,
};

const DEFAULT_ADVANCED = {
  calendar_feed_enabled: false, auto_confirm_appointments: true,
  show_timezone_selector: true, enable_waitlist: false,
};

const DEFAULT_INTEGRATIONS = {
  google: { connected: false }, outlook: { connected: false }, zoom: { connected: false },
  google_meet: { connected: false }, ical: { connected: false, feed_url: '', subscriber_count: 0 },
};

const DEFAULT_INTEGRATION_SETTINGS = {
  google: { two_way_sync: true, conflict_resolution: 'crm_wins', sync_frequency: '15' },
  outlook: { two_way_sync: true, conflict_resolution: 'crm_wins', sync_frequency: '15' },
  zoom: { auto_generate_links: true, waiting_room: true, require_password: true, default_duration: 30 },
  google_meet: { auto_add: true, default_duration: 30 },
};

const DEFAULT_WEBHOOK_SETTINGS = {
  api_key: '', webhook_url: '',
  events: {
    'appointment.created': true, 'appointment.updated': true,
    'appointment.cancelled': true, 'appointment.rescheduled': true,
    'appointment.reminder': false, 'appointment.no_show': false,
  },
};

const DEFAULT_TEAM = {
  assignment_strategy: 'round_robin', apply_to_new_only: true,
  members: [], total_members: 0,
  overflow: { enabled: false, max_overflow_pct: 20, notify_user_ids: [], auto_expand_hours: false },
  permissions: { members_see_calendars: true, members_reschedule_others: false, only_managers_modify: true },
  weekly_coverage: null, utilization_pct: 0,
};

const DEFAULT_EXPANDED_SECTIONS = {
  'weekly-schedule': true, 'week-overview': true, 'schedule-templates': false,
  'buffer-times': true, 'date-overrides': false, 'holidays': false,
  'seasonal-hours': false, 'override-days': false, 'daily-limits': false,
};

// ============================================================================
// Initial state
// ============================================================================

const initialState = {
  activeSection: 'availability',
  loading: true,
  saving: false,
  hasChanges: false,
  saveStatus: 'saved', // 'saved' | 'saving' | 'unsaved'

  sections: {
    availability: {
      data: DEFAULT_AVAILABILITY,
      seasonalHours: [],
      overrideDays: [],
      expandedSections: DEFAULT_EXPANDED_SECTIONS,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    'appointment-types': {
      data: [],
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    notifications: {
      data: DEFAULT_NOTIFICATIONS,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    'booking-page': {
      data: DEFAULT_BOOKING_PAGE,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    'cancellation-policy': {
      data: DEFAULT_CANCELLATION_POLICY,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    advanced: {
      data: DEFAULT_ADVANCED,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    integrations: {
      data: DEFAULT_INTEGRATIONS,
      integrationSettings: DEFAULT_INTEGRATION_SETTINGS,
      syncErrors: [],
      webhookSettings: DEFAULT_WEBHOOK_SETTINGS,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    team: {
      data: DEFAULT_TEAM,
      isManager: false,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    'locations-labels': {
      locations: [],
      locationsLoading: false,
      labels: [],
      labelsLoading: false,
      templates: [],
      templatesLoading: false,
      autoAssignLabels: false,
      labelMappings: {},
      defaultLabelId: null,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
  },
};

// ============================================================================
// Reducer
// ============================================================================

function settingsReducer(state, action) {
  switch (action.type) {
    case SET_TAB:
      return {
        ...state,
        activeSection: action.payload,
        hasChanges: false,
        saveStatus: 'saved',
      };

    case LOAD_SECTION_START:
      return {
        ...state,
        loading: true,
        sections: {
          ...state.sections,
          [action.section]: {
            ...state.sections[action.section],
            loading: true,
            error: null,
          },
        },
      };

    case LOAD_SECTION_SUCCESS: {
      const section = action.section;
      const currentSection = state.sections[section];
      return {
        ...state,
        loading: false,
        hasChanges: false,
        saveStatus: 'saved',
        sections: {
          ...state.sections,
          [section]: {
            ...currentSection,
            ...action.payload,
            loading: false,
            error: null,
            dirty: false,
            lastSaved: action.payload.data || currentSection.data,
          },
        },
      };
    }

    case LOAD_SECTION_ERROR:
      return {
        ...state,
        loading: false,
        hasChanges: false,
        saveStatus: 'saved',
        sections: {
          ...state.sections,
          [action.section]: {
            ...state.sections[action.section],
            loading: false,
            error: action.error,
          },
        },
      };

    case UPDATE_FIELD: {
      const { section, field, value } = action;
      const currentSection = state.sections[section];

      // Support functional updates (same as useState callback pattern)
      const resolvedValue = typeof value === 'function' ? value(currentSection[field]) : value;

      return {
        ...state,
        hasChanges: true,
        saveStatus: 'unsaved',
        sections: {
          ...state.sections,
          [section]: {
            ...currentSection,
            [field]: resolvedValue,
            dirty: true,
          },
        },
      };
    }

    case SAVE_START:
      return {
        ...state,
        saving: true,
        saveStatus: 'saving',
      };

    case SAVE_SUCCESS: {
      const section = action.section;
      const currentSection = state.sections[section];
      return {
        ...state,
        saving: false,
        hasChanges: false,
        saveStatus: 'saved',
        sections: {
          ...state.sections,
          [section]: {
            ...currentSection,
            dirty: false,
            lastSaved: currentSection.data,
          },
        },
      };
    }

    case SAVE_ERROR:
      return {
        ...state,
        saving: false,
        saveStatus: 'unsaved',
      };

    case RESET_SECTION: {
      const section = action.section;
      const currentSection = state.sections[section];
      if (currentSection.lastSaved) {
        return {
          ...state,
          hasChanges: false,
          saveStatus: 'saved',
          sections: {
            ...state.sections,
            [section]: {
              ...currentSection,
              data: currentSection.lastSaved,
              dirty: false,
            },
          },
        };
      }
      return state;
    }

    default:
      return state;
  }
}

// ============================================================================
// Component
// ============================================================================

function CalendarSettings() {
  const navigate = useNavigate();
  const contentRef = useRef(null);
  const [state, dispatch] = useReducer(settingsReducer, initialState);

  // Destructure top-level state for convenience
  const { activeSection, loading, saving, hasChanges, saveStatus, sections } = state;

  // Section data aliases
  const availability = sections.availability.data;
  const seasonalHours = sections.availability.seasonalHours;
  const overrideDays = sections.availability.overrideDays;
  const expandedSections = sections.availability.expandedSections;
  const appointmentTypes = sections['appointment-types'].data;
  const notifications = sections.notifications.data;
  const bookingPage = sections['booking-page'].data;
  const cancellationPolicy = sections['cancellation-policy'].data;
  const advancedSettings = sections.advanced.data;
  const integrations = sections.integrations.data;
  const integrationSettings = sections.integrations.integrationSettings;
  const syncErrors = sections.integrations.syncErrors;
  const webhookSettings = sections.integrations.webhookSettings;
  const team = sections.team.data;
  const isManager = sections.team.isManager;
  const locations = sections['locations-labels'].locations;
  const locationsLoading = sections['locations-labels'].locationsLoading;
  const labels = sections['locations-labels'].labels;
  const labelsLoading = sections['locations-labels'].labelsLoading;
  const templates = sections['locations-labels'].templates;
  const templatesLoading = sections['locations-labels'].templatesLoading;
  const autoAssignLabels = sections['locations-labels'].autoAssignLabels;
  const labelMappings = sections['locations-labels'].labelMappings;
  const defaultLabelId = sections['locations-labels'].defaultLabelId;

  // ========== Derived ==========

  const activeNavItem = ALL_NAV_ITEMS.find(item => item.id === activeSection);
  const activeGroupName = NAV_SECTIONS.find(s => s.items.some(i => i.id === activeSection))?.group || '';
  const showSaveButton = ['availability', 'notifications', 'booking-page', 'team', 'integrations', 'cancellation-policy', 'locations-labels', 'advanced'].includes(activeSection);

  // ============================================================================
  // Setter factories (stable callbacks that mimic useState setters for children)
  // ============================================================================

  const setAvailability = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'availability', field: 'data', value: valueOrFn });
  }, []);

  const setSeasonalHours = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'availability', field: 'seasonalHours', value: valueOrFn });
  }, []);

  const setOverrideDays = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'availability', field: 'overrideDays', value: valueOrFn });
  }, []);

  const setAppointmentTypes = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'appointment-types', field: 'data', value: valueOrFn });
  }, []);

  const setNotifications = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'notifications', field: 'data', value: valueOrFn });
  }, []);

  const setBookingPage = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'booking-page', field: 'data', value: valueOrFn });
  }, []);

  const setCancellationPolicy = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'cancellation-policy', field: 'data', value: valueOrFn });
  }, []);

  const setAdvancedSettings = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'advanced', field: 'data', value: valueOrFn });
  }, []);

  const setIntegrations = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'data', value: valueOrFn });
  }, []);

  const setIntegrationSettings = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'integrationSettings', value: valueOrFn });
  }, []);

  const setSyncErrors = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'syncErrors', value: valueOrFn });
  }, []);

  const setWebhookSettings = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'webhookSettings', value: valueOrFn });
  }, []);

  const setTeam = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'team', field: 'data', value: valueOrFn });
  }, []);

  const setLocations = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'locations', value: valueOrFn });
  }, []);

  const setLabels = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'labels', value: valueOrFn });
  }, []);

  const setTemplates = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'templates', value: valueOrFn });
  }, []);

  const setAutoAssignLabels = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'autoAssignLabels', value: valueOrFn });
  }, []);

  const setLabelMappings = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'labelMappings', value: valueOrFn });
  }, []);

  const setDefaultLabelId = useCallback((valueOrFn) => {
    dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'defaultLabelId', value: valueOrFn });
  }, []);

  // ============================================================================
  // Data Loading
  // ============================================================================

  useEffect(() => {
    loadTabData(activeSection);
  }, [activeSection]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadTabData = async (tab) => {
    dispatch({ type: LOAD_SECTION_START, section: tab });
    try {
      switch (tab) {
        case 'availability': {
          const res = await calendarSettingsAPI.getAvailability();
          if (res?.data) {
            const prev = sections.availability;
            dispatch({
              type: LOAD_SECTION_SUCCESS,
              section: 'availability',
              payload: {
                data: {
                  ...prev.data, ...res.data,
                  blocked_holidays: res.data.blocked_holidays || prev.data.blocked_holidays,
                  custom_blocked_dates: res.data.custom_blocked_dates || prev.data.custom_blocked_dates,
                },
                seasonalHours: res.data.seasonal_hours || prev.seasonalHours,
                overrideDays: res.data.override_days || prev.overrideDays,
              },
            });
          } else {
            dispatch({ type: LOAD_SECTION_SUCCESS, section: 'availability', payload: {} });
          }
          break;
        }
        case 'appointment-types': {
          const res = await calendarSettingsAPI.getAppointmentTypes();
          dispatch({
            type: LOAD_SECTION_SUCCESS,
            section: 'appointment-types',
            payload: {
              data: res?.data?.appointment_types || sections['appointment-types'].data,
            },
          });
          break;
        }
        case 'notifications': {
          const res = await calendarSettingsAPI.getNotifications();
          const prev = sections.notifications.data;
          dispatch({
            type: LOAD_SECTION_SUCCESS,
            section: 'notifications',
            payload: {
              data: res?.data ? { ...prev, ...res.data } : prev,
            },
          });
          break;
        }
        case 'booking-page': {
          const res = await calendarSettingsAPI.getBookingPage();
          if (res?.data) {
            const prev = sections['booking-page'].data;
            dispatch({
              type: LOAD_SECTION_SUCCESS,
              section: 'booking-page',
              payload: {
                data: {
                  branding: { ...prev.branding, ...(res.data.branding || {}) },
                  booking_links: res.data.booking_links || [],
                },
              },
            });
          } else {
            dispatch({ type: LOAD_SECTION_SUCCESS, section: 'booking-page', payload: {} });
          }
          break;
        }
        case 'integrations': {
          const res = await calendarSettingsAPI.getIntegrations();
          if (res?.data) {
            const prev = sections.integrations;
            dispatch({
              type: LOAD_SECTION_SUCCESS,
              section: 'integrations',
              payload: {
                data: {
                  ...prev.data, ...res.data,
                  google: { ...prev.data.google, ...(res.data.google || {}) },
                  outlook: { ...prev.data.outlook, ...(res.data.outlook || {}) },
                  zoom: { ...prev.data.zoom, ...(res.data.zoom || {}) },
                  google_meet: { ...prev.data.google_meet, ...(res.data.google_meet || {}) },
                  ical: { ...prev.data.ical, ...(res.data.ical || {}) },
                },
                syncErrors: res.data.sync_errors || prev.syncErrors,
                webhookSettings: res.data.webhook_settings
                  ? { ...prev.webhookSettings, ...res.data.webhook_settings }
                  : prev.webhookSettings,
                integrationSettings: res.data.integration_settings
                  ? { ...prev.integrationSettings, ...res.data.integration_settings }
                  : prev.integrationSettings,
              },
            });
          } else {
            dispatch({ type: LOAD_SECTION_SUCCESS, section: 'integrations', payload: {} });
          }
          break;
        }
        case 'team': {
          try {
            const res = await calendarSettingsAPI.getTeam();
            if (res?.data) {
              const prev = sections.team.data;
              dispatch({
                type: LOAD_SECTION_SUCCESS,
                section: 'team',
                payload: {
                  data: {
                    ...prev, ...res.data,
                    overflow: { ...prev.overflow, ...(res.data.overflow || {}) },
                    permissions: { ...prev.permissions, ...(res.data.permissions || {}) },
                    members: (res.data.members || []).map(m => ({
                      ...m,
                      specialties: m.specialties || [],
                      weekly_appointments: m.weekly_appointments || 0,
                      weekly_capacity: m.weekly_capacity || (m.max_daily_appointments || 8) * 5,
                    })),
                  },
                  isManager: true,
                },
              });
            } else {
              dispatch({ type: LOAD_SECTION_SUCCESS, section: 'team', payload: { isManager: true } });
            }
          } catch (err) {
            if (err.response?.status === 403) {
              dispatch({
                type: LOAD_SECTION_SUCCESS,
                section: 'team',
                payload: { isManager: false },
              });
            } else {
              throw err;
            }
          }
          break;
        }
        case 'locations-labels': {
          // Locations, labels, and templates load independently with sub-loading states
          const payload = {};

          // Locations
          dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'locationsLoading', value: true });
          try {
            const locRes = await calendarSettingsAPI.getLocations();
            if (locRes?.data?.locations) payload.locations = locRes.data.locations;
          } catch (err) {
            console.error('Failed to load locations:', err);
          }
          dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'locationsLoading', value: false });

          // Labels
          dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'labelsLoading', value: true });
          try {
            const labelsRes = await calendarSettingsAPI.getLabels();
            if (labelsRes?.data?.labels) payload.labels = labelsRes.data.labels;
            if (labelsRes?.data?.auto_assign_enabled !== undefined) payload.autoAssignLabels = labelsRes.data.auto_assign_enabled;
            if (labelsRes?.data?.label_mappings) payload.labelMappings = labelsRes.data.label_mappings;
            if (labelsRes?.data?.default_label_id) payload.defaultLabelId = labelsRes.data.default_label_id;
          } catch (err) {
            console.error('Failed to load labels:', err);
          }
          dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'labelsLoading', value: false });

          // Templates
          dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'templatesLoading', value: true });
          try {
            const templatesRes = await calendarSettingsAPI.getTemplates();
            if (templatesRes?.data?.templates) payload.templates = templatesRes.data.templates;
          } catch (err) {
            console.error('Failed to load templates:', err);
          }
          dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'templatesLoading', value: false });

          dispatch({ type: LOAD_SECTION_SUCCESS, section: 'locations-labels', payload });
          break;
        }
        case 'cancellation-policy':
        case 'advanced':
          dispatch({ type: LOAD_SECTION_SUCCESS, section: tab, payload: {} });
          break;
        default:
          dispatch({ type: LOAD_SECTION_SUCCESS, section: tab, payload: {} });
          break;
      }
    } catch (err) {
      console.error(`Failed to load ${tab}:`, err);
      if (err.response?.status !== 403) {
        toast.error(`Failed to load ${tab} settings`);
      }
      dispatch({ type: LOAD_SECTION_ERROR, section: tab, error: err.message || 'Load failed' });
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
    dispatch({ type: SET_TAB, payload: sectionId });
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
    dispatch({ type: UPDATE_FIELD, section: activeSection, field: 'dirty', value: true });
  }, [activeSection]);

  const toggleExpandedSection = useCallback((key) => {
    dispatch({
      type: UPDATE_FIELD,
      section: 'availability',
      field: 'expandedSections',
      value: (prev) => ({ ...prev, [key]: !prev[key] }),
    });
  }, []);

  const handleSave = async () => {
    switch (activeSection) {
      case 'availability':
        dispatch({ type: SAVE_START });
        try {
          await calendarSettingsAPI.updateAvailability({
            ...availability, seasonal_hours: seasonalHours, override_days: overrideDays,
          });
          toast.success('Availability settings saved');
          dispatch({ type: SAVE_SUCCESS, section: 'availability' });
        } catch (err) {
          toast.error('Failed to save availability settings');
          dispatch({ type: SAVE_ERROR });
        }
        return;

      case 'notifications':
        dispatch({ type: SAVE_START });
        try {
          await calendarSettingsAPI.updateNotifications(notifications);
          toast.success('Notification preferences saved');
          dispatch({ type: SAVE_SUCCESS, section: 'notifications' });
        } catch (err) {
          toast.error('Failed to save notification preferences');
          dispatch({ type: SAVE_ERROR });
        }
        return;

      case 'booking-page':
        dispatch({ type: SAVE_START });
        try {
          await calendarSettingsAPI.updateBookingPage(bookingPage.branding);
          toast.success('Booking page settings saved');
          dispatch({ type: SAVE_SUCCESS, section: 'booking-page' });
        } catch (err) {
          toast.error('Failed to save booking page settings');
          dispatch({ type: SAVE_ERROR });
        }
        return;

      case 'team':
        dispatch({ type: SAVE_START });
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
          dispatch({ type: SAVE_SUCCESS, section: 'team' });
        } catch (err) {
          toast.error('Failed to save team settings');
          dispatch({ type: SAVE_ERROR });
        }
        return;

      case 'integrations':
        dispatch({ type: SAVE_START });
        try {
          await new Promise(resolve => setTimeout(resolve, 500));
          toast.success('Integration settings saved');
          dispatch({ type: SAVE_SUCCESS, section: 'integrations' });
        } catch (err) {
          toast.error('Failed to save integration settings');
          dispatch({ type: SAVE_ERROR });
        }
        return;

      case 'cancellation-policy':
      case 'locations-labels':
      case 'advanced':
        dispatch({ type: SAVE_START });
        setTimeout(() => {
          dispatch({ type: SAVE_SUCCESS, section: activeSection });
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
      case 'ai-scheduling':
        return (
          <AISchedulingSection
            markChanged={markChanged}
          />
        );
      case 'follow-up-cadence':
        return (
          <FollowUpCadenceSection />
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
