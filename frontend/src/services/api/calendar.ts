/**
 * Calendar domain -- events, scheduler, analytics, labels, team calendar, settings, process templates.
 */
import api from './client';
import { ensureArray } from '../../utils/arrayHelpers.js';

// Calendar Events
export const calendarAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/calendar/events', { params });
    return ensureArray(response.data, 'events');
  },
  getById: async (id: number) => {
    const response = await api.get(`/api/v1/calendar/events/${id}`);
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/api/v1/calendar/events', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.patch(`/api/v1/calendar/events/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    await api.delete(`/api/v1/calendar/events/${id}`);
  },
};

// CRM Calendar Sync API (syncs with Salesforce)
export const crmCalendarAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/calendar/events', { params });
    return ensureArray(response.data, 'events');
  },
  getById: async (id: number) => {
    const response = await api.get(`/api/calendar/events/${id}`);
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/api/calendar/events', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/api/calendar/events/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    await api.delete(`/api/calendar/events/${id}`);
  },
  resync: async (id: number) => {
    const response = await api.post(`/api/calendar/events/${id}/resync`);
    return response.data;
  },
  getSyncStatus: async () => {
    const response = await api.get('/api/calendar/sync/status');
    return response.data;
  },
  getSyncHistory: async (params = {}) => {
    const response = await api.get('/api/calendar/sync/history', { params });
    return response.data;
  },
  triggerSync: async () => {
    const response = await api.post('/api/calendar/sync/trigger');
    return response.data;
  },
};

// Unified Calendar API (merges calendar, scheduler, and CRM events server-side)
export const unifiedCalendarAPI = {
  getAll: async (params = {}, { signal }: { signal?: AbortSignal } = {}) => {
    const response = await api.get('/api/v1/calendar/unified', { params, signal });
    return response.data;
  },
};

