/**
 * Perennia AI - Calendar Settings
 *
 * Comprehensive calendar settings page with seven tabs:
 *   1. Availability       - Business hours per day, lunch break, buffer time, booking window
 *   2. Appointment Types  - List with edit/delete/reorder, add new
 *   3. Notifications      - Email/SMS reminder toggles (24h/2h/15min), quiet hours
 *   4. Booking Page       - Preview, branding (logo/colors/tagline), booking link + copy, QR code
 *   5. Locations & Labels - Meeting locations, color-coded labels, appointment templates
 *   6. Integrations       - Google/Outlook connect/disconnect, sync status
 *   7. Team               - LO list, assignment strategy, capacity (managers only)
 *
 * Follows the SmartSchedulerSettings error-handling and layout patterns.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { calendarSettingsAPI, API_BASE_URL } from '../services/api';
import { toast } from '../utils/toast';
import AvailabilityPreferences from '../components/calendar/AvailabilityPreferences';
import BufferTimeSettings from '../components/calendar/BufferTimeSettings';
import CalendarFeedSettings from '../components/calendar/CalendarFeedSettings';
import ReminderSettings from '../components/calendar/ReminderSettings';
import DigestSettings from '../components/calendar/DigestSettings';
import LocationManager from '../components/calendar/LocationManager';
import LabelManager from '../components/calendar/LabelManager';
import '../styles/calendar-settings.css';

// ============================================================================
// Constants
// ============================================================================

const DAYS_OF_WEEK = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_LABELS = {
  monday: 'Monday', tuesday: 'Tuesday', wednesday: 'Wednesday',
  thursday: 'Thursday', friday: 'Friday', saturday: 'Saturday', sunday: 'Sunday',
};

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

// Flat list of all nav items for keyboard navigation and mobile tabs
const ALL_NAV_ITEMS = NAV_SECTIONS.flatMap(s => s.items);

const CANCELLATION_POLICIES = [
  { value: 'flexible', label: 'Flexible', description: 'Clients can cancel or reschedule up to 1 hour before' },
  { value: 'moderate', label: 'Moderate', description: 'Clients can cancel or reschedule up to 24 hours before' },
  { value: 'strict', label: 'Strict', description: 'Clients can cancel or reschedule up to 48 hours before' },
  { value: 'none', label: 'No Cancellation', description: 'Clients cannot cancel or reschedule online' },
];

const ASSIGNMENT_STRATEGIES = [
  {
    value: 'round_robin',
    label: 'Round Robin',
    tagline: 'Distribute evenly',
    description: 'Appointments rotate through team members in order, ensuring everyone gets an equal share regardless of schedule density.',
    icon: 'fa-sync-alt',
  },
  {
    value: 'load_balanced',
    label: 'Load Balanced',
    tagline: 'Assign to least busy',
    description: 'Each new appointment goes to the team member with the fewest upcoming bookings, keeping workloads even across the team.',
    icon: 'fa-balance-scale',
  },
  {
    value: 'ai_optimized',
    label: 'AI Optimized',
    tagline: 'AI picks best match',
    description: 'AI considers borrower needs, LO specialties, historical close rates, and workload to find the ideal match for each appointment.',
    icon: 'fa-brain',
    recommended: true,
  },
  {
    value: 'manual',
    label: 'Manual',
    tagline: 'Admin assigns all',
    description: 'No automatic assignment. A manager must manually assign every incoming appointment to a team member.',
    icon: 'fa-hand-pointer',
  },
];

const SPECIALTY_OPTIONS = ['FHA', 'VA', 'Jumbo', 'Conventional', 'USDA', 'Non-QM', 'Refinance', 'First-Time Buyer', 'Investment', 'Reverse'];
const TEAM_SORT_OPTIONS = [
  { value: 'name', label: 'Name' },
  { value: 'load', label: 'Current Load' },
  { value: 'capacity', label: 'Capacity' },
];

const DEFAULT_COLORS = ['#218D8D', '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#ef4444', '#6366f1'];

const DEFAULT_MORTGAGE_LABELS = [
  { name: 'Pre-Approval', color: '#4A90D9' },
  { name: 'Application', color: '#27AE60' },
  { name: 'Closing', color: '#8E44AD' },
  { name: 'Follow-Up', color: '#E67E22' },
  { name: 'Consultation', color: '#16A085' },
  { name: 'Document Review', color: '#F1C40F' },
];

const LABEL_PRESET_COLORS = [
  '#4A90D9', '#27AE60', '#8E44AD', '#E67E22', '#16A085',
  '#E74C3C', '#F1C40F', '#34495E', '#3498DB', '#1ABC9C',
];

// ============================================================================
// Helper: API request wrapper
// ============================================================================

function CalendarSettings() {
  const navigate = useNavigate();
  const contentRef = useRef(null);

  // ========== Shared state ==========
  const [activeSection, setActiveSection] = useState('availability');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [saveStatus, setSaveStatus] = useState('saved'); // 'saved' | 'saving' | 'unsaved'

  // ========== Cancellation Policy state ==========
  const [cancellationPolicy, setCancellationPolicy] = useState({
    policy: 'moderate',
    allow_reschedule: true,
    reschedule_limit: 2,
    require_reason: false,
  });

  // ========== Advanced state ==========
  const [advancedSettings, setAdvancedSettings] = useState({
    calendar_feed_enabled: false,
    auto_confirm_appointments: true,
    show_timezone_selector: true,
    enable_waitlist: false,
  });

  // ========== Availability state ==========
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
    // Holiday management
    block_us_holidays: false,
    blocked_holidays: {},
    custom_blocked_dates: [],
    // Daily limits
    max_meetings_per_day: 0,
    max_consecutive_meetings: 0,
    min_break_between_meetings: 0,
  });

  // ========== Collapsible section state ==========
  const [expandedSections, setExpandedSections] = useState({
    'weekly-schedule': true,
    'buffer-times': true,
    'date-overrides': false,
    'holidays': false,
    'daily-limits': false,
  });

  // ========== Appointment Types state ==========
  const [appointmentTypes, setAppointmentTypes] = useState([]);
  const [editingType, setEditingType] = useState(null);
  const [showNewTypeForm, setShowNewTypeForm] = useState(false);
  const [newType, setNewType] = useState({
    type_name: '', description: '', duration_minutes: 30, color: '#218D8D', icon: 'fa-calendar', is_public: true,
  });

  // ========== Notification state ==========
  const [notifications, setNotifications] = useState({
    email_reminder_24h: true,
    email_reminder_2h: true,
    email_reminder_15m: false,
    sms_reminder_24h: false,
    sms_reminder_2h: true,
    sms_reminder_15m: false,
    quiet_hours_enabled: false,
    quiet_hours_start: '21:00',
    quiet_hours_end: '08:00',
    notify_on_booking: true,
    notify_on_cancellation: true,
    notify_on_reschedule: true,
    // Event alert preferences (channel per event type)
    alert_new_booking: 'both',
    alert_cancellation: 'email',
    alert_reschedule: 'email',
    alert_no_show: 'push',
    alert_waitlist_opened: 'none',
    alert_survey_response: 'email',
    // Daily digest
    digest: {
      enabled: false,
      frequency: 'daily',
      send_time: '07:00',
      include_cancelled: false,
      include_no_shows: true,
      day_of_week: 'monday',
    },
    // Quiet hours (extended)
    quiet_hours_enabled: false,
    quiet_hours_start: '21:00',
    quiet_hours_end: '08:00',
    quiet_hours_include_weekends: false,
    // Browser notifications
    browser_notifications_enabled: false,
  });
  const [notifSections, setNotifSections] = useState({
    reminders: true,
    alerts: true,
    digest: false,
    quiet: false,
    browser: false,
  });
  const [browserPermission, setBrowserPermission] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'default'
  );

  // ========== Booking Page state ==========
  const [bookingPage, setBookingPage] = useState({
    branding: {
      logo_url: null, primary_color: '#218D8D', secondary_color: '#e6f5f5',
      tagline: '', welcome_message: 'Schedule a time to meet with us', show_branding: true,
    },
    booking_links: [],
  });
  const [copiedLink, setCopiedLink] = useState(null);

  // ========== Integration state ==========
  const [integrations, setIntegrations] = useState({ google: { connected: false }, outlook: { connected: false } });

  // ========== Team state ==========
  const [team, setTeam] = useState({
    assignment_strategy: 'round_robin',
    apply_to_new_only: true,
    members: [],
    total_members: 0,
    overflow: {
      enabled: false,
      max_overflow_pct: 20,
      notify_user_ids: [],
      auto_expand_hours: false,
    },
    permissions: {
      members_see_calendars: true,
      members_reschedule_others: false,
      only_managers_modify: true,
    },
    weekly_coverage: null,
    utilization_pct: 0,
  });
  const [isManager, setIsManager] = useState(false);
  const [teamSearch, setTeamSearch] = useState('');
  const [teamSort, setTeamSort] = useState('name');
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);
  const [showSpecialtyPicker, setShowSpecialtyPicker] = useState(null);

  // ========== Locations & Labels state ==========
  const [labels, setLabels] = useState([]);
  const [labelsLoading, setLabelsLoading] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [autoAssignLabels, setAutoAssignLabels] = useState(false);
  const [labelMappings, setLabelMappings] = useState({});
  const [locLabelsExpanded, setLocLabelsExpanded] = useState({
    locations: true,
    labels: true,
    templates: false,
  });

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
              ...prev,
              ...res.data,
              blocked_holidays: res.data.blocked_holidays || prev.blocked_holidays,
              custom_blocked_dates: res.data.custom_blocked_dates || prev.custom_blocked_dates,
            }));
          }
          break;
        }
        case 'appointment-types': {
          const res = await calendarSettingsAPI.getAppointmentTypes();
          if (res?.data?.appointment_types) {
            setAppointmentTypes(res.data.appointment_types);
          }
          break;
        }
        case 'notifications': {
          const res = await calendarSettingsAPI.getNotifications();
          if (res?.data) {
            setNotifications(prev => ({ ...prev, ...res.data }));
          }
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
            setIntegrations(res.data);
          }
          break;
        }
        case 'team': {
          try {
            const res = await calendarSettingsAPI.getTeam();
            if (res?.data) {
              setTeam(prev => ({
                ...prev,
                ...res.data,
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
          // Load labels
          setLabelsLoading(true);
          try {
            const labelsRes = await calendarSettingsAPI.getLabels();
            if (labelsRes?.data?.labels) {
              setLabels(labelsRes.data.labels);
            }
            if (labelsRes?.data?.auto_assign_enabled !== undefined) {
              setAutoAssignLabels(labelsRes.data.auto_assign_enabled);
            }
            if (labelsRes?.data?.label_mappings) {
              setLabelMappings(labelsRes.data.label_mappings);
            }
          } catch (err) {
            console.error('Failed to load labels:', err);
          } finally {
            setLabelsLoading(false);
          }
          // Load templates
          setTemplatesLoading(true);
          try {
            const templatesRes = await calendarSettingsAPI.getTemplates();
            if (templatesRes?.data?.templates) {
              setTemplates(templatesRes.data.templates);
            }
          } catch (err) {
            console.error('Failed to load templates:', err);
          } finally {
            setTemplatesLoading(false);
          }
          break;
        }
        case 'cancellation-policy':
        case 'advanced':
          // These sections use local state only for now
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
  // Save handlers
  // ============================================================================

  const markChanged = useCallback(() => {
    setHasChanges(true);
    setSaveStatus('unsaved');
  }, []);

  const handleSaveAvailability = async () => {
    setSaving(true);
    setSaveStatus('saving');
    try {
      await calendarSettingsAPI.updateAvailability(availability);
      toast.success('Availability settings saved');
      setHasChanges(false);
      setSaveStatus('saved');
    } catch (err) {
      toast.error('Failed to save availability settings');
      setSaveStatus('unsaved');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveNotifications = async () => {
    setSaving(true);
    setSaveStatus('saving');
    try {
      await calendarSettingsAPI.updateNotifications(notifications);
      toast.success('Notification preferences saved');
      setHasChanges(false);
      setSaveStatus('saved');
    } catch (err) {
      toast.error('Failed to save notification preferences');
      setSaveStatus('unsaved');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveBookingPage = async () => {
    setSaving(true);
    setSaveStatus('saving');
    try {
      await calendarSettingsAPI.updateBookingPage(bookingPage.branding);
      toast.success('Booking page settings saved');
      setHasChanges(false);
      setSaveStatus('saved');
    } catch (err) {
      toast.error('Failed to save booking page settings');
      setSaveStatus('unsaved');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTeam = async () => {
    setSaving(true);
    setSaveStatus('saving');
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
      setHasChanges(false);
      setSaveStatus('saved');
    } catch (err) {
      toast.error('Failed to save team settings');
      setSaveStatus('unsaved');
    } finally {
      setSaving(false);
    }
  };

  const handleInviteTeamMember = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      await calendarSettingsAPI.inviteTeamMember({ email: inviteEmail.trim() });
      toast.success(`Invitation sent to ${inviteEmail}`);
      setInviteEmail('');
      setShowInviteForm(false);
      loadTabData('team');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send invitation');
    } finally {
      setInviting(false);
    }
  };

  const handleSave = async () => {
    switch (activeSection) {
      case 'availability': return handleSaveAvailability();
      case 'notifications': return handleSaveNotifications();
      case 'booking-page': return handleSaveBookingPage();
      case 'team': return handleSaveTeam();
      case 'cancellation-policy':
      case 'locations-labels':
      case 'advanced':
        // Placeholder save for sections without API endpoints yet
        setSaving(true);
        setSaveStatus('saving');
        setTimeout(() => {
          setSaving(false);
          setHasChanges(false);
          setSaveStatus('saved');
          toast.success('Settings saved');
        }, 500);
        return;
      default: return;
    }
  };

  // ============================================================================
  // Availability helpers
  // ============================================================================

  const updateBusinessHours = useCallback((day, field, value) => {
    setAvailability(prev => ({
      ...prev,
      business_hours: {
        ...prev.business_hours,
        [day]: { ...prev.business_hours[day], [field]: value },
      },
    }));
    markChanged();
  }, []);

  const updateLunchBreak = useCallback((field, value) => {
    setAvailability(prev => ({
      ...prev,
      lunch_break: { ...prev.lunch_break, [field]: value },
    }));
    markChanged();
  }, []);

  // ============================================================================
  // Appointment Type helpers
  // ============================================================================

  const handleCreateType = async () => {
    try {
      await calendarSettingsAPI.createAppointmentType(newType);
      toast.success('Appointment type created');
      setShowNewTypeForm(false);
      setNewType({ type_name: '', description: '', duration_minutes: 30, color: '#218D8D', icon: 'fa-calendar', is_public: true });
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to create appointment type');
    }
  };

  const handleUpdateType = async (id, data) => {
    try {
      await calendarSettingsAPI.updateAppointmentType(id, data);
      toast.success('Appointment type updated');
      setEditingType(null);
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to update appointment type');
    }
  };

  const handleDeleteType = async (id) => {
    if (!window.confirm('Remove this appointment type?')) return;
    try {
      await calendarSettingsAPI.deleteAppointmentType(id);
      toast.success('Appointment type removed');
      loadTabData('appointment-types');
    } catch (err) {
      toast.error('Failed to remove appointment type');
    }
  };

  const handleMoveType = async (index, direction) => {
    const newTypes = [...appointmentTypes];
    const swapIdx = index + direction;
    if (swapIdx < 0 || swapIdx >= newTypes.length) return;
    [newTypes[index], newTypes[swapIdx]] = [newTypes[swapIdx], newTypes[index]];
    setAppointmentTypes(newTypes);
    try {
      await calendarSettingsAPI.reorderAppointmentTypes(newTypes.map(t => t.id));
    } catch (err) {
      toast.error('Failed to reorder');
      loadTabData('appointment-types');
    }
  };

  // ============================================================================
  // Booking page helpers
  // ============================================================================

  const handleCopyLink = (url) => {
    const fullUrl = `${window.location.origin}${url}`;
    navigator.clipboard.writeText(fullUrl).then(() => {
      setCopiedLink(url);
      toast.success('Link copied to clipboard');
      setTimeout(() => setCopiedLink(null), 2000);
    }).catch(() => {
      toast.error('Failed to copy link');
    });
  };

  // ============================================================================
  // Locations & Labels helpers
  // ============================================================================

  const toggleLocLabelsSection = useCallback((section) => {
    setLocLabelsExpanded(prev => ({ ...prev, [section]: !prev[section] }));
  }, []);

  const handleCreateLabel = useCallback(async (labelData) => {
    try {
      await calendarSettingsAPI.createLabel(labelData);
      toast.success('Label created');
      loadTabData('locations-labels');
    } catch (err) {
      toast.error('Failed to create label');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleUpdateLabel = useCallback(async (labelId, labelData) => {
    try {
      await calendarSettingsAPI.updateLabel(labelId, labelData);
      toast.success('Label updated');
      loadTabData('locations-labels');
    } catch (err) {
      toast.error('Failed to update label');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDeleteLabel = useCallback(async (labelId) => {
    try {
      await calendarSettingsAPI.deleteLabel(labelId);
      toast.success('Label deleted');
      loadTabData('locations-labels');
    } catch (err) {
      toast.error('Failed to delete label');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleReorderLabels = useCallback(async (orderedIds) => {
    try {
      await calendarSettingsAPI.reorderLabels(orderedIds);
      // Optimistically reorder in state
      const reordered = orderedIds.map(id => labels.find(l => l.id === id)).filter(Boolean);
      setLabels(reordered);
    } catch (err) {
      toast.error('Failed to reorder labels');
      loadTabData('locations-labels');
    }
  }, [labels]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleToggleAutoAssign = useCallback(async (enabled) => {
    setAutoAssignLabels(enabled);
    try {
      await calendarSettingsAPI.updateLabelSettings({ auto_assign_enabled: enabled, label_mappings: labelMappings });
    } catch (err) {
      toast.error('Failed to update auto-assign setting');
      setAutoAssignLabels(!enabled);
    }
  }, [labelMappings]);

  const handleUpdateLabelMapping = useCallback(async (appointmentTypeId, labelId) => {
    const newMappings = { ...labelMappings, [appointmentTypeId]: labelId };
    setLabelMappings(newMappings);
    try {
      await calendarSettingsAPI.updateLabelSettings({ auto_assign_enabled: autoAssignLabels, label_mappings: newMappings });
    } catch (err) {
      toast.error('Failed to save label mapping');
    }
  }, [labelMappings, autoAssignLabels]);

  const handleDeleteTemplate = useCallback(async (templateId) => {
    if (!window.confirm('Delete this appointment template?')) return;
    try {
      await calendarSettingsAPI.deleteTemplate(templateId);
      toast.success('Template deleted');
      setTemplates(prev => prev.filter(t => t.id !== templateId));
    } catch (err) {
      toast.error('Failed to delete template');
    }
  }, []);

  const handleToggleDefaultTemplate = useCallback(async (templateId) => {
    try {
      await calendarSettingsAPI.setDefaultTemplate(templateId);
      setTemplates(prev => prev.map(t => ({
        ...t,
        is_default: t.id === templateId,
      })));
      toast.success('Default template updated');
    } catch (err) {
      toast.error('Failed to set default template');
    }
  }, []);

  // ============================================================================
  // Section metadata helpers
  // ============================================================================

  const activeNavItem = ALL_NAV_ITEMS.find(item => item.id === activeSection);
  const activeGroupName = NAV_SECTIONS.find(s => s.items.some(i => i.id === activeSection))?.group || '';

  const showSaveButton = ['availability', 'notifications', 'booking-page', 'team', 'cancellation-policy', 'locations-labels', 'advanced'].includes(activeSection);

  // ============================================================================
  // Render: Loading
  // ============================================================================

  const renderLoading = () => (
    <div className="cal-settings-loading" role="status">
      <div className="spinner"></div>
      <p>Loading settings...</p>
    </div>
  );

  // ============================================================================
  // Render: Tab 1 - Availability
  // ============================================================================

  const renderAvailability = () => (
    <div role="tabpanel" id="panel-availability" aria-labelledby="calnav-availability">
      {/* Recurring weekly schedule + date overrides (self-contained save) */}
      <AvailabilityPreferences />

      {/* Booking Window settings (saved via parent CalendarSettings save) */}
      <section className="cal-settings-section">
        <h2>Booking Window</h2>
        <p className="section-description">Control how clients can book appointments on your calendar.</p>
        <div className="form-grid">
          <div className="form-field">
            <label htmlFor="buffer">Buffer Between Meetings (min)</label>
            <input
              id="buffer"
              type="number"
              min="0"
              max="60"
              value={availability.buffer_minutes}
              onChange={(e) => { setAvailability(prev => ({ ...prev, buffer_minutes: parseInt(e.target.value) || 0 })); markChanged(); }}
            />
            <span className="field-hint">Break time between consecutive meetings</span>
          </div>
          <div className="form-field">
            <label htmlFor="min-notice">Minimum Notice (hours)</label>
            <input
              id="min-notice"
              type="number"
              min="0"
              max="168"
              value={availability.min_booking_notice_hours}
              onChange={(e) => { setAvailability(prev => ({ ...prev, min_booking_notice_hours: parseInt(e.target.value) || 0 })); markChanged(); }}
            />
            <span className="field-hint">How far in advance bookings must be made</span>
          </div>
          <div className="form-field">
            <label htmlFor="max-advance">Max Advance Booking (days)</label>
            <input
              id="max-advance"
              type="number"
              min="1"
              max="365"
              value={availability.max_advance_booking_days}
              onChange={(e) => { setAvailability(prev => ({ ...prev, max_advance_booking_days: parseInt(e.target.value) || 1 })); markChanged(); }}
            />
            <span className="field-hint">How far into the future clients can book</span>
          </div>
        </div>
      </section>
    </div>
  );

  // ============================================================================
  // Render: Tab 2 - Appointment Types
  // ============================================================================

  const renderAppointmentTypes = () => (
    <section className="cal-settings-section" role="tabpanel" id="panel-appointment-types" aria-labelledby="calnav-appointment-types">
      <div className="section-header-row">
        <div>
          <h2>Appointment Types</h2>
          <p className="section-description">Define the types of meetings clients can book.</p>
        </div>
        <button
          className="btn-primary btn-sm"
          onClick={() => setShowNewTypeForm(true)}
        >
          <i className="fas fa-plus"></i> Add Type
        </button>
      </div>

      {showNewTypeForm && (
        <div className="type-form-card">
          <h3>New Appointment Type</h3>
          <div className="form-grid">
            <div className="form-field">
              <label>Name</label>
              <input
                type="text"
                value={newType.type_name}
                onChange={(e) => setNewType(prev => ({ ...prev, type_name: e.target.value }))}
                placeholder="e.g., Initial Consultation"
              />
            </div>
            <div className="form-field">
              <label>Duration (min)</label>
              <select
                value={newType.duration_minutes}
                onChange={(e) => setNewType(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
              >
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={45}>45 minutes</option>
                <option value={60}>60 minutes</option>
                <option value={90}>90 minutes</option>
              </select>
            </div>
            <div className="form-field full-width">
              <label>Description</label>
              <textarea
                value={newType.description || ''}
                onChange={(e) => setNewType(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Brief description shown to clients"
                rows={2}
              />
            </div>
            <div className="form-field">
              <label>Color</label>
              <div className="color-picker">
                {DEFAULT_COLORS.map(c => (
                  <button
                    key={c}
                    type="button"
                    className={`color-swatch ${newType.color === c ? 'selected' : ''}`}
                    style={{ backgroundColor: c }}
                    onClick={() => setNewType(prev => ({ ...prev, color: c }))}
                    aria-label={`Color ${c}`}
                  />
                ))}
              </div>
            </div>
            <div className="form-field">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={newType.is_public}
                  onChange={(e) => setNewType(prev => ({ ...prev, is_public: e.target.checked }))}
                />
                Available on public booking page
              </label>
            </div>
          </div>
          <div className="form-actions">
            <button className="btn-secondary btn-sm" onClick={() => setShowNewTypeForm(false)}>Cancel</button>
            <button
              className="btn-primary btn-sm"
              disabled={!newType.type_name.trim()}
              onClick={handleCreateType}
            >
              Create
            </button>
          </div>
        </div>
      )}

      <div className="type-list">
        {appointmentTypes.length === 0 && !loading && (
          <div className="empty-state">
            <i className="fas fa-calendar-plus"></i>
            <p>No appointment types yet. Create one to get started.</p>
          </div>
        )}
        {appointmentTypes.map((type, idx) => (
          <div key={type.id} className="type-card">
            <div className="type-color-bar" style={{ backgroundColor: type.color || '#218D8D' }} />
            <div className="type-content">
              {editingType === type.id ? (
                <EditTypeForm
                  type={type}
                  onSave={(data) => handleUpdateType(type.id, data)}
                  onCancel={() => setEditingType(null)}
                />
              ) : (
                <>
                  <div className="type-info">
                    <h4>{type.type_name}</h4>
                    <span className="type-meta">
                      {type.duration_minutes} min
                      {type.is_public && <span className="badge badge-public">Public</span>}
                    </span>
                    {type.description && <p className="type-desc">{type.description}</p>}
                  </div>
                  <div className="type-actions">
                    <button
                      className="icon-btn"
                      onClick={() => handleMoveType(idx, -1)}
                      disabled={idx === 0}
                      aria-label="Move up"
                      title="Move up"
                    >
                      <i className="fas fa-chevron-up"></i>
                    </button>
                    <button
                      className="icon-btn"
                      onClick={() => handleMoveType(idx, 1)}
                      disabled={idx === appointmentTypes.length - 1}
                      aria-label="Move down"
                      title="Move down"
                    >
                      <i className="fas fa-chevron-down"></i>
                    </button>
                    <button className="icon-btn" onClick={() => setEditingType(type.id)} aria-label="Edit" title="Edit">
                      <i className="fas fa-pen"></i>
                    </button>
                    <button className="icon-btn danger" onClick={() => handleDeleteType(type.id)} aria-label="Delete" title="Delete">
                      <i className="fas fa-trash"></i>
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );

  // ============================================================================
  // Render: Tab 3 - Notifications
  // ============================================================================

  const EVENT_ALERT_TYPES = [
    { key: 'alert_new_booking', label: 'New booking received', icon: 'fa-calendar-plus' },
    { key: 'alert_cancellation', label: 'Appointment cancelled', icon: 'fa-calendar-times' },
    { key: 'alert_reschedule', label: 'Appointment rescheduled', icon: 'fa-calendar-alt' },
    { key: 'alert_no_show', label: 'No-show detected', icon: 'fa-user-slash' },
    { key: 'alert_waitlist_opened', label: 'Waitlist slot opened', icon: 'fa-list-ol' },
    { key: 'alert_survey_response', label: 'Survey response received', icon: 'fa-poll' },
  ];

  const ALERT_CHANNEL_OPTIONS = [
    { value: 'email', label: 'Email' },
    { value: 'push', label: 'Push' },
    { value: 'both', label: 'Both' },
    { value: 'none', label: 'None' },
  ];

  const toggleNotifSection = (sectionId) => {
    setNotifSections(prev => ({ ...prev, [sectionId]: !prev[sectionId] }));
  };

  const handleRequestBrowserPermission = async () => {
    if (typeof Notification === 'undefined') {
      toast.error('Browser notifications are not supported in this browser');
      return;
    }
    try {
      const result = await Notification.requestPermission();
      setBrowserPermission(result);
      if (result === 'granted') {
        updateNotif('browser_notifications_enabled', true);
        toast.success('Browser notifications enabled');
      } else if (result === 'denied') {
        toast.error('Browser notification permission was denied. You can change this in your browser settings.');
      }
    } catch (err) {
      toast.error('Failed to request notification permission');
    }
  };

  const handleTestNotification = () => {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') {
      toast.error('Browser notifications are not enabled');
      return;
    }
    new Notification('Perennia AI - Test Notification', {
      body: 'Your browser notifications are working correctly.',
      icon: '/favicon.ico',
    });
    toast.success('Test notification sent');
  };

  const computeQuietArc = () => {
    const parseTime = (t) => {
      const [h, m] = (t || '00:00').split(':').map(Number);
      return h + m / 60;
    };
    const startH = parseTime(notifications.quiet_hours_start);
    const endH = parseTime(notifications.quiet_hours_end);
    const startAngle = (startH / 24) * 360 - 90;
    const endAngle = (endH / 24) * 360 - 90;
    return { startAngle, endAngle };
  };

  const describeArc = (cx, cy, r, startAngle, endAngle) => {
    const toRad = (deg) => (deg * Math.PI) / 180;
    const start = { x: cx + r * Math.cos(toRad(startAngle)), y: cy + r * Math.sin(toRad(startAngle)) };
    const end = { x: cx + r * Math.cos(toRad(endAngle)), y: cy + r * Math.sin(toRad(endAngle)) };
    let sweep = endAngle - startAngle;
    if (sweep < 0) sweep += 360;
    const largeArc = sweep > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
  };

  const activeReminders = [
    notifications.email_reminder_24h && { label: '24h', channel: 'Email', minutes: 1440 },
    notifications.email_reminder_2h && { label: '2h', channel: 'Email', minutes: 120 },
    notifications.email_reminder_15m && { label: '15m', channel: 'Email', minutes: 15 },
    notifications.sms_reminder_24h && { label: '24h', channel: 'SMS', minutes: 1440 },
    notifications.sms_reminder_2h && { label: '2h', channel: 'SMS', minutes: 120 },
    notifications.sms_reminder_15m && { label: '15m', channel: 'SMS', minutes: 15 },
  ].filter(Boolean).sort((a, b) => b.minutes - a.minutes);

  const updateNotif = (key, value) => {
    setNotifications(prev => ({ ...prev, [key]: value }));
    markChanged();
  };

  const renderNotifications = () => {
    return (
      <section className="cal-settings-section notif-enhanced-section" role="tabpanel" id="panel-notifications" aria-labelledby="calnav-notifications">
        <h2><i className="fas fa-bell" aria-hidden="true"></i> Notification Preferences</h2>
        <p className="section-description">Control how and when you receive notifications about your calendar events.</p>

        {/* ---- Section 1: Appointment Reminders ---- */}
        <div className="notif-collapsible-section">
          <button
            type="button"
            className="notif-section-header"
            onClick={() => toggleNotifSection('reminders')}
            aria-expanded={notifSections.reminders}
          >
            <div className="notif-section-header-left">
              <i className="fas fa-clock" aria-hidden="true"></i>
              <div>
                <span className="notif-section-title">Appointment Reminders</span>
                <span className="notif-section-desc">Configure automated reminders sent before each appointment</span>
              </div>
            </div>
            <i className={`fas fa-chevron-${notifSections.reminders ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
          </button>

          {notifSections.reminders && (
            <div className="notif-section-body">
              {/* Visual reminder timeline */}
              {activeReminders.length > 0 && (
                <div className="reminder-timeline">
                  <div className="reminder-timeline-label">Reminder Timeline</div>
                  <div className="reminder-timeline-track">
                    <div className="reminder-timeline-line"></div>
                    {activeReminders.map((r) => {
                      const maxMin = 1440;
                      const pct = Math.max(5, Math.min(95, ((maxMin - r.minutes) / maxMin) * 100));
                      return (
                        <div
                          key={`${r.channel}-${r.label}`}
                          className="reminder-timeline-marker"
                          style={{ left: `${pct}%` }}
                          title={`${r.channel} - ${r.label} before`}
                        >
                          <div className={`reminder-marker-dot ${r.channel === 'Email' ? 'marker-email' : 'marker-sms'}`}></div>
                          <div className="reminder-marker-label">{r.channel} {r.label}</div>
                        </div>
                      );
                    })}
                    <div className="reminder-timeline-marker" style={{ left: '100%' }}>
                      <div className="reminder-marker-dot marker-event"></div>
                      <div className="reminder-marker-label">Appointment</div>
                    </div>
                    <div className="reminder-timeline-start-label">24h before</div>
                    <div className="reminder-timeline-end-label">Start time</div>
                  </div>
                </div>
              )}

              <ReminderSettings />
            </div>
          )}
        </div>

        {/* ---- Section 2: Event Alerts ---- */}
        <div className="notif-collapsible-section">
          <button
            type="button"
            className="notif-section-header"
            onClick={() => toggleNotifSection('alerts')}
            aria-expanded={notifSections.alerts}
          >
            <div className="notif-section-header-left">
              <i className="fas fa-exclamation-circle" aria-hidden="true"></i>
              <div>
                <span className="notif-section-title">Event Alerts</span>
                <span className="notif-section-desc">Choose how you are notified for each type of calendar event</span>
              </div>
            </div>
            <i className={`fas fa-chevron-${notifSections.alerts ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
          </button>

          {notifSections.alerts && (
            <div className="notif-section-body">
              <div className="event-alerts-grid">
                <div className="event-alerts-header">
                  <span className="event-alerts-header-event">Event</span>
                  <span className="event-alerts-header-channel">Notification Channel</span>
                </div>
                {EVENT_ALERT_TYPES.map(evt => (
                  <div key={evt.key} className="event-alert-row">
                    <div className="event-alert-label">
                      <i className={`fas ${evt.icon}`} aria-hidden="true"></i>
                      <span>{evt.label}</span>
                    </div>
                    <div className="event-alert-channels">
                      {ALERT_CHANNEL_OPTIONS.map(ch => (
                        <label key={ch.value} className={`event-alert-chip ${notifications[evt.key] === ch.value ? 'active' : ''}`}>
                          <input
                            type="radio"
                            name={evt.key}
                            value={ch.value}
                            checked={notifications[evt.key] === ch.value}
                            onChange={() => updateNotif(evt.key, ch.value)}
                          />
                          <span>{ch.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ---- Section 3: Daily Digest ---- */}
        <div className="notif-collapsible-section">
          <button
            type="button"
            className="notif-section-header"
            onClick={() => toggleNotifSection('digest')}
            aria-expanded={notifSections.digest}
          >
            <div className="notif-section-header-left">
              <i className="fas fa-newspaper" aria-hidden="true"></i>
              <div>
                <span className="notif-section-title">Daily Digest</span>
                <span className="notif-section-desc">Receive a daily summary email of your upcoming schedule</span>
              </div>
            </div>
            <i className={`fas fa-chevron-${notifSections.digest ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
          </button>

          {notifSections.digest && (
            <div className="notif-section-body">
              <DigestSettings
                digest={notifications.digest}
                onChange={(updatedDigest) => {
                  setNotifications(prev => ({ ...prev, digest: updatedDigest }));
                  markChanged();
                }}
              />
            </div>
          )}
        </div>

        {/* ---- Section 4: Quiet Hours ---- */}
        <div className="notif-collapsible-section">
          <button
            type="button"
            className="notif-section-header"
            onClick={() => toggleNotifSection('quiet')}
            aria-expanded={notifSections.quiet}
          >
            <div className="notif-section-header-left">
              <i className="fas fa-moon" aria-hidden="true"></i>
              <div>
                <span className="notif-section-title">Quiet Hours</span>
                <span className="notif-section-desc">Suppress all notifications during specified hours</span>
              </div>
            </div>
            <i className={`fas fa-chevron-${notifSections.quiet ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
          </button>

          {notifSections.quiet && (
            <div className="notif-section-body">
              <div className="quiet-hours-content">
                <div className="quiet-hours-controls">
                  <label className="quiet-hours-toggle-row">
                    <label className="toggle-switch">
                      <input
                        type="checkbox"
                        checked={notifications.quiet_hours_enabled}
                        onChange={(e) => updateNotif('quiet_hours_enabled', e.target.checked)}
                        aria-label="Enable quiet hours"
                      />
                      <span className="toggle-slider"></span>
                    </label>
                    <span>Enable quiet hours</span>
                  </label>

                  {notifications.quiet_hours_enabled && (
                    <>
                      <div className="quiet-hours-times">
                        <div className="quiet-hours-time-field">
                          <label>Start time</label>
                          <input
                            type="time"
                            value={notifications.quiet_hours_start}
                            onChange={(e) => updateNotif('quiet_hours_start', e.target.value)}
                            aria-label="Quiet hours start"
                          />
                        </div>
                        <span className="time-separator">to</span>
                        <div className="quiet-hours-time-field">
                          <label>End time</label>
                          <input
                            type="time"
                            value={notifications.quiet_hours_end}
                            onChange={(e) => updateNotif('quiet_hours_end', e.target.value)}
                            aria-label="Quiet hours end"
                          />
                        </div>
                      </div>

                      <label className="quiet-hours-toggle-row">
                        <label className="toggle-switch">
                          <input
                            type="checkbox"
                            checked={notifications.quiet_hours_include_weekends}
                            onChange={(e) => updateNotif('quiet_hours_include_weekends', e.target.checked)}
                            aria-label="Include weekends in quiet hours"
                          />
                          <span className="toggle-slider"></span>
                        </label>
                        <span>Include weekends</span>
                      </label>
                    </>
                  )}
                </div>

                {notifications.quiet_hours_enabled && (() => {
                  const arc = computeQuietArc();
                  return (
                    <div className="quiet-hours-clock">
                      <svg viewBox="0 0 120 120" width="140" height="140" aria-label={`Quiet hours from ${notifications.quiet_hours_start} to ${notifications.quiet_hours_end}`}>
                        <circle cx="60" cy="60" r="52" fill="#f8fafc" stroke="#e2e8f0" strokeWidth="2" />
                        <path
                          d={describeArc(60, 60, 44, arc.startAngle, arc.endAngle)}
                          fill="none"
                          stroke="#818cf8"
                          strokeWidth="10"
                          strokeLinecap="round"
                          opacity="0.3"
                        />
                        {[0, 3, 6, 9, 12, 15, 18, 21].map(h => {
                          const angle = ((h / 24) * 360 - 90) * (Math.PI / 180);
                          const x1 = 60 + 48 * Math.cos(angle);
                          const y1 = 60 + 48 * Math.sin(angle);
                          const x2 = 60 + 52 * Math.cos(angle);
                          const y2 = 60 + 52 * Math.sin(angle);
                          const tx = 60 + 40 * Math.cos(angle);
                          const ty = 60 + 40 * Math.sin(angle);
                          return (
                            <g key={h}>
                              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#94a3b8" strokeWidth="1.5" />
                              <text x={tx} y={ty} textAnchor="middle" dominantBaseline="central" fontSize="8" fill="#64748b">
                                {h === 0 ? '12a' : h === 12 ? '12p' : h < 12 ? `${h}a` : `${h - 12}p`}
                              </text>
                            </g>
                          );
                        })}
                        <text x="60" y="62" textAnchor="middle" dominantBaseline="central" fontSize="16" aria-hidden="true">
                          {'\uD83C\uDF19'}
                        </text>
                      </svg>
                      <div className="quiet-clock-label">
                        {notifications.quiet_hours_start} - {notifications.quiet_hours_end}
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>
          )}
        </div>

        {/* ---- Section 5: Browser Notifications ---- */}
        <div className="notif-collapsible-section">
          <button
            type="button"
            className="notif-section-header"
            onClick={() => toggleNotifSection('browser')}
            aria-expanded={notifSections.browser}
          >
            <div className="notif-section-header-left">
              <i className="fas fa-desktop" aria-hidden="true"></i>
              <div>
                <span className="notif-section-title">Browser Notifications</span>
                <span className="notif-section-desc">Get real-time desktop notifications in your browser</span>
              </div>
            </div>
            <i className={`fas fa-chevron-${notifSections.browser ? 'up' : 'down'} notif-chevron`} aria-hidden="true"></i>
          </button>

          {notifSections.browser && (
            <div className="notif-section-body">
              <div className="browser-notif-content">
                <div className="browser-notif-status">
                  <span className="browser-notif-status-label">Permission status:</span>
                  <span className={`browser-notif-status-badge status-${browserPermission}`}>
                    {browserPermission === 'granted' ? 'Granted' : browserPermission === 'denied' ? 'Denied' : 'Not Asked'}
                  </span>
                </div>

                <div className="browser-notif-actions">
                  {browserPermission !== 'granted' && (
                    <button
                      type="button"
                      className="btn-primary btn-sm"
                      onClick={handleRequestBrowserPermission}
                      disabled={browserPermission === 'denied'}
                    >
                      <i className="fas fa-bell" aria-hidden="true"></i>
                      {browserPermission === 'denied' ? 'Permission Denied' : 'Enable Browser Notifications'}
                    </button>
                  )}
                  {browserPermission === 'granted' && (
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={handleTestNotification}
                    >
                      <i className="fas fa-paper-plane" aria-hidden="true"></i>
                      Send Test Notification
                    </button>
                  )}
                </div>

                <div className="browser-notif-note">
                  <i className="fas fa-info-circle" aria-hidden="true"></i>
                  <span>
                    Browser notifications require your browser to be open. They work in Chrome, Firefox, Edge, and Safari.
                    {browserPermission === 'denied' && ' You previously denied permission. To re-enable, update your notification settings in your browser\'s site permissions.'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    );
  };

  // ============================================================================
  // Render: Tab 4 - Booking Page
  // ============================================================================

  const renderBookingPage = () => {
    const updateBranding = (key, value) => {
      setBookingPage(prev => ({
        ...prev,
        branding: { ...prev.branding, [key]: value },
      }));
      markChanged();
    };

    return (
      <section className="cal-settings-section" role="tabpanel" id="panel-booking-page" aria-labelledby="calnav-booking-page">
        <h2>Booking Page</h2>
        <p className="section-description">Customize the appearance of your public booking page.</p>

        {/* Branding */}
        <div className="form-grid">
          <div className="form-field">
            <label>Logo URL</label>
            <input
              type="url"
              value={bookingPage.branding.logo_url || ''}
              onChange={(e) => updateBranding('logo_url', e.target.value || null)}
              placeholder="https://example.com/logo.png"
            />
          </div>
          <div className="form-field">
            <label>Primary Color</label>
            <div className="color-input-row">
              <input
                type="color"
                value={bookingPage.branding.primary_color}
                onChange={(e) => updateBranding('primary_color', e.target.value)}
              />
              <input
                type="text"
                value={bookingPage.branding.primary_color}
                onChange={(e) => updateBranding('primary_color', e.target.value)}
                className="color-text-input"
              />
            </div>
          </div>
          <div className="form-field">
            <label>Secondary Color</label>
            <div className="color-input-row">
              <input
                type="color"
                value={bookingPage.branding.secondary_color}
                onChange={(e) => updateBranding('secondary_color', e.target.value)}
              />
              <input
                type="text"
                value={bookingPage.branding.secondary_color}
                onChange={(e) => updateBranding('secondary_color', e.target.value)}
                className="color-text-input"
              />
            </div>
          </div>
          <div className="form-field full-width">
            <label>Tagline</label>
            <input
              type="text"
              value={bookingPage.branding.tagline || ''}
              onChange={(e) => updateBranding('tagline', e.target.value)}
              placeholder="Your trusted mortgage partner"
            />
          </div>
          <div className="form-field full-width">
            <label>Welcome Message</label>
            <textarea
              value={bookingPage.branding.welcome_message || ''}
              onChange={(e) => updateBranding('welcome_message', e.target.value)}
              rows={2}
              placeholder="Schedule a time to meet with us"
            />
          </div>
          <div className="form-field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={bookingPage.branding.show_branding}
                onChange={(e) => updateBranding('show_branding', e.target.checked)}
              />
              Show Perennia branding
            </label>
          </div>
        </div>

        {/* Preview */}
        <h3 className="subsection-title">Preview</h3>
        <div
          className="booking-preview"
          style={{
            borderColor: bookingPage.branding.primary_color,
            backgroundColor: bookingPage.branding.secondary_color,
          }}
        >
          {bookingPage.branding.logo_url && (
            <img src={bookingPage.branding.logo_url} alt="Logo" className="preview-logo" />
          )}
          <h4 style={{ color: bookingPage.branding.primary_color }}>
            {bookingPage.branding.tagline || 'Your Booking Page'}
          </h4>
          <p>{bookingPage.branding.welcome_message || 'Schedule a time to meet with us'}</p>
          <button className="preview-cta" style={{ backgroundColor: bookingPage.branding.primary_color }}>
            Book an Appointment
          </button>
        </div>

        {/* Booking Links */}
        <h3 className="subsection-title">Booking Links</h3>
        {bookingPage.booking_links.length === 0 ? (
          <p className="empty-hint">No booking links yet. Create one in the Booking Links tab of Smart Scheduler Settings.</p>
        ) : (
          <div className="booking-links-list">
            {bookingPage.booking_links.map(link => (
              <div key={link.id} className="booking-link-row">
                <div className="link-info">
                  <strong>{link.name}</strong>
                  <code>{window.location.origin}{link.url}</code>
                </div>
                <div className="link-actions">
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => handleCopyLink(link.url)}
                  >
                    <i className={`fas ${copiedLink === link.url ? 'fa-check' : 'fa-copy'}`}></i>
                    {copiedLink === link.url ? 'Copied' : 'Copy'}
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => {
                      const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(window.location.origin + link.url)}`;
                      window.open(qrUrl, '_blank');
                    }}
                    title="Generate QR Code"
                  >
                    <i className="fas fa-qrcode"></i> QR
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    );
  };

  // ============================================================================
  // Render: Tab 5 - Locations & Labels
  // ============================================================================

  const renderLocationsLabels = () => {
    const LOCATION_TYPE_ICONS = {
      office: 'fa-building',
      virtual: 'fa-video',
      phone: 'fa-phone',
      borrower_home: 'fa-home',
    };

    const durationLabel = (min) => {
      if (min >= 60) {
        const h = Math.floor(min / 60);
        const m = min % 60;
        return m > 0 ? `${h}h ${m}m` : `${h} hour${h > 1 ? 's' : ''}`;
      }
      return `${min} min`;
    };

    return (
      <div role="tabpanel" id="panel-locations-labels" aria-labelledby="calnav-locations-labels">

        {/* ---- Section 1: Meeting Locations ---- */}
        <section className="cal-settings-section loc-labels-section">
          <button
            type="button"
            className="collapsible-header"
            onClick={() => toggleLocLabelsSection('locations')}
            aria-expanded={locLabelsExpanded.locations}
          >
            <div className="collapsible-header-left">
              <i className={`fas fa-chevron-${locLabelsExpanded.locations ? 'down' : 'right'} collapsible-chevron`}></i>
              <div>
                <h2>Meeting Locations</h2>
                <p className="section-description">
                  Define where appointments take place -- office, virtual, phone, or borrower's home.
                </p>
              </div>
            </div>
            <span className="collapsible-badge">
              <i className="fas fa-map-marker-alt"></i>
            </span>
          </button>
          {locLabelsExpanded.locations && (
            <div className="collapsible-body">
              <LocationManager />
            </div>
          )}
        </section>

        {/* ---- Section 2: Calendar Labels ---- */}
        <section className="cal-settings-section loc-labels-section">
          <button
            type="button"
            className="collapsible-header"
            onClick={() => toggleLocLabelsSection('labels')}
            aria-expanded={locLabelsExpanded.labels}
          >
            <div className="collapsible-header-left">
              <i className={`fas fa-chevron-${locLabelsExpanded.labels ? 'down' : 'right'} collapsible-chevron`}></i>
              <div>
                <h2>Calendar Labels</h2>
                <p className="section-description">
                  Color-coded labels to categorize and filter your appointments at a glance.
                </p>
              </div>
            </div>
            <span className="collapsible-badge">
              <i className="fas fa-tags"></i>
            </span>
          </button>
          {locLabelsExpanded.labels && (
            <div className="collapsible-body">
              <LabelManager
                labels={labels}
                onCreateLabel={handleCreateLabel}
                onUpdateLabel={handleUpdateLabel}
                onDeleteLabel={handleDeleteLabel}
                onReorderLabels={handleReorderLabels}
                loading={labelsLoading}
              />

              {/* Auto-assign toggle */}
              <div className="auto-assign-section">
                <label className="toggle-row auto-assign-toggle">
                  <input
                    type="checkbox"
                    checked={autoAssignLabels}
                    onChange={(e) => handleToggleAutoAssign(e.target.checked)}
                  />
                  <span>Auto-assign labels based on appointment type</span>
                </label>

                {autoAssignLabels && appointmentTypes.length > 0 && (
                  <div className="label-mapping-grid">
                    {appointmentTypes.map(type => (
                      <div key={type.id} className="label-mapping-row">
                        <div className="mapping-type-name">
                          <div
                            className="mapping-color-dot"
                            style={{ backgroundColor: type.color || '#218D8D' }}
                          />
                          <span>{type.type_name}</span>
                        </div>
                        <select
                          value={labelMappings[type.id] || ''}
                          onChange={(e) => handleUpdateLabelMapping(type.id, e.target.value || null)}
                          className="mapping-select"
                        >
                          <option value="">No label</option>
                          {labels.map(label => (
                            <option key={label.id} value={label.id}>
                              {label.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                )}

                {autoAssignLabels && appointmentTypes.length === 0 && (
                  <p className="empty-hint" style={{ marginTop: 8 }}>
                    Create appointment types first to set up label mappings.
                  </p>
                )}
              </div>
            </div>
          )}
        </section>

        {/* ---- Section 3: Appointment Templates ---- */}
        <section className="cal-settings-section loc-labels-section">
          <button
            type="button"
            className="collapsible-header"
            onClick={() => toggleLocLabelsSection('templates')}
            aria-expanded={locLabelsExpanded.templates}
          >
            <div className="collapsible-header-left">
              <i className={`fas fa-chevron-${locLabelsExpanded.templates ? 'down' : 'right'} collapsible-chevron`}></i>
              <div>
                <h2>Appointment Templates</h2>
                <p className="section-description">
                  Pre-configured appointment setups for quick scheduling. Set a default for one-click booking.
                </p>
              </div>
            </div>
            <span className="collapsible-badge">
              <i className="fas fa-copy"></i>
            </span>
          </button>
          {locLabelsExpanded.templates && (
            <div className="collapsible-body">
              {templatesLoading ? (
                <div className="empty-hint">Loading templates...</div>
              ) : templates.length === 0 ? (
                <div className="empty-state">
                  <i className="fas fa-layer-group"></i>
                  <p>No appointment templates yet.</p>
                  <p className="empty-hint">
                    Templates help you quickly create common appointment types with pre-filled settings.
                  </p>
                </div>
              ) : (
                <div className="template-list">
                  {templates.map(template => (
                    <div key={template.id} className={`template-card${template.is_default ? ' is-default' : ''}`}>
                      <div className="template-card-left">
                        <div className="template-card-header">
                          <strong>{template.name}</strong>
                          {template.is_default && (
                            <span className="badge badge-default">Default</span>
                          )}
                        </div>
                        <div className="template-meta">
                          <span>
                            <i className="fas fa-clock"></i> {durationLabel(template.duration_minutes || 30)}
                          </span>
                          {template.location_type && (
                            <span>
                              <i className={`fas ${LOCATION_TYPE_ICONS[template.location_type] || 'fa-map-pin'}`}></i>
                              {' '}{template.location_type.replace('_', ' ')}
                            </span>
                          )}
                          {template.appointment_type_name && (
                            <span>
                              <i className="fas fa-tag"></i> {template.appointment_type_name}
                            </span>
                          )}
                        </div>
                        {template.description && (
                          <p className="template-desc">{template.description}</p>
                        )}
                      </div>
                      <div className="template-card-actions">
                        {!template.is_default && (
                          <button
                            className="btn-secondary btn-sm"
                            onClick={() => handleToggleDefaultTemplate(template.id)}
                            title="Use as default"
                          >
                            <i className="fas fa-star"></i> Set Default
                          </button>
                        )}
                        <button
                          className="icon-btn danger"
                          onClick={() => handleDeleteTemplate(template.id)}
                          title="Delete template"
                        >
                          <i className="fas fa-trash"></i>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    );
  };

  // ============================================================================
  // Render: Tab 6 - Integrations
  // ============================================================================

  const renderIntegrations = () => (
    <section className="cal-settings-section" role="tabpanel" id="panel-integrations" aria-labelledby="calnav-integrations">
      <h2>Calendar Integrations</h2>
      <p className="section-description">Connect your external calendars to sync events and check availability.</p>

      <div className="integration-cards">
        {/* Google Calendar */}
        <div className={`integration-card ${integrations.google?.connected ? 'connected' : ''}`}>
          <div className="integration-icon google">
            <i className="fab fa-google"></i>
          </div>
          <div className="integration-info">
            <h3>Google Calendar</h3>
            {integrations.google?.connected ? (
              <>
                <p className="connected-text">
                  <i className="fas fa-check-circle"></i> Connected as {integrations.google.email}
                </p>
                {integrations.google.last_synced && (
                  <p className="sync-time">Last synced: {new Date(integrations.google.last_synced).toLocaleString()}</p>
                )}
              </>
            ) : (
              <p className="disconnected-text">Not connected</p>
            )}
          </div>
          <div className="integration-action">
            {integrations.google?.connected ? (
              <button
                className="btn-secondary btn-sm"
                onClick={() => {
                  window.location.href = `${API_BASE_URL}/api/v1/google-calendar/disconnect`;
                }}
              >
                Disconnect
              </button>
            ) : (
              <button
                className="btn-primary btn-sm"
                onClick={() => {
                  window.location.href = `${API_BASE_URL}/api/v1/google-calendar/connect`;
                }}
              >
                Connect
              </button>
            )}
          </div>
        </div>

        {/* Outlook Calendar */}
        <div className={`integration-card ${integrations.outlook?.connected ? 'connected' : ''}`}>
          <div className="integration-icon outlook">
            <i className="fab fa-microsoft"></i>
          </div>
          <div className="integration-info">
            <h3>Outlook Calendar</h3>
            {integrations.outlook?.connected ? (
              <>
                <p className="connected-text">
                  <i className="fas fa-check-circle"></i> Connected as {integrations.outlook.email}
                </p>
                {integrations.outlook.last_synced && (
                  <p className="sync-time">Last synced: {new Date(integrations.outlook.last_synced).toLocaleString()}</p>
                )}
              </>
            ) : (
              <p className="disconnected-text">Not connected</p>
            )}
          </div>
          <div className="integration-action">
            {integrations.outlook?.connected ? (
              <button
                className="btn-secondary btn-sm"
                onClick={() => {
                  window.location.href = `${API_BASE_URL}/api/v1/microsoft/calendar/disconnect`;
                }}
              >
                Disconnect
              </button>
            ) : (
              <button
                className="btn-primary btn-sm"
                onClick={() => {
                  window.location.href = `${API_BASE_URL}/api/v1/microsoft/calendar/connect`;
                }}
              >
                Connect
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );

  // ============================================================================
  // Render: Tab 7 - Team
  // ============================================================================

  const renderTeam = () => {
    if (!isManager) {
      return (
        <section className="cal-settings-section" role="tabpanel" id="panel-team" aria-labelledby="calnav-team">
          <div className="empty-state">
            <i className="fas fa-lock"></i>
            <p>Team calendar settings are available to managers only.</p>
          </div>
        </section>
      );
    }

    return (
      <section className="cal-settings-section" role="tabpanel" id="panel-team" aria-labelledby="calnav-team">
        <h2>Team Calendar</h2>
        <p className="section-description">Manage how appointments are distributed across your team.</p>

        <h3 className="subsection-title">Assignment Strategy</h3>
        <div className="strategy-options">
          {ASSIGNMENT_STRATEGIES.map(strategy => (
            <label
              key={strategy.value}
              className={`strategy-option ${team.assignment_strategy === strategy.value ? 'selected' : ''}`}
            >
              <input
                type="radio"
                name="strategy"
                value={strategy.value}
                checked={team.assignment_strategy === strategy.value}
                onChange={() => {
                  setTeam(prev => ({ ...prev, assignment_strategy: strategy.value }));
                  markChanged();
                }}
              />
              <div className="strategy-content">
                <strong>{strategy.label}</strong>
                <span>{strategy.description}</span>
              </div>
            </label>
          ))}
        </div>

        <h3 className="subsection-title">Team Members ({team.total_members})</h3>
        <div className="team-table-wrap">
          <table className="team-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Max Daily</th>
                <th>Upcoming</th>
                <th>Accepting</th>
              </tr>
            </thead>
            <tbody>
              {(team.members || []).map(member => (
                <tr key={member.user_id}>
                  <td className="member-name">{member.name}</td>
                  <td className="member-email">{member.email}</td>
                  <td>
                    <input
                      type="number"
                      min="0"
                      max="24"
                      value={member.max_daily_appointments}
                      className="capacity-input"
                      onChange={(e) => {
                        const val = parseInt(e.target.value) || 0;
                        setTeam(prev => ({
                          ...prev,
                          members: prev.members.map(m =>
                            m.user_id === member.user_id ? { ...m, max_daily_appointments: val } : m
                          ),
                        }));
                        markChanged();
                      }}
                    />
                  </td>
                  <td className="upcoming-count">{member.upcoming_appointments}</td>
                  <td>
                    <label className="toggle-switch">
                      <input
                        type="checkbox"
                        checked={member.is_accepting_appointments}
                        onChange={(e) => {
                          setTeam(prev => ({
                            ...prev,
                            members: prev.members.map(m =>
                              m.user_id === member.user_id ? { ...m, is_accepting_appointments: e.target.checked } : m
                            ),
                          }));
                          markChanged();
                        }}
                      />
                      <span className="toggle-slider"></span>
                    </label>
                  </td>
                </tr>
              ))}
              {(!team.members || team.members.length === 0) && (
                <tr>
                  <td colSpan={5} className="empty-row">No team members found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  };

  // ============================================================================
  // Render: Cancellation Policy
  // ============================================================================

  const renderCancellationPolicy = () => (
    <div role="tabpanel" id="panel-cancellation-policy" aria-labelledby="calnav-cancellation-policy">
      <section className="cal-settings-section">
        <h2>Cancellation Policy</h2>
        <p className="section-description">Set rules for when clients can cancel or reschedule appointments.</p>

        <div className="cancel-policy-options">
          {CANCELLATION_POLICIES.map(policy => (
            <label
              key={policy.value}
              className={`cancel-policy-option ${cancellationPolicy.policy === policy.value ? 'selected' : ''}`}
            >
              <input
                type="radio"
                name="cancellation-policy"
                value={policy.value}
                checked={cancellationPolicy.policy === policy.value}
                onChange={() => {
                  setCancellationPolicy(prev => ({ ...prev, policy: policy.value }));
                  markChanged();
                }}
              />
              <div className="strategy-content">
                <strong>{policy.label}</strong>
                <span>{policy.description}</span>
              </div>
            </label>
          ))}
        </div>

        <h3 className="subsection-title">Rescheduling</h3>
        <div className="form-grid">
          <div className="form-field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={cancellationPolicy.allow_reschedule}
                onChange={(e) => {
                  setCancellationPolicy(prev => ({ ...prev, allow_reschedule: e.target.checked }));
                  markChanged();
                }}
              />
              Allow clients to reschedule online
            </label>
          </div>
          <div className="form-field">
            <label htmlFor="reschedule-limit">Max reschedules per appointment</label>
            <input
              id="reschedule-limit"
              type="number"
              min="0"
              max="10"
              value={cancellationPolicy.reschedule_limit}
              onChange={(e) => {
                setCancellationPolicy(prev => ({ ...prev, reschedule_limit: parseInt(e.target.value) || 0 }));
                markChanged();
              }}
            />
          </div>
          <div className="form-field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={cancellationPolicy.require_reason}
                onChange={(e) => {
                  setCancellationPolicy(prev => ({ ...prev, require_reason: e.target.checked }));
                  markChanged();
                }}
              />
              Require reason for cancellation
            </label>
          </div>
        </div>
      </section>
    </div>
  );

  // ============================================================================
  // Render: Advanced
  // ============================================================================

  const renderAdvanced = () => (
    <div role="tabpanel" id="panel-advanced" aria-labelledby="calnav-advanced">
      <section className="cal-settings-section">
        <h2>Advanced Settings</h2>
        <p className="section-description">Additional configuration options for power users.</p>

        <div className="advanced-settings-list">
          <div className="advanced-setting-item">
            <div className="advanced-setting-info">
              <h4>Auto-confirm Appointments</h4>
              <p>Automatically confirm appointments without manual approval.</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={advancedSettings.auto_confirm_appointments}
                onChange={(e) => {
                  setAdvancedSettings(prev => ({ ...prev, auto_confirm_appointments: e.target.checked }));
                  markChanged();
                }}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="advanced-setting-item">
            <div className="advanced-setting-info">
              <h4>Show Timezone Selector</h4>
              <p>Allow clients to select their timezone on the booking page.</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={advancedSettings.show_timezone_selector}
                onChange={(e) => {
                  setAdvancedSettings(prev => ({ ...prev, show_timezone_selector: e.target.checked }));
                  markChanged();
                }}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="advanced-setting-item">
            <div className="advanced-setting-info">
              <h4>Enable Waitlist</h4>
              <p>Allow clients to join a waitlist when no slots are available.</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={advancedSettings.enable_waitlist}
                onChange={(e) => {
                  setAdvancedSettings(prev => ({ ...prev, enable_waitlist: e.target.checked }));
                  markChanged();
                }}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="advanced-setting-item">
            <div className="advanced-setting-info">
              <h4>Calendar Feed (iCal/ICS)</h4>
              <p>Generate an ICS feed URL for subscribing in external calendar apps.</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={advancedSettings.calendar_feed_enabled}
                onChange={(e) => {
                  setAdvancedSettings(prev => ({ ...prev, calendar_feed_enabled: e.target.checked }));
                  markChanged();
                }}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>
        </div>
      </section>

      {advancedSettings.calendar_feed_enabled && (
        <section className="cal-settings-section">
          <CalendarFeedSettings />
        </section>
      )}
    </div>
  );

  // ============================================================================
  // Render: Section Router
  // ============================================================================

  const renderActiveSection = () => {
    if (loading) return renderLoading();

    switch (activeSection) {
      case 'availability': return renderAvailability();
      case 'appointment-types': return renderAppointmentTypes();
      case 'locations-labels': return renderLocationsLabels();
      case 'booking-page': return renderBookingPage();
      case 'cancellation-policy': return renderCancellationPolicy();
      case 'notifications': return renderNotifications();
      case 'integrations': return renderIntegrations();
      case 'team': return renderTeam();
      case 'advanced': return renderAdvanced();
      default: return renderAvailability();
    }
  };

  // ============================================================================
  // Render: Main Layout
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
            {/* Save Status Indicator */}
            <div className={`save-status ${saveStatus}`}>
              <span className="status-dot"></span>
              <span>
                {saveStatus === 'saved' && 'All changes saved'}
                {saveStatus === 'saving' && 'Saving...'}
                {saveStatus === 'unsaved' && 'Unsaved changes'}
              </span>
            </div>

            {/* Action Buttons */}
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
            <div key={section.group} className="sidebar-nav-group">
              <span className="sidebar-group-label">{section.group}</span>
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
                  <i className={`fas ${item.icon}`}></i>
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

// ============================================================================
// Sub-component: Edit Type Form (inline)
// ============================================================================

function EditTypeForm({ type, onSave, onCancel }) {
  const [form, setForm] = useState({
    type_name: type.type_name || '',
    description: type.description || '',
    duration_minutes: type.duration_minutes || 30,
    color: type.color || '#218D8D',
    is_public: type.is_public !== false,
  });

  return (
    <div className="edit-type-form">
      <div className="form-grid">
        <div className="form-field">
          <label>Name</label>
          <input
            type="text"
            value={form.type_name}
            onChange={(e) => setForm(prev => ({ ...prev, type_name: e.target.value }))}
          />
        </div>
        <div className="form-field">
          <label>Duration</label>
          <select
            value={form.duration_minutes}
            onChange={(e) => setForm(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
          >
            <option value={15}>15 min</option>
            <option value={30}>30 min</option>
            <option value={45}>45 min</option>
            <option value={60}>60 min</option>
            <option value={90}>90 min</option>
          </select>
        </div>
        <div className="form-field full-width">
          <label>Description</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
            rows={2}
          />
        </div>
        <div className="form-field">
          <label>Color</label>
          <div className="color-picker">
            {DEFAULT_COLORS.map(c => (
              <button
                key={c}
                type="button"
                className={`color-swatch ${form.color === c ? 'selected' : ''}`}
                style={{ backgroundColor: c }}
                onClick={() => setForm(prev => ({ ...prev, color: c }))}
                aria-label={`Color ${c}`}
              />
            ))}
          </div>
        </div>
        <div className="form-field">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.is_public}
              onChange={(e) => setForm(prev => ({ ...prev, is_public: e.target.checked }))}
            />
            Public
          </label>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
        <button
          className="btn-primary btn-sm"
          disabled={!form.type_name.trim()}
          onClick={() => onSave(form)}
        >
          Save
        </button>
      </div>
    </div>
  );
}

export default CalendarSettings;
