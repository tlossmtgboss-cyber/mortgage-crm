import { useState, useEffect } from 'react';
import { getAuthHeaders } from '../../utils/auth';
import { toast } from '../../utils/toast';
import { API_BASE } from './utils';

const DEFAULT_CONFIG = {
  working_hours: {
    monday: { enabled: true, start: '09:00', end: '17:00' },
    tuesday: { enabled: true, start: '09:00', end: '17:00' },
    wednesday: { enabled: true, start: '09:00', end: '17:00' },
    thursday: { enabled: true, start: '09:00', end: '17:00' },
    friday: { enabled: true, start: '09:00', end: '17:00' },
    saturday: { enabled: false, start: '09:00', end: '12:00' },
    sunday: { enabled: false, start: '09:00', end: '12:00' }
  },
  default_duration_minutes: 30,
  buffer_before_minutes: 5,
  buffer_after_minutes: 5,
  min_notice_hours: 2,
  max_advance_days: 30,
  max_meetings_per_day: 8,
  ai_scheduling_enabled: true,
  auto_reschedule_enabled: true,
  smart_reminders_enabled: true
};

const DEFAULT_LANDING_PAGE = {
  logo_url: '',
  profile_picture_url: '',
  video_url: '',
  video_type: 'youtube',
  headline: 'Schedule a Video Meeting',
  subheadline: 'Choose a time that works for you',
  description: '',
  show_profile: true,
  profile_name: '',
  profile_title: '',
  profile_bio: '',
  accent_color: '#2D7A52',
  background_style: 'white',
  show_company_logo: true,
  show_social_proof: false,
  testimonial_text: '',
  testimonial_author: ''
};

const DEFAULT_REMINDER_SETTINGS = {
  enabled: true,
  bookingConfirmation: {
    enabled: true,
    method: 'both',
    emailSubject: 'Your Video Meeting is Confirmed',
    message: 'Your video meeting has been confirmed for {{appointment_date}} at {{appointment_time}}. You will receive a meeting link before the call.'
  },
  reminders: [
    { id: 1, timing: 24, unit: 'hours', method: 'both', enabled: true, message: 'Reminder: Your video meeting is scheduled for {{appointment_time}} on {{appointment_date}}. Please ensure your camera and microphone are working.' },
    { id: 2, timing: 1, unit: 'hours', method: 'sms', enabled: true, message: 'Your video meeting starts in 1 hour at {{appointment_time}}. Check your inbox for the meeting link.' },
    { id: 3, timing: 15, unit: 'minutes', method: 'sms', enabled: false, message: 'Your video meeting starts in 15 minutes!' }
  ],
  default_email_subject: 'Reminder: Your Upcoming Video Meeting',
  include_calendar_link: true,
  include_reschedule_link: true,
  include_cancel_link: true
};

