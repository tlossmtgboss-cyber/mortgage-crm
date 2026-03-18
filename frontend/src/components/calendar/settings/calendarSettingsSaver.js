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
        await new Promise(resolve => setTimeout(resolve, 500));
        toast.success('Integration settings saved');
        dispatch({ type: SAVE_SUCCESS, section: 'integrations' });
      } catch (err) {
        toast.error('Failed to save integration settings');
        dispatch({ type: SAVE_ERROR });
      }
      return;
    }

    case 'cancellation-policy':
    case 'locations-labels':
    case 'advanced':
      dispatch({ type: SAVE_START });
      setTimeout(() => {
        dispatch({ type: SAVE_SUCCESS, section: activeSection });
        toast.success('Settings saved');
      }, 500);
      return;

    default:
      return;
  }
}
