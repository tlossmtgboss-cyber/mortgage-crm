/**
 * Calendar Settings - Data Loading Logic
 *
 * Encapsulates all tab-specific API fetch + dispatch logic.
 * Extracted from CalendarSettings.js for clarity.
 */

import { calendarSettingsAPI } from '../../../services/api';
import { toast } from '../../../utils/toast';
import {
  LOAD_SECTION_START,
  LOAD_SECTION_SUCCESS,
  LOAD_SECTION_ERROR,
  UPDATE_FIELD,
} from './calendarSettingsReducer';

/**
 * Load data for a given tab. Reads current section state from `getState()`
 * (a thunk-style accessor) so the loader always has fresh state.
 *
 * @param {string} tab        - Section id (e.g. 'availability')
 * @param {Function} dispatch - useReducer dispatch
 * @param {Function} getState - Returns current reducer state
 */
export async function loadTabData(tab, dispatch, getState) {
  dispatch({ type: LOAD_SECTION_START, section: tab });

  try {
    const sections = getState().sections;

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
              meetingDefaults: res.data.meeting_defaults
                ? { ...prev.meetingDefaults, ...res.data.meeting_defaults }
                : prev.meetingDefaults,
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

      case 'cancellation-policy': {
        try {
          const cpRes = await calendarSettingsAPI.getCancellationPolicy();
          if (cpRes) {
            const prev = sections['cancellation-policy'].data;
            // Map backend fields back to frontend model
            let policyPreset = 'moderate';
            if (cpRes.min_notice_hours <= 1) policyPreset = 'flexible';
            else if (cpRes.min_notice_hours >= 24) policyPreset = 'strict';
            dispatch({
              type: LOAD_SECTION_SUCCESS,
              section: 'cancellation-policy',
              payload: {
                data: {
                  ...prev,
                  policy: policyPreset,
                  allow_reschedule: cpRes.allow_borrower_cancel !== false,
                  reschedule_limit: cpRes.max_cancellations_per_borrower || prev.reschedule_limit,
                  require_reason: cpRes.require_reason || false,
                },
              },
            });
          } else {
            dispatch({ type: LOAD_SECTION_SUCCESS, section: 'cancellation-policy', payload: {} });
          }
        } catch (err) {
          // Endpoint may not exist yet; fall back to defaults silently
          console.warn('Cancellation policy load fell back to defaults:', err.message);
          dispatch({ type: LOAD_SECTION_SUCCESS, section: 'cancellation-policy', payload: {} });
        }
        break;
      }

      case 'advanced':
        dispatch({ type: LOAD_SECTION_SUCCESS, section: tab, payload: {} });
        break;

      case 'ai-scheduling': {
        try {
          const res = await calendarSettingsAPI.getAIScheduling();
          if (res?.data) {
            const prev = sections['ai-scheduling'].data;
            dispatch({
              type: LOAD_SECTION_SUCCESS,
              section: 'ai-scheduling',
              payload: {
                data: { ...prev, ...res.data },
              },
            });
          } else {
            dispatch({ type: LOAD_SECTION_SUCCESS, section: 'ai-scheduling', payload: {} });
          }
        } catch (err) {
          // Endpoint may not exist yet; fall back to defaults silently
          console.warn('AI scheduling settings load fell back to defaults:', err.message);
          dispatch({ type: LOAD_SECTION_SUCCESS, section: 'ai-scheduling', payload: {} });
        }
        break;
      }

      case 'ai-automation': {
        // Merged tab: load ai-scheduling data, then mark advanced as loaded too
        try {
          const res = await calendarSettingsAPI.getAIScheduling();
          if (res?.data) {
            const prev = sections['ai-scheduling'].data;
            dispatch({
              type: LOAD_SECTION_SUCCESS,
              section: 'ai-scheduling',
              payload: {
                data: { ...prev, ...res.data },
              },
            });
          } else {
            dispatch({ type: LOAD_SECTION_SUCCESS, section: 'ai-scheduling', payload: {} });
          }
        } catch (err) {
          console.warn('AI scheduling settings load fell back to defaults:', err.message);
          dispatch({ type: LOAD_SECTION_SUCCESS, section: 'ai-scheduling', payload: {} });
        }
        // Advanced section uses local defaults only (no API endpoint)
        dispatch({ type: LOAD_SECTION_SUCCESS, section: 'advanced', payload: {} });
        // Mark the merged tab itself as loaded
        dispatch({ type: LOAD_SECTION_SUCCESS, section: 'ai-automation', payload: {} });
        break;
      }

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
}