// Scheduler Appointments API
export const schedulerAPI = {
  getAppointments: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/appointments', { params });
    return ensureArray(response.data, 'appointments');
  },
  getAppointmentById: async (id: number) => {
    const response = await api.get(`/api/v1/scheduler/appointments/${id}`);
    return response.data;
  },
  createAppointment: async (data: any) => {
    const response = await api.post('/api/v1/scheduler/appointments', data);
    return response.data;
  },
  updateAppointment: async (id: number, data: any) => {
    const response = await api.put(`/api/v1/scheduler/appointments/${id}`, data);
    return response.data;
  },
  cancelAppointment: async (id: number, reason: string) => {
    const response = await api.post(`/api/v1/scheduler/appointments/${id}/cancel`, { reason });
    return response.data;
  },
  sendReminder: async (id: number) => {
    const response = await api.post(`/api/v1/scheduler/appointments/${id}/remind`);
    return response.data;
  },
  getAppointmentTimeline: async (id: number) => {
    const response = await api.get(`/api/v1/scheduler/appointments/${id}/timeline`);
    return response.data;
  },
  searchAppointments: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/search', { params, paramsSerializer: (p: Record<string, any>) => {
      const parts: string[] = [];
      for (const [key, value] of Object.entries(p)) {
        if (value === undefined || value === null || value === '') continue;
        if (Array.isArray(value)) {
          value.forEach((v: any) => parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(v)}`));
        } else {
          parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
        }
      }
      return parts.join('&');
    }});
    return response.data;
  },
  searchSuggestions: async (q: string) => {
    const response = await api.get('/api/v1/scheduler/search/suggestions', { params: { q } });
    return response.data;
  },
  getNotifications: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/notifications', { params });
    return response.data;
  },
  markNotificationRead: async (notificationId: number) => {
    const response = await api.put(`/api/v1/scheduler/notifications/${notificationId}/read`);
    return response.data;
  },
  markAllNotificationsRead: async () => {
    const response = await api.put('/api/v1/scheduler/notifications/read-all');
    return response.data;
  },
  checkConflicts: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/conflicts/check', { params });
    return response.data;
  },
  listConflicts: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/conflicts/list', { params });
    return response.data;
  },
  resolveConflict: async (appointmentId: number, data: any) => {
    const response = await api.post(`/api/v1/scheduler/conflicts/resolve/${appointmentId}`, data);
    return response.data;
  },
};

// Calendar Analytics API (dashboard metrics, trends, breakdowns)
export const calendarAnalyticsAPI = {
  getOverview: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/overview', { params });
    return response.data;
  },
  getTrends: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/trends', { params });
    return response.data;
  },
  getByType: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/by-type', { params });
    return response.data;
  },
  getByLO: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/by-lo', { params });
    return response.data;
  },
  getAppointmentOutcomes: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/appointment-outcomes', { params });
    return response.data;
  },
  getAppointmentTypeEffectiveness: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/appointment-type-effectiveness', { params });
    return response.data;
  },
};

// Calendar Labels API (color-coded appointment categorization)
export const calendarLabelsAPI = {
  getLabels: async () => {
    const response = await api.get('/api/v1/scheduler/labels');
    return response.data;
  },
  createLabel: async (data: any) => {
    const response = await api.post('/api/v1/scheduler/labels', data);
    return response.data;
  },
  updateLabel: async (id: number, data: any) => {
    const response = await api.put(`/api/v1/scheduler/labels/${id}`, data);
    return response.data;
  },
  deleteLabel: async (id: number) => {
    const response = await api.delete(`/api/v1/scheduler/labels/${id}`);
    return response.data;
  },
  reorderLabels: async (orderedIds: number[]) => {
    const response = await api.put('/api/v1/scheduler/labels/reorder', { order: orderedIds });
    return response.data;
  },
  assignLabels: async (appointmentId: number, labelIds: number[]) => {
    const response = await api.post('/api/v1/scheduler/labels/assign', {
      appointment_id: appointmentId,
      label_ids: labelIds,
    });
    return response.data;
  },
  unassignLabels: async (appointmentId: number, labelIds: number[]) => {
    const response = await api.delete('/api/v1/scheduler/labels/assign', {
      data: { appointment_id: appointmentId, label_ids: labelIds },
    });
    return response.data;
  },
  getAppointmentLabels: async (appointmentId: number) => {
    const response = await api.get(`/api/v1/scheduler/labels/appointment/${appointmentId}`);
    return response.data;
  },
};

// Team Calendar API (manager/admin multi-LO schedule view)
export const teamCalendarAPI = {
  getTeamCalendar: async (startDate: string, endDate: string, loIds: number[] | null = null) => {
    const params: any = { start_date: startDate, end_date: endDate };
    if (loIds) params.lo_ids = loIds;
    const response = await api.get('/api/v1/calendar/team', { params });
    return response.data;
  },
  getCapacity: async (startDate: string, endDate: string, loIds: number[] | null = null) => {
    const params: any = { start_date: startDate, end_date: endDate };
    if (loIds) params.lo_ids = loIds;
    const response = await api.get('/api/v1/calendar/team/capacity', { params });
    return response.data;
  },
  reassignAppointment: async (appointmentId: number, newLoId: number, reason: string | null = null) => {
    const response = await api.post('/api/v1/calendar/team/reassign', {
      appointment_id: appointmentId,
      new_lo_id: newLoId,
      reason,
    });
    return response.data;
  },
  getAvailabilityMatrix: async (targetDate: string, durationMinutes = 30, loIds: number[] | null = null) => {
    const params: any = { target_date: targetDate, duration_minutes: durationMinutes };
    if (loIds) params.lo_ids = loIds;
    const response = await api.get('/api/v1/calendar/team/availability-matrix', { params });
    return response.data;
  },
};

// Calendar Settings API (availability, appointment types, notifications, booking page, integrations, team)
export const calendarSettingsAPI = {
  // Availability
  getAvailability: async () => {
    const response = await api.get('/api/v1/calendar-settings/availability');
    return response.data;
  },
  updateAvailability: async (data: any) => {
    const response = await api.put('/api/v1/calendar-settings/availability', data);
    return response.data;
  },
  getAvailabilitySource: async () => {
    const response = await api.get('/api/v1/scheduler/settings/availability-source');
    return response.data;
  },
  // Appointment Types
  getAppointmentTypes: async () => {
    const response = await api.get('/api/v1/calendar-settings/appointment-types');
    return response.data;
  },
  createAppointmentType: async (data: any) => {
    const response = await api.post('/api/v1/calendar-settings/appointment-types', data);
    return response.data;
  },
  updateAppointmentType: async (id: number, data: any) => {
    const response = await api.put(`/api/v1/calendar-settings/appointment-types/${id}`, data);
    return response.data;
  },
  deleteAppointmentType: async (id: number) => {
    const response = await api.delete(`/api/v1/calendar-settings/appointment-types/${id}`);
    return response.data;
  },
  reorderAppointmentTypes: async (typeIds: number[]) => {
    const response = await api.put('/api/v1/calendar-settings/appointment-types/reorder', { type_ids: typeIds });
    return response.data;
  },
  // Notifications
  getNotifications: async () => {
    const response = await api.get('/api/v1/calendar-settings/notifications');
    return response.data;
  },
  updateNotifications: async (data: any) => {
    const response = await api.put('/api/v1/calendar-settings/notifications', data);
    return response.data;
  },
  // Booking Page
  getBookingPage: async () => {
    const response = await api.get('/api/v1/calendar-settings/booking-page');
    return response.data;
  },
  updateBookingPage: async (data: any) => {
    const response = await api.put('/api/v1/calendar-settings/booking-page', data);
    return response.data;
  },
  // Integrations
  getIntegrations: async () => {
    const response = await api.get('/api/v1/calendar-settings/integrations');
    return response.data;
  },
  updateIntegrations: async (data: any) => {
    const response = await api.put('/api/v1/scheduler/settings/integrations', data);
    return response.data;
  },
  // Cancellation Policy
  getCancellationPolicy: async () => {
    const response = await api.get('/api/v1/scheduler/cancellation-policy');
    return response.data;
  },
  updateCancellationPolicy: async (data: any) => {
    const response = await api.put('/api/v1/scheduler/cancellation-policy', data);
    return response.data;
  },
  // Advanced Settings
  getAdvancedSettings: async () => {
    const response = await api.get('/api/v1/scheduler/settings/all');
    return { data: (response.data as any)?.advanced || {} };
  },
  updateAdvancedSettings: async (data: any) => {
    const response = await api.put('/api/v1/scheduler/settings/advanced', data);
    return response.data;
  },
  // Team
  getTeam: async () => {
    const response = await api.get('/api/v1/calendar-settings/team');
    return response.data;
  },
  updateTeam: async (data: any) => {
    const response = await api.put('/api/v1/calendar-settings/team', data);
    return response.data;
  },
  inviteTeamMember: async (data: any) => {
    const response = await api.post('/api/v1/calendar-settings/team/invite', data);
    return response.data;
  },
  getLabels: async () => {
    try {
      const response = await api.get('/api/v1/scheduler/settings/all');
      const labels = (response.data as any)?.data?.labels || [];
      return { data: { labels, auto_assign_enabled: false, label_mappings: [], default_label_id: null } };
    } catch {
      return { data: { labels: [] } };
    }
  },
  createLabel: async (data: any) => {
    const response = await api.post('/api/v1/scheduler/labels', data);
    return response.data;
  },
  updateLabel: async (id: number, data: any) => {
    const response = await api.put(`/api/v1/scheduler/labels/${id}`, data);
    return response.data;
  },
  deleteLabel: async (id: number) => {
    const response = await api.delete(`/api/v1/scheduler/labels/${id}`);
    return response.data;
  },
  reorderLabels: async (labelIds: number[]) => {
    const response = await api.put('/api/v1/scheduler/labels/reorder', { label_ids: labelIds });
    return response.data;
  },
  updateLabelSettings: async (data: any) => {
    const response = await api.put('/api/v1/scheduler/settings/labels', data);
    return response.data;
  },
  // Appointment Templates -- no backend yet, return empty defaults
  getTemplates: async () => {
    return { status: 'success', data: { templates: [] } };
  },
  deleteTemplate: async () => {
    return { status: 'success', data: {} };
  },
  setDefaultTemplate: async () => {
    return { status: 'success', data: {} };
  },
  createTemplate: async () => {
    return { status: 'success', data: {} };
  },
  updateTemplate: async () => {
    return { status: 'success', data: {} };
  },
  duplicateTemplate: async () => {
    return { status: 'success', data: {} };
  },
  // Locations -- no backend yet, return empty defaults
  getLocations: async () => {
    return { status: 'success', data: { locations: [] } };
  },
  createLocation: async () => {
    return { status: 'success', data: {} };
  },
  updateLocation: async () => {
    return { status: 'success', data: {} };
  },
  deleteLocation: async () => {
    return { status: 'success', data: {} };
  },
  reorderLocations: async () => {
    return { status: 'success', data: {} };
  },
  setDefaultLocation: async () => {
    return { status: 'success', data: {} };
  },
  setDefaultLabel: async (id: number) => {
    const response = await api.put(`/api/v1/scheduler/labels/${id}/default`);
    return response.data;
  },
  // AI Scheduling
  getAIScheduling: async () => {
    const response = await api.get('/api/v1/scheduler/settings/ai-scheduling');
    return response.data;
  },
  updateAIScheduling: async (data: any) => {
    const response = await api.put('/api/v1/scheduler/settings/ai_scheduling', data);
    return response.data;
  },
};

// Process Templates API
export const processTemplatesAPI = {
  getAll: async () => {
    const response = await api.get('/api/v1/process-templates/');
    return ensureArray(response.data, 'templates');
  },
  getByRole: async (roleName: string) => {
    const response = await api.get(`/api/v1/process-templates/?role_name=${encodeURIComponent(roleName)}`);
    return ensureArray(response.data, 'templates');
  },
  getRoles: async () => {
    const response = await api.get('/api/v1/process-templates/roles');
    return ensureArray(response.data, 'roles');
  },
  create: async (data: any) => {
    const response = await api.post('/api/v1/process-templates/', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.patch(`/api/v1/process-templates/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    await api.delete(`/api/v1/process-templates/${id}`);
  },
  analyzeEfficiency: async (roleName: string | null = null) => {
    const url = roleName
      ? `/api/v1/process-templates/analyze-efficiency?role_name=${encodeURIComponent(roleName)}`
      : '/api/v1/process-templates/analyze-efficiency';
    const response = await api.post(url);
    return response.data;
  },
  seedDefaults: async () => {
    const response = await api.post('/api/v1/process-templates/seed-defaults');
    return response.data;
  },
};
