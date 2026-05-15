/**
 * Calendar Settings - Default Data & Navigation Constants
 *
 * All default state objects and navigation configuration for CalendarSettings.
 * Extracted from CalendarSettings.js to keep the container lean.
 */

// ============================================================================
// Navigation constants
// ============================================================================

export const NAV_SECTIONS = [
  {
    group: 'Schedule',
    items: [
      { id: 'availability', label: 'Availability', icon: 'fa-clock', description: 'Business hours, time blocks, buffer time, and booking window' },
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
      { id: 'integrations', label: 'Integrations', icon: 'fa-plug', description: 'Meeting defaults, external calendars, and third-party tools' },
    ],
  },
  {
    group: 'AI & Automation',
    items: [
      { id: 'ai-automation', label: 'AI & Automation', icon: 'fa-robot', description: 'AI scheduling, follow-up cadence, and advanced calendar options' },
    ],
  },
  {
    group: 'Management',
    items: [
      { id: 'team', label: 'Team', icon: 'fa-users', description: 'Manage team assignment strategy and capacity', badge: 'Manager' },
    ],
  },
];

export const ALL_NAV_ITEMS = NAV_SECTIONS.flatMap(s => s.items);

// ============================================================================
// Section default data
// ============================================================================

export const DEFAULT_AVAILABILITY = {
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
  time_blocks: [],
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

export const DEFAULT_NOTIFICATIONS = {
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

export const DEFAULT_BOOKING_PAGE = {
  branding: {
    logo_url: null, primary_color: '#1F3D2E', secondary_color: '#e6f5f5',
    tagline: '', welcome_message: 'Schedule a time to meet with us', show_branding: true,
  },
  booking_links: [],
};

export const DEFAULT_CANCELLATION_POLICY = {
  policy: 'moderate', allow_reschedule: true, reschedule_limit: 2, require_reason: false,
};

export const DEFAULT_ADVANCED = {
  calendar_feed_enabled: false, auto_confirm_appointments: true,
  show_timezone_selector: true, enable_waitlist: false,
};

export const DEFAULT_AI_SCHEDULING = {
  enabled: true,
  auto_book_enabled: false,
  preferred_times: ['10:00', '14:00', '16:00'],
  max_ai_bookings_per_day: 5,
  buffer_before_minutes: 15,
  buffer_after_minutes: 10,
  allowed_appointment_types: ['discovery_call', 'pre_purchase_consultation', 'document_review'],
  require_confirmation: true,
  confirmation_method: 'sms',
  smart_scheduling: {
    avoid_back_to_back: true,
    cluster_similar_meetings: true,
    protect_focus_time: true,
    focus_time_blocks: ['08:00-09:30'],
  },
  sms_triggers: {
    send_booking_link: true,
    follow_up_no_response_hours: 24,
    max_follow_ups: 3,
    include_calendar_preview: true,
  },
  ai_response_handling: {
    auto_reschedule_on_cancel: true,
    suggest_alternatives: 3,
    respect_borrower_timezone: true,
  },
};

export const DEFAULT_INTEGRATIONS = {
  google: { connected: false }, outlook: { connected: false }, zoom: { connected: false },
  google_meet: { connected: false }, ical: { connected: false, feed_url: '', subscriber_count: 0 },
};

export const DEFAULT_MEETING_DEFAULTS = {
  default_meeting_mode: 'video',
  auto_create_meeting_link: true,
};

export const DEFAULT_INTEGRATION_SETTINGS = {
  google: { two_way_sync: true, conflict_resolution: 'crm_wins', sync_frequency: '15' },
  outlook: { two_way_sync: true, conflict_resolution: 'crm_wins', sync_frequency: '15' },
  zoom: { auto_generate_links: true, waiting_room: true, require_password: true, default_duration: 30 },
  google_meet: { auto_add: true, default_duration: 30 },
};

export const DEFAULT_WEBHOOK_SETTINGS = {
  api_key: '', webhook_url: '',
  events: {
    'appointment.created': true, 'appointment.updated': true,
    'appointment.cancelled': true, 'appointment.rescheduled': true,
    'appointment.reminder': false, 'appointment.no_show': false,
  },
};

export const DEFAULT_TEAM = {
  assignment_strategy: 'round_robin', apply_to_new_only: true,
  members: [], total_members: 0,
  overflow: { enabled: false, max_overflow_pct: 20, notify_user_ids: [], auto_expand_hours: false },
  permissions: { members_see_calendars: true, members_reschedule_others: false, only_managers_modify: true },
  weekly_coverage: null, utilization_pct: 0,
};

export const DEFAULT_EXPANDED_SECTIONS = {
  'weekly-schedule': true, 'week-overview': true, 'schedule-templates': false,
  'time-blocks': true, 'buffer-times': true, 'date-overrides': false,
  'holidays': false, 'seasonal-hours': false, 'override-days': false,
  'daily-limits': false,
};

// ============================================================================
// Sections that show the Save button
// ============================================================================

export const SAVEABLE_SECTIONS = [
  'availability', 'notifications', 'booking-page', 'team',
  'integrations', 'cancellation-policy', 'locations-labels',
  'ai-automation',
];