export const useVideoMeetingsState = ({ leadId, loanId }) => {
  const [view, setView] = useState('types');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Data states
  const [meetings, setMeetings] = useState([]);
  const [meetingTypes, setMeetingTypes] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [stats, setStats] = useState(null);
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [bookingLinks, setBookingLinks] = useState([]);
  const [config, setConfig] = useState(null);

  // Filter states
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('upcoming');

  // Create meeting form
  const [meetingForm, setMeetingForm] = useState({
    room_name: '',
    room_description: '',
    scheduled_start: '',
    duration_minutes: 30,
    meeting_type: 'general',
    recording_enabled: true,
    transcription_enabled: true,
    ai_assistant_enabled: true,
    waiting_room_enabled: true,
    template_id: null
  });

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showMeetingDetail, setShowMeetingDetail] = useState(false);
  const [showRecordingPlayer, setShowRecordingPlayer] = useState(false);
  const [selectedRecording, setSelectedRecording] = useState(null);
  const [showNewTypeModal, setShowNewTypeModal] = useState(false);
  const [showNewLinkModal, setShowNewLinkModal] = useState(false);
  const [editingType, setEditingType] = useState(null);

  // Settings sub-tab state
  const [settingsTab, setSettingsTab] = useState('working-hours');
  const [editableConfig, setEditableConfig] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);

  // Landing Page state
  const [landingPageSettings, setLandingPageSettings] = useState({ ...DEFAULT_LANDING_PAGE });
  const [savingLandingPage, setSavingLandingPage] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);

  // Reminder settings state
  const [reminderSettings, setReminderSettings] = useState({ ...DEFAULT_REMINDER_SETTINGS });
  const [savingReminders, setSavingReminders] = useState(false);

  // Link form state
  const [linkForm, setLinkForm] = useState({
    slug: '',
    link_name: '',
    description: '',
    meeting_type_ids: []
  });

  // Meeting type form state
  const [typeForm, setTypeForm] = useState({
    type_name: '',
    type_key: '',
    description: '',
    default_duration_minutes: 30,
    allowed_durations: [15, 30, 45, 60],
    color: '#2D7A52',
    icon: 'video',
    is_public: true,
    requires_confirmation: false,
    buffer_before_minutes: 5,
    buffer_after_minutes: 5,
    recording_enabled: true,
    ai_assistant_enabled: true
  });

  // Fetch initial data
  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [meetingsRes, templatesRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/meetings/rooms?limit=50`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/meetings/templates`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/meetings/stats`, { headers: getAuthHeaders() })
      ]);

      if (meetingsRes.ok) {
        const meetingsData = await meetingsRes.json();
        setMeetings(meetingsData.meetings || []);
      }

      if (templatesRes.ok) {
        const templatesData = await templatesRes.json();
        setTemplates(templatesData.templates || []);
        setMeetingTypes(templatesData.templates || []);
      }

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData.stats || null);
      }

      setConfig({ ...DEFAULT_CONFIG });
      setEditableConfig(JSON.parse(JSON.stringify(DEFAULT_CONFIG)));
      setBookingLinks([]);
    } catch (err) {
      setError('Failed to load meeting data');
      console.error('Meetings fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const createInstantMeeting = async () => {
    const newWindow = window.open('about:blank', '_blank');
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/api/v1/meetings/instant`, {
        method: 'POST',
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        if (newWindow) {
          newWindow.location.href = data.meeting.join_url;
        } else {
          toast.success(`Meeting created! Open this link: ${window.location.origin}${data.meeting.join_url}`);
        }
        fetchData();
      } else {
        if (newWindow) newWindow.close();
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || 'Failed to create instant meeting');
      }
    } catch (err) {
      if (newWindow) newWindow.close();
      setError('Failed to create instant meeting. Please check your connection.');
      console.error('Instant meeting error:', err);
    } finally {
      setLoading(false);
    }
  };

  const createScheduledMeeting = async () => {
    try {
      const payload = {
        ...meetingForm,
        loan_id: loanId || null,
        lead_id: leadId || null
      };
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload)
      });
      if (response.ok) {
        setShowCreateModal(false);
        setMeetingForm({
          room_name: '', room_description: '', scheduled_start: '',
          duration_minutes: 30, meeting_type: 'general', recording_enabled: true,
          transcription_enabled: true, ai_assistant_enabled: true,
          waiting_room_enabled: true, template_id: null
        });
        fetchData();
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to create meeting');
      }
    } catch (err) {
      setError('Failed to create meeting');
      console.error('Create meeting error:', err);
    }
  };

  const getMeetingDetails = async (meetingId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setSelectedMeeting(data);
        setShowMeetingDetail(true);
      }
    } catch (err) {
      console.error('Get meeting details error:', err);
    }
  };

  const startMeeting = async (meetingId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}/start`, {
        method: 'POST', headers: getAuthHeaders()
      });
      if (response.ok) fetchData();
    } catch (err) {
      console.error('Start meeting error:', err);
    }
  };

  const endMeeting = async (meetingId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}/end`, {
        method: 'POST', headers: getAuthHeaders()
      });
      if (response.ok) {
        fetchData();
        setShowMeetingDetail(false);
      }
    } catch (err) {
      console.error('End meeting error:', err);
    }
  };

  const cancelMeeting = async (meetingId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}`, {
        method: 'DELETE', headers: getAuthHeaders()
      });
      if (response.ok) {
        fetchData();
        setShowMeetingDetail(false);
      }
    } catch (err) {
      console.error('Cancel meeting error:', err);
    }
  };

  const viewRecording = async (recordingId, meetingTitle) => {
    try {
      const [transcriptRes, analysisRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/meetings/recordings/${recordingId}/transcript`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/v1/meetings/recordings/${recordingId}/analysis`, { headers: getAuthHeaders() })
      ]);
      let transcript = {};
      let analysis = {};
      if (transcriptRes.ok) transcript = await transcriptRes.json();
      if (analysisRes.ok) analysis = await analysisRes.json();

      setSelectedRecording({
        id: recordingId,
        meeting_title: meetingTitle,
        recording_url: `${API_BASE}/api/v1/meetings/recordings/${recordingId}/stream`,
        transcript,
        analysis: analysis.analysis || {},
        created_at: new Date().toISOString()
      });
      setShowRecordingPlayer(true);
    } catch (err) {
      console.error('View recording error:', err);
      setError('Failed to load recording');
    }
  };

  const seedDefaultTemplates = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/templates/seed-defaults`, {
        method: 'POST', headers: getAuthHeaders()
      });
      if (response.ok) {
        fetchData();
        toast.success('Default meeting types created!');
      }
    } catch (err) {
      console.error('Seed templates error:', err);
    }
  };

  const handleSaveMeetingType = async () => {
    try {
      const isEditing = editingType !== null;
      const url = isEditing
        ? `${API_BASE}/api/v1/meetings/templates/${editingType.id}`
        : `${API_BASE}/api/v1/meetings/templates`;
      const payload = {
        template_name: typeForm.type_name,
        template_key: typeForm.type_key || typeForm.type_name.toLowerCase().replace(/\s+/g, '_'),
        description: typeForm.description,
        default_duration_minutes: typeForm.default_duration_minutes,
        color: typeForm.color,
        icon: typeForm.icon,
        recording_enabled: typeForm.recording_enabled,
        ai_assistant_enabled: typeForm.ai_assistant_enabled
      };
      const response = await fetch(url, {
        method: isEditing ? 'PUT' : 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload)
      });
      if (response.ok) {
        setShowNewTypeModal(false);
        setEditingType(null);
        resetTypeForm();
        fetchData();
        toast.success(isEditing ? 'Meeting type updated!' : 'Meeting type created!');
      } else {
        const err = await response.json();
        toast.error(`Failed to save: ${err.detail}`);
      }
    } catch (err) {
      console.error('Save type error:', err);
      toast.error('Failed to save meeting type');
    }
  };

  const handleDeleteMeetingType = async (typeId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/templates/${typeId}`, {
        method: 'DELETE', headers: getAuthHeaders()
      });
      if (response.ok) {
        fetchData();
        toast.success('Meeting type deleted!');
      } else {
        const err = await response.json();
        toast.error(`Failed to delete: ${err.detail}`);
      }
    } catch (err) {
      console.error('Delete type error:', err);
    }
  };

  const handleEditType = (type) => {
    setEditingType(type);
    setTypeForm({
      type_name: type.template_name || type.type_name || '',
      type_key: type.template_key || type.type_key || '',
      description: type.description || '',
      default_duration_minutes: type.default_duration_minutes || 30,
      allowed_durations: type.allowed_durations || [15, 30, 45, 60],
      color: type.color || '#2D7A52',
      icon: type.icon || 'video',
      is_public: type.is_public !== false,
      requires_confirmation: type.requires_confirmation || false,
      buffer_before_minutes: type.buffer_before_minutes || 5,
      buffer_after_minutes: type.buffer_after_minutes || 5,
      recording_enabled: type.recording_enabled !== false,
      ai_assistant_enabled: type.ai_assistant_enabled !== false
    });
    setShowNewTypeModal(true);
  };

  const resetTypeForm = () => {
    setTypeForm({
      type_name: '', type_key: '', description: '',
      default_duration_minutes: 30, allowed_durations: [15, 30, 45, 60],
      color: '#2D7A52', icon: 'video', is_public: true,
      requires_confirmation: false, buffer_before_minutes: 5,
      buffer_after_minutes: 5, recording_enabled: true,
      ai_assistant_enabled: true
    });
  };

  const handleCreateBookingLink = async (linkData) => {
    const newLink = {
      id: Date.now(),
      ...linkData,
      view_count: 0,
      booking_count: 0,
      created_at: new Date().toISOString()
    };
    setBookingLinks([...bookingLinks, newLink]);
    setShowNewLinkModal(false);
    setLinkForm({ slug: '', link_name: '', description: '', meeting_type_ids: [] });
    toast.success('Booking link created!');
  };

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 500));
      setConfig(JSON.parse(JSON.stringify(editableConfig)));
      toast.success('Settings saved successfully!');
    } catch (err) {
      console.error('Save settings error:', err);
      toast.error('Failed to save settings');
    } finally {
      setSavingSettings(false);
    }
  };

  const updateWorkingHours = (day, field, value) => {
    setEditableConfig(prev => ({
      ...prev,
      working_hours: {
        ...prev.working_hours,
        [day]: { ...prev.working_hours[day], [field]: value }
      }
    }));
  };

  const updateConfigField = (field, value) => {
    setEditableConfig(prev => ({ ...prev, [field]: value }));
  };

  const applyTemplate = (template) => {
    setMeetingForm({
      ...meetingForm,
      room_name: template.template_name,
      meeting_type: template.template_key,
      duration_minutes: template.default_duration_minutes,
      recording_enabled: template.recording_enabled,
      ai_assistant_enabled: template.ai_assistant_enabled,
      template_id: template.id
    });
  };

  const getFilteredMeetings = () => {
    let filtered = [...meetings];
    if (leadId) filtered = filtered.filter(m => m.lead_id !== leadId);
    if (loanId) filtered = filtered.filter(m => m.loan_id !== loanId);
    if (statusFilter !== 'all') filtered = filtered.filter(m => m.status === statusFilter);

    const now = new Date();
    if (dateFilter === 'upcoming') {
      filtered = filtered.filter(m => m.scheduled_start && new Date(m.scheduled_start) >= now);
    } else if (dateFilter === 'past') {
      filtered = filtered.filter(m => m.scheduled_start && new Date(m.scheduled_start) < now);
    } else if (dateFilter === 'today') {
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const todayEnd = new Date(todayStart.getTime() + 24 * 60 * 60 * 1000);
      filtered = filtered.filter(m => {
        const start = new Date(m.scheduled_start);
        return start >= todayStart && start < todayEnd;
      });
    }
    return filtered;
  };

  const handleSaveLandingPage = async () => {
    setSavingLandingPage(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 500));
      toast.success('Landing page settings saved successfully!');
    } catch (err) {
      console.error('Save landing page error:', err);
      toast.error('Failed to save landing page settings');
    } finally {
      setSavingLandingPage(false);
    }
  };

  return {
    // View state
    view, setView,
    loading, error, setError,

    // Data
    meetings, meetingTypes, templates, stats,
    selectedMeeting, setSelectedMeeting,
    bookingLinks, config, editableConfig, setEditableConfig,

    // Filters
    statusFilter, setStatusFilter,
    dateFilter, setDateFilter,

    // Forms
    meetingForm, setMeetingForm,
    typeForm, setTypeForm,
    linkForm, setLinkForm,

    // Modals
    showCreateModal, setShowCreateModal,
    showMeetingDetail, setShowMeetingDetail,
    showRecordingPlayer, setShowRecordingPlayer,
    selectedRecording, setSelectedRecording,
    showNewTypeModal, setShowNewTypeModal,
    showNewLinkModal, setShowNewLinkModal,
    editingType, setEditingType,

    // Settings
    settingsTab, setSettingsTab,
    savingSettings,

    // Landing page
    landingPageSettings, setLandingPageSettings,
    savingLandingPage, previewMode, setPreviewMode,

    // Reminders
    reminderSettings, setReminderSettings,
    savingReminders, setSavingReminders,

    // Actions
    fetchData,
    createInstantMeeting,
    createScheduledMeeting,
    getMeetingDetails,
    startMeeting,
    endMeeting,
    cancelMeeting,
    viewRecording,
    seedDefaultTemplates,
    handleSaveMeetingType,
    handleDeleteMeetingType,
    handleEditType,
    resetTypeForm,
    handleCreateBookingLink,
    handleSaveSettings,
    updateWorkingHours,
    updateConfigField,
    applyTemplate,
    getFilteredMeetings,
    handleSaveLandingPage,

    // Constants
    DEFAULT_LANDING_PAGE
  };
};
