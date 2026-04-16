import { getToken } from '../utils/tokenStore';

/**
 * DEPRECATED — Not imported by any active component.
 * Active scheduling uses api.js (schedulerAPI, calendarAPI).
 * Retained for reference only. Do NOT import.
 *
 * Original: Unified interface for booking appointments through either:
 * - Smart Scheduler (internal)
 * - Calendly (external integration)
 */

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

/**
 * Get available time slots for scheduling
 * @param {Object} options
 * @param {string} options.userId - User ID to check availability for
 * @param {Date} options.startDate - Start of availability window
 * @param {Date} options.endDate - End of availability window
 * @param {string} options.provider - 'calendly' or 'smart_scheduler'
 * @returns {Promise<Object>} Available time slots
 */
export async function getAvailability({ userId, startDate, endDate, provider = 'smart_scheduler' }) {
  const token = getToken();

  try {
    if (provider === 'calendly') {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/availability`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: userId,
          start_time: startDate.toISOString(),
          end_time: endDate.toISOString()
        })
      });

      if (!response.ok) {
        throw new Error('Failed to fetch Calendly availability');
      }

      return await response.json();
    } else {
      // Smart Scheduler - get business hours and existing appointments
      const response = await fetch(`${API_BASE_URL}/api/v1/scheduler/config`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch scheduler settings');
      }

      const settings = await response.json();

      // Also get existing appointments
      const appointmentsResponse = await fetch(
        `${API_BASE_URL}/api/v1/scheduler/appointments?days_ahead=30`,
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      const appointments = appointmentsResponse.ok ? await appointmentsResponse.json() : [];

      return {
        success: true,
        business_hours: settings.business_hours,
        existing_appointments: appointments,
        buffer_minutes: settings.buffer_between_appointments,
        default_duration: settings.default_duration_minutes
      };
    }
  } catch (error) {
    // Error handled by returning failure status
    return { success: false, error: error.message };
  }
}

/**
 * Get the Calendly scheduling URL for embedding
 * @param {string} userId - User ID
 * @returns {Promise<Object>} Event type with scheduling URL
 */
export async function getCalendlySchedulingUrl(userId) {
  const token = getToken();

  try {
    // First check if Calendly is connected
    const statusResponse = await fetch(`${API_BASE_URL}/api/v1/calendly/status?user_id=${userId}`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!statusResponse.ok) {
      return { success: false, connected: false };
    }

    const status = await statusResponse.json();

    if (!status.is_connected) {
      return { success: false, connected: false };
    }

    // Get event types
    const eventTypesResponse = await fetch(`${API_BASE_URL}/api/v1/calendly/event-types?user_id=${userId}`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!eventTypesResponse.ok) {
      throw new Error('Failed to fetch event types');
    }

    const eventTypes = await eventTypesResponse.json();

    // Return the first active event type's scheduling URL
    const primaryEventType = eventTypes.find(et => et.active) || eventTypes[0];

    return {
      success: true,
      connected: true,
      schedulingUrl: primaryEventType?.scheduling_url,
      eventTypes: eventTypes,
      userName: status.calendly_user_name
    };
  } catch (error) {
    // Error handled by returning failure status
    return { success: false, error: error.message };
  }
}

/**
 * Book an appointment through the appropriate provider
 * @param {Object} booking
 * @param {string} booking.contactName - Name of the contact
 * @param {string} booking.contactEmail - Email of the contact
 * @param {string} booking.contactPhone - Phone number (optional)
 * @param {Date} booking.appointmentTime - Desired appointment time
 * @param {string} booking.appointmentType - Type of appointment
 * @param {number} booking.durationMinutes - Duration in minutes (optional)
 * @param {string} booking.notes - Additional notes (optional)
 * @param {string} booking.provider - 'calendly' or 'smart_scheduler'
 * @returns {Promise<Object>} Booking result
 */
export async function bookAppointment({
  contactName,
  contactEmail,
  contactPhone,
  appointmentTime,
  appointmentType = 'consultation',
  durationMinutes = 30,
  notes,
  provider = 'smart_scheduler'
}) {
  const token = getToken();

  try {
    // For now, always use Smart Scheduler for booking
    // Calendly bookings happen through their widget
    const response = await fetch(`${API_BASE_URL}/api/v1/scheduler/appointments`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        contact_name: contactName,
        contact_email: contactEmail,
        contact_phone: contactPhone,
        appointment_time: appointmentTime.toISOString(),
        appointment_type: appointmentType,
        duration_minutes: durationMinutes,
        notes
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to book appointment');
    }

    return await response.json();
  } catch (error) {
    // Error handled by returning failure status
    return { success: false, error: error.message };
  }
}

/**
 * Cancel an appointment
 * @param {string} appointmentId - Appointment ID to cancel
 * @param {string} reason - Cancellation reason
 * @param {string} provider - 'calendly' or 'smart_scheduler'
 * @returns {Promise<Object>} Cancellation result
 */
export async function cancelAppointment(appointmentId, reason, provider = 'smart_scheduler') {
  const token = getToken();

  try {
    let endpoint;

    if (provider === 'calendly') {
      endpoint = `${API_BASE_URL}/api/v1/calendly/bookings/${encodeURIComponent(appointmentId)}/cancel`;
    } else {
      endpoint = `${API_BASE_URL}/api/v1/scheduler/appointments/${appointmentId}/cancel`;
    }

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ reason })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to cancel appointment');
    }

    return { success: true };
  } catch (error) {
    // Error handled by returning failure status
    return { success: false, error: error.message };
  }
}

/**
 * Get upcoming appointments
 * @param {Object} options
 * @param {number} options.daysAhead - Number of days to look ahead
 * @param {string} options.provider - 'calendly' or 'smart_scheduler'
 * @param {string} options.userId - User ID (required for Calendly)
 * @returns {Promise<Object>} Appointments list
 */
export async function getUpcomingAppointments({ daysAhead = 7, provider = 'smart_scheduler', userId }) {
  const token = getToken();

  try {
    let endpoint;

    if (provider === 'calendly' && userId) {
      endpoint = `${API_BASE_URL}/api/v1/calendly/bookings?user_id=${userId}&days_ahead=${daysAhead}`;
    } else {
      endpoint = `${API_BASE_URL}/api/v1/scheduler/appointments?days_ahead=${daysAhead}`;
    }

    const response = await fetch(endpoint, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error('Failed to fetch appointments');
    }

    return await response.json();
  } catch (error) {
    // Error handled by returning empty array
    return [];
  }
}

/**
 * Check which scheduling provider is configured
 * @param {string} userId - User ID to check
 * @returns {Promise<Object>} Provider status
 */
export async function getSchedulingProvider(userId) {
  const token = getToken();

  try {
    // Check Calendly status first
    const calendlyResponse = await fetch(`${API_BASE_URL}/api/v1/calendly/status?user_id=${userId}`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (calendlyResponse.ok) {
      const calendlyStatus = await calendlyResponse.json();
      if (calendlyStatus.is_connected) {
        return {
          provider: 'calendly',
          configured: true,
          calendly: calendlyStatus
        };
      }
    }

    // Fall back to Smart Scheduler
    const schedulerResponse = await fetch(`${API_BASE_URL}/api/v1/scheduler/config`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (schedulerResponse.ok) {
      const loanOfficers = await schedulerResponse.json();
      return {
        provider: 'smart_scheduler',
        configured: loanOfficers.length > 0,
        loanOfficerCount: loanOfficers.length
      };
    }

    return { provider: null, configured: false };
  } catch (error) {
    // Error handled by returning failure status
    return { provider: null, configured: false, error: error.message };
  }
}

export default {
  getAvailability,
  getCalendlySchedulingUrl,
  bookAppointment,
  cancelAppointment,
  getUpcomingAppointments,
  getSchedulingProvider
};
