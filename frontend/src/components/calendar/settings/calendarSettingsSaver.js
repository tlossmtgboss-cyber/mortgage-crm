/**
 * Calendar Settings - Save Dispatch Logic
 *
 * Handles persisting section data back to the API.
 * Extracted from CalendarSettings.js for clarity.
 */

import { calendarSettingsAPI } from '../../../services/api';
import { toast } from '../../../utils/toast';
import {
  SAVE_START,
  SAVE_SUCCESS,
  SAVE_ERROR,
} from './calendarSettingsReducer';

/**
 * Save the currently active section's data.
 *
 * @param {string}   activeSection - Section id (e.g. 'availability')
 * @param {Object}   sections      - All section state from the reducer
 * @param {Function} dispatch      - useReducer dispatch
 */
export async function handleSave(activeSection, sections, dispatch) {
  switch (activeSection) {
    case 'availability': {
      dispatch({ type: SAVE_START });
      try {
        const availability = sections.availability.data;
        const seasonalHours = sections.availability.seasonalHours;
        const overrideDays = sections.availability.overrideDays;
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
    }

    case 'notifications': {
      dispatch({ type: SAVE_START });
      try {
        await calendarSettingsAPI.updateNotifications(sections.notifications.data);
        toast.success('Notification preferences saved');
        dispatch({ type: SAVE_SUCCESS, section: 'notifications' });
      } catch (err) {
        toast.error('Failed to save notification preferences');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    case 'booking-page': {
      dispatch({ type: SAVE_START });
      try {
        await calendarSettingsAPI.updateBookingPage(sections['booking-page'].data.branding);
        toast.success('Booking page settings saved');
        dispatch({ type: SAVE_SUCCESS, section: 'booking-page' });
      } catch (err) {
        toast.error('Failed to save booking page settings');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    case 'team': {
      dispatch({ type: SAVE_START });
      try {
        const team = sections.team.data;
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
    }

    case 'integrations': {
      dispatch({ type: SAVE_START });
      try {
        const integrations = sections.integrations;
        const meetingDefaults = integrations.meetingDefaults || {};
        const integrationSettings = integrations.integrationSettings || {};
        await calendarSettingsAPI.updateIntegrations({
          default_meeting_mode: meetingDefaults.default_meeting_mode || 'video',
          auto_create_meeting_link: meetingDefaults.auto_create_meeting_link !== false,
          zoom_enabled: integrationSettings.zoom?.auto_generate_links !== false,
          google_meet_enabled: integrationSettings.google_meet?.auto_add !== false,
        });
        toast.success('Integration settings saved');
        dispatch({ type: SAVE_SUCCESS, section: 'integrations' });
      } catch (err) {
        toast.error('Failed to save integration settings');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    case 'cancellation-policy': {
      dispatch({ type: SAVE_START });
      try {
        const policy = sections['cancellation-policy'].data;
        // Map frontend policy presets to backend fields
        const policyMap = {
          flexible:  { min_notice_hours: 1,  max_cancellations_per_borrower: 10 },
          moderate:  { min_notice_hours: 4,  max_cancellations_per_borrower: 3 },
          strict:    { min_notice_hours: 24, max_cancellations_per_borrower: 1 },
        };
        const preset = policyMap[policy.policy] || policyMap.moderate;
        await calendarSettingsAPI.updateCancellationPolicy({
          min_notice_hours: preset.min_notice_hours,
          max_cancellations_per_borrower: preset.max_cancellations_per_borrower,
          allow_borrower_cancel: policy.allow_reschedule !== false,
          require_reason: policy.require_reason || false,
        });
        toast.success('Cancellation policy saved');
        dispatch({ type: SAVE_SUCCESS, section: 'cancellation-policy' });
      } catch (err) {
        toast.error('Failed to save cancellation policy');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    case 'locations-labels': {
      dispatch({ type: SAVE_START });
      try {
        const ll = sections['locations-labels'];
        await calendarSettingsAPI.updateLabelSettings({
          auto_assign_enabled: ll.autoAssignLabels || false,
          default_label_id: ll.defaultLabelId || null,
          label_mappings: ll.labelMappings || {},
        });
        toast.success('Label settings saved');
        dispatch({ type: SAVE_SUCCESS, section: 'locations-labels' });
      } catch (err) {
        toast.error('Failed to save label settings');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    case 'advanced': {
      dispatch({ type: SAVE_START });
      try {
        const advanced = sections.advanced.data;
        await calendarSettingsAPI.updateAdvancedSettings({
          ai_settings: {
            ai_scheduling_enabled: advanced.auto_confirm_appointments !== false,
            smart_reminders_enabled: advanced.enable_waitlist || false,
          },
        });
        toast.success('Advanced settings saved');
        dispatch({ type: SAVE_SUCCESS, section: 'advanced' });
      } catch (err) {
        toast.error('Failed to save advanced settings');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    case 'ai-scheduling': {
      dispatch({ type: SAVE_START });
      try {
        await calendarSettingsAPI.updateAIScheduling(sections['ai-scheduling'].data);
        toast.success('AI scheduling settings saved');
        dispatch({ type: SAVE_SUCCESS, section: 'ai-scheduling' });
      } catch (err) {
        toast.error('Failed to save AI scheduling settings');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    case 'ai-automation': {
      // Merged tab: save both ai-scheduling and advanced sections
      dispatch({ type: SAVE_START });
      try {
        // Save AI scheduling data
        await calendarSettingsAPI.updateAIScheduling(sections['ai-scheduling'].data);
        dispatch({ type: SAVE_SUCCESS, section: 'ai-scheduling' });

        // Save Advanced data
        const advanced = sections.advanced.data;
        await calendarSettingsAPI.updateAdvancedSettings({
          ai_settings: {
            ai_scheduling_enabled: advanced.auto_confirm_appointments !== false,
            smart_reminders_enabled: advanced.enable_waitlist || false,
          },
        });
        dispatch({ type: SAVE_SUCCESS, section: 'advanced' });

        toast.success('AI & Automation settings saved');
      } catch (err) {
        toast.error('Failed to save AI & Automation settings');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    default:
      return;
  }
}
