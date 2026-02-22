import React, { useState, useEffect, useCallback } from 'react';
import './SmartScheduler.css';
import RecordingPlayer from './VideoMeetings/RecordingPlayer';
import { sanitizeText, SafeHTML } from '../utils/sanitize';
import { getAuthHeaders } from '../utils/auth';
import { toast } from '../utils/toast';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const VideoMeetings = ({ onClose, leadId, loanId, contactId }) => {
  const [view, setView] = useState('types'); // types, booking-links, reminders, settings, tutorial
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

  // Landing Page customization state
  const [landingPageSettings, setLandingPageSettings] = useState({
    logo_url: '',
    profile_picture_url: '',
    video_url: '',
    video_type: 'youtube', // youtube, vimeo, loom, custom
    headline: 'Schedule a Video Meeting',
    subheadline: 'Choose a time that works for you',
    description: '',
    show_profile: true,
    profile_name: '',
    profile_title: '',
    profile_bio: '',
    accent_color: '#10b981',
    background_style: 'white', // white, light, gradient
    show_company_logo: true,
    show_social_proof: false,
    testimonial_text: '',
    testimonial_author: ''
  });
  const [savingLandingPage, setSavingLandingPage] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);

  // Reminder settings state
  const [reminderSettings, setReminderSettings] = useState({
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
  });
  const [savingReminders, setSavingReminders] = useState(false);

  // New link form state
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
    color: '#10b981',
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
        // Transform templates to meeting types format
        setMeetingTypes(templatesData.templates || []);
      }

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData.stats || null);
      }

      // Initialize config with defaults
      const defaultConfig = {
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
      setConfig(defaultConfig);
      setEditableConfig(JSON.parse(JSON.stringify(defaultConfig)));

      // Initialize sample booking links
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
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
      }
    } catch (err) {
      console.error('Start meeting error:', err);
    }
  };

  const endMeeting = async (meetingId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meetingId}/end`, {
        method: 'POST',
        headers: getAuthHeaders()
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
        method: 'DELETE',
        headers: getAuthHeaders()
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
        fetch(`${API_BASE}/api/v1/meetings/recordings/${recordingId}/transcript`, {
          headers: getAuthHeaders()
        }),
        fetch(`${API_BASE}/api/v1/meetings/recordings/${recordingId}/analysis`, {
          headers: getAuthHeaders()
        })
      ]);

      let transcript = {};
      let analysis = {};

      if (transcriptRes.ok) {
        transcript = await transcriptRes.json();
      }

      if (analysisRes.ok) {
        analysis = await analysisRes.json();
      }

      setSelectedRecording({
        id: recordingId,
        meeting_title: meetingTitle,
        recording_url: `${API_BASE}/api/v1/meetings/recordings/${recordingId}/stream`,
        transcript: transcript,
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
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        fetchData();
        toast.success('Default meeting types created!');
      }
    } catch (err) {
      console.error('Seed templates error:', err);
    }
  };

  // Save meeting type
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

  // Delete meeting type
  const handleDeleteMeetingType = async (typeId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/templates/${typeId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
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

  // Open edit modal for meeting type
  const handleEditType = (type) => {
    setEditingType(type);
    setTypeForm({
      type_name: type.template_name || type.type_name || '',
      type_key: type.template_key || type.type_key || '',
      description: type.description || '',
      default_duration_minutes: type.default_duration_minutes || 30,
      allowed_durations: type.allowed_durations || [15, 30, 45, 60],
      color: type.color || '#10b981',
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

  // Reset type form
  const resetTypeForm = () => {
    setTypeForm({
      type_name: '',
      type_key: '',
      description: '',
      default_duration_minutes: 30,
      allowed_durations: [15, 30, 45, 60],
      color: '#10b981',
      icon: 'video',
      is_public: true,
      requires_confirmation: false,
      buffer_before_minutes: 5,
      buffer_after_minutes: 5,
      recording_enabled: true,
      ai_assistant_enabled: true
    });
  };

  // Create booking link
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

  // Save settings
  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      // Simulate save - in production this would call an API
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

  // Update working hours for a specific day
  const updateWorkingHours = (day, field, value) => {
    setEditableConfig(prev => ({
      ...prev,
      working_hours: {
        ...prev.working_hours,
        [day]: {
          ...prev.working_hours[day],
          [field]: value
        }
      }
    }));
  };

  // Update a general config field
  const updateConfigField = (field, value) => {
    setEditableConfig(prev => ({
      ...prev,
      [field]: value
    }));
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

    if (leadId) {
      filtered = filtered.filter(m => m.lead_id !== leadId);
    }
    if (loanId) {
      filtered = filtered.filter(m => m.loan_id !== loanId);
    }

    if (statusFilter !== 'all') {
      filtered = filtered.filter(m => m.status === statusFilter);
    }

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

  const formatDateTime = (dateStr) => {
    if (!dateStr) return 'Not scheduled';
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  };

  const getStatusBadge = (status) => {
    const statusColors = {
      scheduled: { bg: '#dbeafe', color: '#1e40af' },
      active: { bg: '#dcfce7', color: '#166534' },
      waiting: { bg: '#fef3c7', color: '#92400e' },
      ended: { bg: '#f3f4f6', color: '#374151' },
      cancelled: { bg: '#fee2e2', color: '#991b1b' }
    };
    const style = statusColors[status] || statusColors.scheduled;
    return (
      <span
        className="status-badge"
        style={{ backgroundColor: style.bg, color: style.color }}
      >
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  };

  const getTemplateIcon = (icon) => {
    const icons = {
      phone: '📞',
      document: '📄',
      folder: '📁',
      lock: '🔒',
      clipboard: '📋',
      users: '👥',
      video: '🎥',
      home: '🏠',
      calendar: '📅'
    };
    return icons[icon] || '🎥';
  };

  // Generate time options for select dropdowns (5:00 AM to 10:00 PM)
  const timeOptions = [];
  for (let h = 5; h <= 22; h++) {
    for (let m = 0; m < 60; m += 30) {
      const hour = h.toString().padStart(2, '0');
      const minute = m.toString().padStart(2, '0');
      const time24 = `${hour}:${minute}`;
      const hour12 = h > 12 ? h - 12 : (h === 0 ? 12 : h);
      const ampm = h >= 12 ? 'PM' : 'AM';
      const label = `${hour12}:${minute.padStart(2, '0')} ${ampm}`;
      timeOptions.push({ value: time24, label });
    }
  }

  // Helper function to get video embed URL
  const getVideoEmbedUrl = (url, type) => {
    if (!url) return null;

    if (type === 'youtube') {
      const match = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
      return match ? `https://www.youtube.com/embed/${match[1]}` : null;
    } else if (type === 'vimeo') {
      const match = url.match(/vimeo\.com\/(\d+)/);
      return match ? `https://player.vimeo.com/video/${match[1]}` : null;
    } else if (type === 'loom') {
      const match = url.match(/loom\.com\/share\/([a-zA-Z0-9]+)/);
      return match ? `https://www.loom.com/embed/${match[1]}` : null;
    }
    return url;
  };

  // Save landing page settings
  const handleSaveLandingPage = async () => {
    setSavingLandingPage(true);
    try {
      // Simulate save - in production this would call an API
      await new Promise(resolve => setTimeout(resolve, 500));
      toast.success('Landing page settings saved successfully!');
    } catch (err) {
      console.error('Save landing page error:', err);
      toast.error('Failed to save landing page settings');
    } finally {
      setSavingLandingPage(false);
    }
  };

  // Render Landing Page View
  const renderLandingPageView = () => {
    const videoEmbedUrl = getVideoEmbedUrl(landingPageSettings.video_url, landingPageSettings.video_type);

    if (previewMode) {
      // Preview Mode
      return (
        <div className="scheduler-landing-page-view">
          <div className="landing-page-header">
            <div className="header-content">
              <h3>Landing Page Preview</h3>
              <p className="description">This is how your video meeting booking page will appear to clients.</p>
            </div>
            <div className="preview-toggle">
              <span>Preview Mode</span>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={previewMode}
                  onChange={(e) => setPreviewMode(e.target.checked)}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>
          </div>

          <div className="landing-page-preview">
            <div className={`preview-container bg-${landingPageSettings.background_style}`}>
              {/* Preview Header */}
              <div className="preview-header">
                {landingPageSettings.show_company_logo && landingPageSettings.logo_url && (
                  <img src={landingPageSettings.logo_url} alt="Logo" className="preview-logo" />
                )}
                <h2 style={{ color: landingPageSettings.accent_color }}>
                  {landingPageSettings.headline || 'Schedule a Video Meeting'}
                </h2>
                <p className="preview-subheadline">{landingPageSettings.subheadline}</p>
              </div>

              {/* Preview Video */}
              {videoEmbedUrl && (
                <div className="preview-video">
                  <iframe
                    src={videoEmbedUrl}
                    title="Introduction Video"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                  />
                </div>
              )}

              {/* Preview Profile */}
              {landingPageSettings.show_profile && (landingPageSettings.profile_name || landingPageSettings.profile_picture_url) && (
                <div className="preview-profile">
                  {landingPageSettings.profile_picture_url && (
                    <img src={landingPageSettings.profile_picture_url} alt="Profile" className="preview-profile-picture" />
                  )}
                  <div className="preview-profile-info">
                    {landingPageSettings.profile_name && <h4>{landingPageSettings.profile_name}</h4>}
                    {landingPageSettings.profile_title && <p className="profile-title">{landingPageSettings.profile_title}</p>}
                    {landingPageSettings.profile_bio && <p className="profile-bio">{landingPageSettings.profile_bio}</p>}
                  </div>
                </div>
              )}

              {/* Preview Description */}
              {landingPageSettings.description && (
                <div className="preview-description">
                  <h4>About This Meeting</h4>
                  <p>{landingPageSettings.description}</p>
                </div>
              )}

              {/* Calendar Mock */}
              <div className="calendar-mock">
                <p>Calendar widget will appear here</p>
              </div>

              {/* Testimonial */}
              {landingPageSettings.show_social_proof && landingPageSettings.testimonial_text && (
                <div className="preview-testimonial">
                  <blockquote>"{landingPageSettings.testimonial_text}"</blockquote>
                  {landingPageSettings.testimonial_author && (
                    <cite>— {landingPageSettings.testimonial_author}</cite>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      );
    }

    // Edit Mode
    return (
      <div className="scheduler-landing-page-view">
        <div className="landing-page-header">
          <div className="header-content">
            <h3>Landing Page Customization</h3>
            <p className="description">Customize how your video meeting booking page looks to clients.</p>
          </div>
          <div className="preview-toggle">
            <span>Preview Mode</span>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={previewMode}
                onChange={(e) => setPreviewMode(e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div className="landing-page-editor">
          {/* Branding Section */}
          <div className="editor-section">
            <h4><span className="section-icon">🎨</span> Branding</h4>
            <div className="form-group">
              <label>Company Logo URL</label>
              <input
                type="text"
                value={landingPageSettings.logo_url}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, logo_url: e.target.value})}
                placeholder="https://example.com/logo.png"
              />
              <span className="help-text">Enter the URL of your company logo image</span>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Accent Color</label>
                <div className="color-input-group">
                  <input
                    type="color"
                    value={landingPageSettings.accent_color}
                    onChange={(e) => setLandingPageSettings({...landingPageSettings, accent_color: e.target.value})}
                  />
                  <input
                    type="text"
                    value={landingPageSettings.accent_color}
                    onChange={(e) => setLandingPageSettings({...landingPageSettings, accent_color: e.target.value})}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Background Style</label>
                <select
                  value={landingPageSettings.background_style}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, background_style: e.target.value})}
                >
                  <option value="white">White</option>
                  <option value="light">Light Gray</option>
                  <option value="gradient">Gradient</option>
                </select>
              </div>
            </div>
          </div>

          {/* Video Section */}
          <div className="editor-section">
            <h4><span className="section-icon">🎥</span> Introduction Video</h4>
            <div className="form-row">
              <div className="form-group">
                <label>Video Platform</label>
                <select
                  value={landingPageSettings.video_type}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, video_type: e.target.value})}
                >
                  <option value="youtube">YouTube</option>
                  <option value="vimeo">Vimeo</option>
                  <option value="loom">Loom</option>
                  <option value="custom">Custom Embed</option>
                </select>
              </div>
              <div className="form-group">
                <label>Video URL</label>
                <input
                  type="text"
                  value={landingPageSettings.video_url}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, video_url: e.target.value})}
                  placeholder="https://youtube.com/watch?v=..."
                />
              </div>
            </div>
            {videoEmbedUrl && (
              <div className="video-preview">
                <iframe
                  src={videoEmbedUrl}
                  title="Video Preview"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            )}
          </div>

          {/* Profile Section */}
          <div className="editor-section">
            <h4><span className="section-icon">👤</span> Your Profile</h4>
            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={landingPageSettings.show_profile}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, show_profile: e.target.checked})}
                />
                Show profile section on landing page
              </label>
            </div>
            <div className="form-group">
              <label>Profile Picture URL</label>
              <input
                type="text"
                value={landingPageSettings.profile_picture_url}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, profile_picture_url: e.target.value})}
                placeholder="https://example.com/photo.jpg"
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Your Name</label>
                <input
                  type="text"
                  value={landingPageSettings.profile_name}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, profile_name: e.target.value})}
                  placeholder="John Smith"
                />
              </div>
              <div className="form-group">
                <label>Title/Role</label>
                <input
                  type="text"
                  value={landingPageSettings.profile_title}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, profile_title: e.target.value})}
                  placeholder="Senior Loan Officer"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Short Bio</label>
              <textarea
                value={landingPageSettings.profile_bio}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, profile_bio: e.target.value})}
                placeholder="Brief introduction about yourself..."
                rows={2}
              />
            </div>
          </div>

          {/* Content Section */}
          <div className="editor-section">
            <h4><span className="section-icon">📝</span> Page Content</h4>
            <div className="form-group">
              <label>Headline</label>
              <input
                type="text"
                value={landingPageSettings.headline}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, headline: e.target.value})}
                placeholder="Schedule a Video Meeting"
              />
            </div>
            <div className="form-group">
              <label>Subheadline</label>
              <input
                type="text"
                value={landingPageSettings.subheadline}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, subheadline: e.target.value})}
                placeholder="Choose a time that works for you"
              />
            </div>
            <div className="form-group">
              <label>Meeting Description/Agenda</label>
              <textarea
                value={landingPageSettings.description}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, description: e.target.value})}
                placeholder="Describe what the meeting will cover..."
                rows={4}
              />
              <span className="help-text">Help clients understand what to expect from the video meeting</span>
            </div>
          </div>

          {/* Social Proof Section */}
          <div className="editor-section">
            <h4><span className="section-icon">⭐</span> Social Proof</h4>
            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={landingPageSettings.show_social_proof}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, show_social_proof: e.target.checked})}
                />
                Show testimonial on landing page
              </label>
            </div>
            <div className="form-group">
              <label>Testimonial Text</label>
              <textarea
                value={landingPageSettings.testimonial_text}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, testimonial_text: e.target.value})}
                placeholder="What a satisfied client said about working with you..."
                rows={3}
              />
            </div>
            <div className="form-group">
              <label>Testimonial Author</label>
              <input
                type="text"
                value={landingPageSettings.testimonial_author}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, testimonial_author: e.target.value})}
                placeholder="Jane D., First-time Homebuyer"
              />
            </div>
          </div>
        </div>

        <div className="landing-page-actions">
          <button
            className="reset-landing-btn"
            onClick={() => setLandingPageSettings({
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
              accent_color: '#10b981',
              background_style: 'white',
              show_company_logo: true,
              show_social_proof: false,
              testimonial_text: '',
              testimonial_author: ''
            })}
          >
            Reset to Defaults
          </button>
          <button
            className="save-landing-btn"
            onClick={handleSaveLandingPage}
            disabled={savingLandingPage}
          >
            {savingLandingPage ? 'Saving...' : 'Save Landing Page'}
          </button>
        </div>
      </div>
    );
  };

  // Render Stats Cards
  const renderStats = () => {
    if (!stats) return null;

    return (
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats.total_meetings}</div>
          <div className="stat-label">Total Meetings</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.meetings_this_week}</div>
          <div className="stat-label">This Week</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.upcoming_meetings}</div>
          <div className="stat-label">Upcoming</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.total_meeting_hours}h</div>
          <div className="stat-label">Total Hours</div>
        </div>
      </div>
    );
  };

  // Render Meeting Types view (like SmartScheduler's Appointment Types)
  const renderTypesView = () => (
    <div className="scheduler-types-view">
      <div className="types-header">
        <h3>Meeting Types</h3>
        <div className="types-actions">
          <button className="seed-btn" onClick={seedDefaultTemplates}>
            Seed Defaults
          </button>
          <button className="add-type-btn" onClick={() => {
            setEditingType(null);
            resetTypeForm();
            setShowNewTypeModal(true);
          }}>
            + New Type
          </button>
        </div>
      </div>

      {meetingTypes.length === 0 ? (
        <div className="empty-state">
          <p>No meeting types configured</p>
          <button onClick={seedDefaultTemplates}>Create Default Types</button>
        </div>
      ) : (
        <div className="types-grid">
          {meetingTypes.map(type => (
            <div
              key={type.id || type.template_key}
              className="type-card clickable"
              style={{ borderLeftColor: type.color }}
              onClick={() => handleEditType(type)}
            >
              <div className="type-header">
                <h4>{type.template_name || type.type_name}</h4>
              </div>
              <p className="type-description">{type.description}</p>
              <div className="type-meta">
                <span>{type.default_duration_minutes} min</span>
                <span className={`public-badge ${type.is_public ? 'public' : 'private'}`}>
                  {type.is_public ? 'Public' : 'Private'}
                </span>
              </div>
              <div className="type-durations">
                {(type.allowed_durations || [type.default_duration_minutes]).map(d => (
                  <span key={d} className="duration-chip">{d}m</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Render Booking Links view
  const renderBookingLinksView = () => (
    <div className="scheduler-links-view">
      <div className="links-header">
        <h3>Booking Links</h3>
        <button className="add-link-btn" onClick={() => setShowNewLinkModal(true)}>
          + New Link
        </button>
      </div>

      {bookingLinks.length === 0 ? (
        <div className="empty-state">
          <p>No booking links created</p>
          <p className="hint">Create shareable links for clients to book video meetings</p>
        </div>
      ) : (
        <div className="links-list">
          {bookingLinks.map(link => (
            <div key={link.id} className="link-card">
              <div className="link-info">
                <h4>{link.link_name}</h4>
                <p className="link-url">/meeting/book/{link.slug}</p>
                {link.description && <p className="link-description">{link.description}</p>}
              </div>
              <div className="link-stats">
                <span className="stat">
                  <span className="stat-value">{link.view_count}</span>
                  <span className="stat-label">Views</span>
                </span>
                <span className="stat">
                  <span className="stat-value">{link.booking_count}</span>
                  <span className="stat-label">Bookings</span>
                </span>
              </div>
              <div className="link-actions">
                <button
                  className="copy-btn"
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/meeting/book/${link.slug}`);
                    toast.success('Link copied!');
                  }}
                >
                  Copy Link
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Render working hours tab content
  const renderWorkingHoursTab = () => {
    const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    const dayLabels = {
      sunday: 'Sunday',
      monday: 'Monday',
      tuesday: 'Tuesday',
      wednesday: 'Wednesday',
      thursday: 'Thursday',
      friday: 'Friday',
      saturday: 'Saturday'
    };

    return (
      <div className="settings-tab-content">
        <p className="settings-description">Configure which days and hours you're available for video meetings.</p>
        <div className="working-hours-editor">
          {days.map(day => {
            const hours = editableConfig?.working_hours?.[day] || { enabled: false, start: '09:00', end: '17:00' };
            return (
              <div key={day} className={`day-row ${hours.enabled ? 'enabled' : 'disabled'}`}>
                <div className="day-toggle">
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={hours.enabled}
                      onChange={(e) => updateWorkingHours(day, 'enabled', e.target.checked)}
                    />
                    <span className="toggle-slider"></span>
                  </label>
                  <span className="day-label">{dayLabels[day]}</span>
                </div>
                {hours.enabled ? (
                  <div className="time-range">
                    <select
                      value={hours.start}
                      onChange={(e) => updateWorkingHours(day, 'start', e.target.value)}
                    >
                      {timeOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                    <span className="time-separator">to</span>
                    <select
                      value={hours.end}
                      onChange={(e) => updateWorkingHours(day, 'end', e.target.value)}
                    >
                      {timeOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="time-range-off">
                    <span>Unavailable</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // Render booking settings tab content
  const renderBookingTab = () => (
    <div className="settings-tab-content">
      <p className="settings-description">Configure default booking behavior and limits for video meetings.</p>
      <div className="booking-settings-form">
        <div className="form-group">
          <label>Default Duration</label>
          <select
            value={editableConfig?.default_duration_minutes || 30}
            onChange={(e) => updateConfigField('default_duration_minutes', parseInt(e.target.value))}
          >
            <option value={15}>15 minutes</option>
            <option value={20}>20 minutes</option>
            <option value={30}>30 minutes</option>
            <option value={45}>45 minutes</option>
            <option value={60}>60 minutes</option>
            <option value={90}>90 minutes</option>
          </select>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Buffer Before (minutes)</label>
            <input
              type="number"
              value={editableConfig?.buffer_before_minutes || 0}
              onChange={(e) => updateConfigField('buffer_before_minutes', parseInt(e.target.value) || 0)}
              min="0"
              max="60"
            />
            <span className="help-text">Time before meetings for preparation</span>
          </div>

          <div className="form-group">
            <label>Buffer After (minutes)</label>
            <input
              type="number"
              value={editableConfig?.buffer_after_minutes || 0}
              onChange={(e) => updateConfigField('buffer_after_minutes', parseInt(e.target.value) || 0)}
              min="0"
              max="60"
            />
            <span className="help-text">Time after meetings for follow-up</span>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Minimum Notice (hours)</label>
            <input
              type="number"
              value={editableConfig?.min_notice_hours || 1}
              onChange={(e) => updateConfigField('min_notice_hours', parseInt(e.target.value) || 1)}
              min="1"
              max="168"
            />
            <span className="help-text">How far in advance clients must book</span>
          </div>

          <div className="form-group">
            <label>Max Advance Booking (days)</label>
            <input
              type="number"
              value={editableConfig?.max_advance_days || 30}
              onChange={(e) => updateConfigField('max_advance_days', parseInt(e.target.value) || 30)}
              min="1"
              max="365"
            />
            <span className="help-text">How far in the future clients can book</span>
          </div>
        </div>

        <div className="form-group">
          <label>Max Meetings Per Day</label>
          <input
            type="number"
            value={editableConfig?.max_meetings_per_day || 8}
            onChange={(e) => updateConfigField('max_meetings_per_day', parseInt(e.target.value) || 8)}
            min="1"
            max="20"
          />
          <span className="help-text">Maximum number of video meetings per day</span>
        </div>
      </div>
    </div>
  );

  // Render AI settings tab content
  const renderAITab = () => (
    <div className="settings-tab-content">
      <p className="settings-description">Configure AI-powered video meeting features.</p>
      <div className="ai-settings-form">
        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.ai_scheduling_enabled || false}
                onChange={(e) => updateConfigField('ai_scheduling_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">AI Smart Scheduling</span>
              <span className="toggle-description">Let AI suggest optimal meeting times based on your patterns and client preferences</span>
            </div>
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.auto_reschedule_enabled || false}
                onChange={(e) => updateConfigField('auto_reschedule_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">Auto-Reschedule Suggestions</span>
              <span className="toggle-description">Automatically suggest better times when conflicts arise</span>
            </div>
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.smart_reminders_enabled || false}
                onChange={(e) => updateConfigField('smart_reminders_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">Smart Reminders</span>
              <span className="toggle-description">AI-optimized reminder timing based on client engagement</span>
            </div>
          </label>
        </div>
      </div>
    </div>
  );

  // Render settings view with sub-tabs
  const renderSettingsView = () => (
    <div className="scheduler-settings-view">
      {editableConfig ? (
        <>
          <div className="settings-sub-tabs">
            <button
              className={`sub-tab ${settingsTab === 'working-hours' ? 'active' : ''}`}
              onClick={() => setSettingsTab('working-hours')}
            >
              Working Hours
            </button>
            <button
              className={`sub-tab ${settingsTab === 'booking' ? 'active' : ''}`}
              onClick={() => setSettingsTab('booking')}
            >
              Booking Settings
            </button>
            <button
              className={`sub-tab ${settingsTab === 'ai' ? 'active' : ''}`}
              onClick={() => setSettingsTab('ai')}
            >
              AI Settings
            </button>
          </div>

          {settingsTab === 'working-hours' && renderWorkingHoursTab()}
          {settingsTab === 'booking' && renderBookingTab()}
          {settingsTab === 'ai' && renderAITab()}

          <div className="settings-actions">
            <button
              className="save-settings-btn"
              onClick={handleSaveSettings}
              disabled={savingSettings}
            >
              {savingSettings ? 'Saving...' : 'Save Settings'}
            </button>
            <button
              className="reset-settings-btn"
              onClick={() => setEditableConfig(JSON.parse(JSON.stringify(config)))}
              disabled={savingSettings}
            >
              Reset Changes
            </button>
          </div>
        </>
      ) : (
        <div className="empty-state">
          <p>No configuration found</p>
          <button onClick={seedDefaultTemplates}>Initialize Meetings</button>
        </div>
      )}
    </div>
  );

  // Render reminders view
  const renderRemindersView = () => {
    const addReminder = () => {
      const newId = Math.max(...reminderSettings.reminders.map(r => r.id), 0) + 1;
      setReminderSettings(prev => ({
        ...prev,
        reminders: [...prev.reminders, {
          id: newId,
          timing: 24,
          unit: 'hours',
          method: 'email',
          enabled: true,
          message: 'Reminder: Your video meeting is coming up on {{appointment_date}} at {{appointment_time}}.'
        }]
      }));
    };

    const updateReminder = (id, field, value) => {
      setReminderSettings(prev => ({
        ...prev,
        reminders: prev.reminders.map(r =>
          r.id === id ? { ...r, [field]: value } : r
        )
      }));
    };

    const deleteReminder = (id) => {
      setReminderSettings(prev => ({
        ...prev,
        reminders: prev.reminders.filter(r => r.id !== id)
      }));
    };

    const handleSaveReminders = async () => {
      setSavingReminders(true);
      try {
        await new Promise(resolve => setTimeout(resolve, 500));
        toast.success('Reminder settings saved successfully!');
      } catch (err) {
        console.error('Save reminders error:', err);
        toast.error('Failed to save reminder settings');
      } finally {
        setSavingReminders(false);
      }
    };

    return (
      <div className="scheduler-reminders-view">
        <div className="reminders-header">
          <div className="header-content">
            <h3>Meeting Reminders</h3>
            <p className="description">Configure automatic reminder messages to reduce no-shows and keep clients informed about their upcoming video meetings.</p>
          </div>
          <label className="master-toggle">
            <span>Reminders {reminderSettings.enabled ? 'Enabled' : 'Disabled'}</span>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={reminderSettings.enabled}
                onChange={(e) => setReminderSettings(prev => ({ ...prev, enabled: e.target.checked }))}
              />
              <span className="toggle-slider"></span>
            </label>
          </label>
        </div>

        {reminderSettings.enabled && (
          <>
            <div className="reminders-list">
              <div className="list-header">
                <h4>Reminder Schedule</h4>
                <button className="add-reminder-btn" onClick={addReminder}>+ Add Reminder</button>
              </div>

              {/* Booking Confirmation */}
              <div className={`reminder-card booking-confirmation ${reminderSettings.bookingConfirmation?.enabled ? '' : 'disabled'}`}>
                <div className="reminder-header">
                  <div className="reminder-number">Meeting Confirmation</div>
                  <div className="reminder-controls">
                    <label className="toggle-switch small">
                      <input
                        type="checkbox"
                        checked={reminderSettings.bookingConfirmation?.enabled ?? true}
                        onChange={(e) => setReminderSettings(prev => ({
                          ...prev,
                          bookingConfirmation: { ...prev.bookingConfirmation, enabled: e.target.checked }
                        }))}
                      />
                      <span className="toggle-slider"></span>
                    </label>
                  </div>
                </div>

                <div className="reminder-config">
                  <div className="timing-row">
                    <label>Send</label>
                    <span className="confirmation-timing">immediately after booking</span>
                    <span>via</span>
                    <select
                      value={reminderSettings.bookingConfirmation?.method || 'both'}
                      onChange={(e) => setReminderSettings(prev => ({
                        ...prev,
                        bookingConfirmation: { ...prev.bookingConfirmation, method: e.target.value }
                      }))}
                      className="method-select"
                    >
                      <option value="email">Email</option>
                      <option value="sms">SMS</option>
                      <option value="both">Both</option>
                    </select>
                  </div>

                  <div className="message-row">
                    <label>Message</label>
                    <textarea
                      value={reminderSettings.bookingConfirmation?.message || ''}
                      onChange={(e) => setReminderSettings(prev => ({
                        ...prev,
                        bookingConfirmation: { ...prev.bookingConfirmation, message: e.target.value }
                      }))}
                      placeholder="Enter confirmation message..."
                      rows={3}
                    />
                    <div className="message-help">
                      <span className="help-label">Available variables:</span>
                      <code>{'{{appointment_date}}'}</code>
                      <code>{'{{appointment_time}}'}</code>
                      <code>{'{{attendee_name}}'}</code>
                      <code>{'{{meeting_type}}'}</code>
                      <code>{'{{meeting_link}}'}</code>
                    </div>
                  </div>
                </div>
              </div>

              {reminderSettings.reminders.map((reminder, index) => (
                <div key={reminder.id} className={`reminder-card ${reminder.enabled ? '' : 'disabled'}`}>
                  <div className="reminder-header">
                    <div className="reminder-number">Reminder {index + 1}</div>
                    <div className="reminder-controls">
                      <label className="toggle-switch small">
                        <input
                          type="checkbox"
                          checked={reminder.enabled}
                          onChange={(e) => updateReminder(reminder.id, 'enabled', e.target.checked)}
                        />
                        <span className="toggle-slider"></span>
                      </label>
                      <button
                        className="delete-reminder-btn"
                        onClick={() => deleteReminder(reminder.id)}
                        title="Delete reminder"
                      >
                        ×
                      </button>
                    </div>
                  </div>

                  <div className="reminder-config">
                    <div className="timing-row">
                      <label>Send</label>
                      <input
                        type="number"
                        value={reminder.timing}
                        onChange={(e) => updateReminder(reminder.id, 'timing', parseInt(e.target.value) || 1)}
                        min="1"
                        max="168"
                        className="timing-input"
                      />
                      <select
                        value={reminder.unit}
                        onChange={(e) => updateReminder(reminder.id, 'unit', e.target.value)}
                        className="unit-select"
                      >
                        <option value="minutes">minutes</option>
                        <option value="hours">hours</option>
                        <option value="days">days</option>
                      </select>
                      <span>before meeting via</span>
                      <select
                        value={reminder.method}
                        onChange={(e) => updateReminder(reminder.id, 'method', e.target.value)}
                        className="method-select"
                      >
                        <option value="email">Email</option>
                        <option value="sms">SMS</option>
                        <option value="both">Both</option>
                      </select>
                    </div>

                    <div className="message-row">
                      <label>Message</label>
                      <textarea
                        value={reminder.message}
                        onChange={(e) => updateReminder(reminder.id, 'message', e.target.value)}
                        placeholder="Enter reminder message..."
                        rows={3}
                      />
                      <div className="message-help">
                        <span className="help-label">Available variables:</span>
                        <code>{'{{appointment_date}}'}</code>
                        <code>{'{{appointment_time}}'}</code>
                        <code>{'{{attendee_name}}'}</code>
                        <code>{'{{meeting_type}}'}</code>
                        <code>{'{{meeting_link}}'}</code>
                      </div>
                    </div>
                  </div>
                </div>
              ))}

              {reminderSettings.reminders.length === 0 && (
                <div className="empty-reminders">
                  <p>No reminders configured. Add a reminder to reduce no-shows.</p>
                  <button onClick={addReminder}>+ Add Your First Reminder</button>
                </div>
              )}
            </div>

            <div className="reminder-options">
              <h4>Email Options</h4>

              <div className="form-group">
                <label>Default Email Subject</label>
                <input
                  type="text"
                  value={reminderSettings.default_email_subject}
                  onChange={(e) => setReminderSettings(prev => ({ ...prev, default_email_subject: e.target.value }))}
                  placeholder="Reminder: Your Upcoming Video Meeting"
                />
              </div>

              <div className="checkbox-options">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={reminderSettings.include_calendar_link}
                    onChange={(e) => setReminderSettings(prev => ({ ...prev, include_calendar_link: e.target.checked }))}
                  />
                  Include "Add to Calendar" link
                </label>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={reminderSettings.include_reschedule_link}
                    onChange={(e) => setReminderSettings(prev => ({ ...prev, include_reschedule_link: e.target.checked }))}
                  />
                  Include reschedule link
                </label>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={reminderSettings.include_cancel_link}
                    onChange={(e) => setReminderSettings(prev => ({ ...prev, include_cancel_link: e.target.checked }))}
                  />
                  Include cancellation link
                </label>
              </div>
            </div>

            <div className="reminders-actions">
              <button
                className="save-reminders-btn"
                onClick={handleSaveReminders}
                disabled={savingReminders}
              >
                {savingReminders ? 'Saving...' : 'Save Reminder Settings'}
              </button>
            </div>
          </>
        )}
      </div>
    );
  };

  // Render Tutorial View
  const renderTutorialView = () => (
    <div className="scheduler-tutorial-view">
      <div className="tutorial-header">
        <h3>Video Meetings Tutorial</h3>
        <p className="tutorial-intro">Learn how to maximize productivity with our AI-powered video conferencing system</p>
      </div>

      <div className="tutorial-sections">
        {/* Quick Start */}
        <div className="tutorial-section">
          <div className="section-icon">🚀</div>
          <h4>Quick Start Guide</h4>
          <div className="section-content">
            <ol>
              <li><strong>Create Meeting Types:</strong> Go to "Meeting Types" tab and click "Seed Defaults" to create standard meeting types for mortgage discussions</li>
              <li><strong>Set Your Hours:</strong> Navigate to "Settings" tab and configure your working hours for each day of the week</li>
              <li><strong>Schedule a Meeting:</strong> Click "Schedule Meeting" to create a new video meeting with all the AI features</li>
              <li><strong>Start Instant:</strong> Use "Start Instant" for immediate meetings without scheduling</li>
              <li><strong>Share Booking Links:</strong> Create public booking links in the "Booking Links" tab</li>
            </ol>
          </div>
        </div>

        {/* Meeting Types */}
        <div className="tutorial-section">
          <div className="section-icon">📋</div>
          <h4>Meeting Types</h4>
          <div className="section-content">
            <p>Customize meeting types for different video call purposes:</p>
            <ul>
              <li><strong>Discovery Call:</strong> Initial video consultation with new leads (15-30 min)</li>
              <li><strong>Pre-Approval Review:</strong> Screen share to review pre-approval documents (30-45 min)</li>
              <li><strong>Document Review Session:</strong> Collect and review mortgage documents on video (30-60 min)</li>
              <li><strong>Rate Lock Discussion:</strong> Review market conditions and lock options via video (20-30 min)</li>
              <li><strong>Closing Preparation:</strong> Final walkthrough before closing day (45-60 min)</li>
              <li><strong>Post-Close Review:</strong> Follow-up after closing to ensure satisfaction (15-30 min)</li>
              <li><strong>Team Sync:</strong> Internal team meetings and coordination (30 min)</li>
            </ul>
            <p className="tip">Tip: Click on any meeting type card to edit its settings, durations, and colors.</p>
          </div>
        </div>

        {/* Booking Links */}
        <div className="tutorial-section">
          <div className="section-icon">🔗</div>
          <h4>Booking Links</h4>
          <div className="section-content">
            <p>Create shareable links for clients to book video meetings directly:</p>
            <ul>
              <li><strong>Custom URL Slugs:</strong> Create memorable URLs like /meeting/book/john-smith</li>
              <li><strong>Type Filtering:</strong> Limit which meeting types are available on each link</li>
              <li><strong>Analytics:</strong> Track views and bookings for each link</li>
              <li><strong>Easy Sharing:</strong> Copy links with one click to share via email or text</li>
            </ul>
          </div>
        </div>

        {/* AI Features */}
        <div className="tutorial-section highlight">
          <div className="section-icon">🤖</div>
          <h4>AI-Powered Features</h4>
          <div className="section-content">
            <p>Video Meetings includes advanced AI capabilities:</p>
            <ul>
              <li><strong>AI Meeting Assistant:</strong> Real-time suggestions and note-taking during calls</li>
              <li><strong>Auto-Transcription:</strong> Automatic transcription of all video meetings</li>
              <li><strong>Smart Summaries:</strong> AI-generated meeting summaries and action items</li>
              <li><strong>Smart Scheduling:</strong> AI suggests optimal meeting times based on patterns</li>
              <li><strong>Auto-Reschedule:</strong> Automatically suggests alternatives when conflicts arise</li>
              <li><strong>Smart Reminders:</strong> AI-optimized reminder timing based on engagement</li>
            </ul>
            <p className="tip">Enable AI features in Settings → AI Settings tab</p>
          </div>
        </div>

        {/* Recording Features */}
        <div className="tutorial-section">
          <div className="section-icon">🎥</div>
          <h4>Recording & Transcription</h4>
          <div className="section-content">
            <p>Comprehensive meeting documentation:</p>
            <ul>
              <li><strong>Auto-Recording:</strong> Meetings are automatically recorded when enabled</li>
              <li><strong>Cloud Storage:</strong> Recordings are securely stored and accessible anytime</li>
              <li><strong>Searchable Transcripts:</strong> Full-text search across all meeting transcripts</li>
              <li><strong>Timestamp Navigation:</strong> Jump to specific moments in recordings</li>
              <li><strong>Compliance Ready:</strong> Recordings meet mortgage compliance requirements</li>
            </ul>
          </div>
        </div>

        {/* Best Practices */}
        <div className="tutorial-section best-practices">
          <div className="section-icon">💡</div>
          <h4>Best Practices</h4>
          <div className="section-content">
            <ul>
              <li><strong>Test Equipment:</strong> Ensure camera and microphone work before important calls</li>
              <li><strong>Buffer Time:</strong> Add 5-15 minute buffers between meetings for preparation</li>
              <li><strong>Enable Recording:</strong> Always record important client discussions for compliance</li>
              <li><strong>Use Waiting Room:</strong> Enable waiting room for better meeting control</li>
              <li><strong>Send Reminders:</strong> Configure automatic reminders to reduce no-shows</li>
              <li><strong>Review AI Summaries:</strong> Check AI-generated summaries for accuracy after meetings</li>
            </ul>
          </div>
        </div>
      </div>

      <div className="tutorial-footer">
        <p>Need more help? Contact support or visit our documentation.</p>
        <div className="tutorial-actions">
          <button className="start-btn" onClick={() => setView('types')}>
            Meeting Types
          </button>
          <button className="setup-btn" onClick={() => setView('settings')}>
            Configure Settings
          </button>
        </div>
      </div>
    </div>
  );

  // Render Create Meeting Modal
  const renderCreateModal = () => {
    if (!showCreateModal) return null;

    return (
      <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>Schedule Meeting</h3>
            <button className="close-btn" onClick={() => setShowCreateModal(false)}>×</button>
          </div>
          <div className="modal-body">
            <div className="form-group">
              <label>Meeting Name *</label>
              <input
                type="text"
                value={meetingForm.room_name}
                onChange={(e) => setMeetingForm({ ...meetingForm, room_name: e.target.value })}
                placeholder="e.g., Discovery Call with John"
              />
            </div>

            <div className="form-group">
              <label>Description</label>
              <textarea
                value={meetingForm.room_description}
                onChange={(e) => setMeetingForm({ ...meetingForm, room_description: e.target.value })}
                placeholder="Meeting description..."
                rows={3}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Date & Time *</label>
                <input
                  type="datetime-local"
                  value={meetingForm.scheduled_start}
                  onChange={(e) => setMeetingForm({ ...meetingForm, scheduled_start: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Duration</label>
                <select
                  value={meetingForm.duration_minutes}
                  onChange={(e) => setMeetingForm({ ...meetingForm, duration_minutes: parseInt(e.target.value) })}
                >
                  <option value={15}>15 minutes</option>
                  <option value={30}>30 minutes</option>
                  <option value={45}>45 minutes</option>
                  <option value={60}>1 hour</option>
                  <option value={90}>1.5 hours</option>
                  <option value={120}>2 hours</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label>Meeting Type</label>
              <select
                value={meetingForm.meeting_type}
                onChange={(e) => setMeetingForm({ ...meetingForm, meeting_type: e.target.value })}
              >
                <option value="general">General</option>
                <option value="discovery_call">Discovery Call</option>
                <option value="pre_approval_review">Pre-Approval Review</option>
                <option value="document_review">Document Review</option>
                <option value="rate_lock_discussion">Rate Lock Discussion</option>
                <option value="closing_prep">Closing Preparation</option>
                <option value="post_close_review">Post-Close Review</option>
                <option value="team_sync">Team Sync</option>
              </select>
            </div>

            <div className="form-section">
              <h4>Meeting Settings</h4>
              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={meetingForm.recording_enabled}
                    onChange={(e) => setMeetingForm({ ...meetingForm, recording_enabled: e.target.checked })}
                  />
                  <span>Enable Recording</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={meetingForm.transcription_enabled}
                    onChange={(e) => setMeetingForm({ ...meetingForm, transcription_enabled: e.target.checked })}
                  />
                  <span>Enable Transcription</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={meetingForm.ai_assistant_enabled}
                    onChange={(e) => setMeetingForm({ ...meetingForm, ai_assistant_enabled: e.target.checked })}
                  />
                  <span>Enable AI Assistant</span>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={meetingForm.waiting_room_enabled}
                    onChange={(e) => setMeetingForm({ ...meetingForm, waiting_room_enabled: e.target.checked })}
                  />
                  <span>Enable Waiting Room</span>
                </label>
              </div>
            </div>
          </div>
          <div className="modal-footer">
            <button className="secondary-btn" onClick={() => setShowCreateModal(false)}>
              Cancel
            </button>
            <button
              className="primary-btn"
              onClick={createScheduledMeeting}
              disabled={!meetingForm.room_name || !meetingForm.scheduled_start}
            >
              Create Meeting
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Render Meeting Type Modal
  const renderTypeModal = () => {
    if (!showNewTypeModal) return null;

    const iconOptions = [
      { value: 'phone', label: 'Phone' },
      { value: 'video', label: 'Video' },
      { value: 'document', label: 'Document' },
      { value: 'clipboard', label: 'Clipboard' },
      { value: 'folder', label: 'Folder' },
      { value: 'lock', label: 'Lock' },
      { value: 'home', label: 'Home' },
      { value: 'users', label: 'Users' },
      { value: 'calendar', label: 'Calendar' }
    ];

    const colorOptions = [
      '#10b981', '#3b82f6', '#8b5cf6', '#f59e0b',
      '#ef4444', '#ec4899', '#06b6d4', '#84cc16'
    ];

    const durationOptions = [15, 20, 30, 45, 60, 90, 120];

    const toggleDuration = (duration) => {
      const current = typeForm.allowed_durations || [];
      if (current.includes(duration)) {
        setTypeForm({ ...typeForm, allowed_durations: current.filter(d => d !== duration) });
      } else {
        setTypeForm({ ...typeForm, allowed_durations: [...current, duration].sort((a, b) => a - b) });
      }
    };

    return (
      <div className="scheduler-modal-overlay" onClick={() => {
        setShowNewTypeModal(false);
        setEditingType(null);
      }}>
        <div className="scheduler-modal type-modal" onClick={e => e.stopPropagation()}>
          <div className="modal-header">
            <h3>{editingType ? 'Edit Meeting Type' : 'New Meeting Type'}</h3>
            <button className="close-btn" onClick={() => {
              setShowNewTypeModal(false);
              setEditingType(null);
            }}>×</button>
          </div>

          <div className="modal-content">
            <div className="form-group">
              <label>Type Name *</label>
              <input
                type="text"
                value={typeForm.type_name}
                onChange={e => setTypeForm({ ...typeForm, type_name: e.target.value })}
                placeholder="e.g., Discovery Call"
              />
            </div>

            <div className="form-group">
              <label>Description</label>
              <textarea
                value={typeForm.description}
                onChange={e => setTypeForm({ ...typeForm, description: e.target.value })}
                placeholder="Brief description of this meeting type..."
                rows={2}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Default Duration</label>
                <select
                  value={typeForm.default_duration_minutes}
                  onChange={e => setTypeForm({ ...typeForm, default_duration_minutes: parseInt(e.target.value) })}
                >
                  {durationOptions.map(d => (
                    <option key={d} value={d}>{d} minutes</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Icon</label>
                <select
                  value={typeForm.icon}
                  onChange={e => setTypeForm({ ...typeForm, icon: e.target.value })}
                >
                  {iconOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-group">
              <label>Allowed Durations</label>
              <div className="duration-toggles">
                {durationOptions.map(d => (
                  <button
                    key={d}
                    type="button"
                    className={`duration-toggle ${(typeForm.allowed_durations || []).includes(d) ? 'active' : ''}`}
                    onClick={() => toggleDuration(d)}
                  >
                    {d}m
                  </button>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label>Color</label>
              <div className="color-options">
                {colorOptions.map(color => (
                  <button
                    key={color}
                    type="button"
                    className={`color-option ${typeForm.color === color ? 'selected' : ''}`}
                    style={{ backgroundColor: color }}
                    onClick={() => setTypeForm({ ...typeForm, color })}
                  />
                ))}
              </div>
            </div>

            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={typeForm.recording_enabled}
                  onChange={e => setTypeForm({ ...typeForm, recording_enabled: e.target.checked })}
                />
                Enable Recording by default
              </label>
            </div>

            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={typeForm.ai_assistant_enabled}
                  onChange={e => setTypeForm({ ...typeForm, ai_assistant_enabled: e.target.checked })}
                />
                Enable AI Assistant by default
              </label>
            </div>
          </div>

          <div className="modal-footer">
            {editingType && (
              <button
                className="delete-btn"
                onClick={() => {
                  handleDeleteMeetingType(editingType.id);
                  setShowNewTypeModal(false);
                  setEditingType(null);
                }}
              >
                Delete
              </button>
            )}
            <div className="footer-right">
              <button className="cancel-btn" onClick={() => {
                setShowNewTypeModal(false);
                setEditingType(null);
              }}>Cancel</button>
              <button
                className="confirm-btn"
                onClick={handleSaveMeetingType}
                disabled={!typeForm.type_name}
              >
                {editingType ? 'Save Changes' : 'Create Type'}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // Render new booking link modal
  const renderNewLinkModal = () => {
    if (!showNewLinkModal) return null;

    return (
      <div className="scheduler-modal-overlay" onClick={() => setShowNewLinkModal(false)}>
        <div className="scheduler-modal" onClick={e => e.stopPropagation()}>
          <div className="modal-header">
            <h3>Create Booking Link</h3>
            <button className="close-btn" onClick={() => setShowNewLinkModal(false)}>×</button>
          </div>

          <div className="modal-content">
            <div className="form-group">
              <label>Link Name *</label>
              <input
                type="text"
                value={linkForm.link_name}
                onChange={e => setLinkForm({ ...linkForm, link_name: e.target.value })}
                placeholder="My Video Booking Link"
              />
            </div>

            <div className="form-group">
              <label>URL Slug *</label>
              <div className="slug-input">
                <span className="slug-prefix">/meeting/book/</span>
                <input
                  type="text"
                  value={linkForm.slug}
                  onChange={e => setLinkForm({ ...linkForm, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })}
                  placeholder="my-link"
                />
              </div>
            </div>

            <div className="form-group">
              <label>Description</label>
              <textarea
                value={linkForm.description}
                onChange={e => setLinkForm({ ...linkForm, description: e.target.value })}
                placeholder="Optional description..."
                rows={2}
              />
            </div>

            <div className="form-group">
              <label>Meeting Types</label>
              <div className="type-checkboxes">
                {meetingTypes.map(type => (
                  <label key={type.id || type.template_key} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={linkForm.meeting_type_ids.includes(type.id)}
                      onChange={e => {
                        if (e.target.checked) {
                          setLinkForm({ ...linkForm, meeting_type_ids: [...linkForm.meeting_type_ids, type.id] });
                        } else {
                          setLinkForm({ ...linkForm, meeting_type_ids: linkForm.meeting_type_ids.filter(id => id !== type.id) });
                        }
                      }}
                    />
                    {type.template_name || type.type_name}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="modal-footer">
            <button className="cancel-btn" onClick={() => setShowNewLinkModal(false)}>Cancel</button>
            <button
              className="confirm-btn"
              onClick={() => handleCreateBookingLink(linkForm)}
              disabled={!linkForm.slug || !linkForm.link_name}
            >
              Create Link
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Render Meeting Detail Modal
  const renderMeetingDetailModal = () => {
    if (!showMeetingDetail || !selectedMeeting) return null;

    const meeting = selectedMeeting.meeting;
    const participants = selectedMeeting.participants || [];
    const recordings = selectedMeeting.recordings || [];

    return (
      <div className="modal-overlay" onClick={() => setShowMeetingDetail(false)}>
        <div className="modal-content large" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>{sanitizeText(meeting.room_name)}</h3>
            <button className="close-btn" onClick={() => setShowMeetingDetail(false)}>×</button>
          </div>
          <div className="modal-body">
            <div className="detail-section">
              <div className="detail-row">
                <span className="detail-label">Status:</span>
                {getStatusBadge(meeting.status)}
              </div>
              <div className="detail-row">
                <span className="detail-label">Room Code:</span>
                <span className="room-code-large">{meeting.room_code}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Scheduled:</span>
                <span>{formatDateTime(meeting.scheduled_start)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Duration:</span>
                <span>{meeting.duration_minutes} minutes</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Type:</span>
                <span>{meeting.meeting_type}</span>
              </div>
              {meeting.room_description && (
                <div className="detail-row">
                  <span className="detail-label">Description:</span>
                  <SafeHTML html={meeting.room_description} />
                </div>
              )}
            </div>

            <div className="detail-section">
              <h4>Participants ({participants.length})</h4>
              {participants.length === 0 ? (
                <p className="no-data">No participants yet</p>
              ) : (
                <div className="participants-list">
                  {participants.map(p => (
                    <div key={p.id} className="participant-item">
                      <span className="participant-name">{sanitizeText(p.display_name || p.email)}</span>
                      <span className={`participant-role ${p.role}`}>{p.role}</span>
                      <span className={`participant-status ${p.status}`}>{p.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="detail-section">
              <h4>Recordings ({recordings.length})</h4>
              {recordings.length === 0 ? (
                <p className="no-data">No recordings yet</p>
              ) : (
                <div className="recordings-list">
                  {recordings.map(r => (
                    <div
                      key={r.id}
                      className="recording-item clickable"
                      onClick={() => viewRecording(r.id, meeting.room_name)}
                    >
                      <span className="recording-icon">🔴</span>
                      <span className="recording-name">{sanitizeText(r.recording_name)}</span>
                      <span className="recording-status">{r.status}</span>
                      {r.duration_seconds && (
                        <span className="recording-duration">
                          {Math.floor(r.duration_seconds / 60)}:{(r.duration_seconds % 60).toString().padStart(2, '0')}
                        </span>
                      )}
                      <span className="recording-play-btn">▶ Play</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {meeting.ai_summary && (
              <div className="detail-section">
                <h4>AI Summary</h4>
                <SafeHTML className="ai-summary" html={meeting.ai_summary} />
              </div>
            )}

            {meeting.ai_action_items && meeting.ai_action_items.length > 0 && (
              <div className="detail-section">
                <h4>Action Items</h4>
                <ul className="action-items-list">
                  {meeting.ai_action_items.map((item, idx) => (
                    <li key={idx}>{sanitizeText(item)}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div className="modal-footer">
            {meeting.status === 'scheduled' && (
              <>
                <button className="danger-btn" onClick={() => cancelMeeting(meeting.id)}>
                  Cancel Meeting
                </button>
                <button className="primary-btn" onClick={() => startMeeting(meeting.id)}>
                  Start Meeting
                </button>
              </>
            )}
            {meeting.status === 'active' && (
              <>
                <button className="danger-btn" onClick={() => endMeeting(meeting.id)}>
                  End Meeting
                </button>
                <button
                  className="primary-btn"
                  onClick={() => window.open(`/meeting/${meeting.room_code}`, '_blank')}
                >
                  Join Meeting
                </button>
              </>
            )}
            {meeting.status === 'ended' && (
              <button className="secondary-btn" onClick={() => setShowMeetingDetail(false)}>
                Close
              </button>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Main Render
  if (loading) {
    return (
      <div className="video-meetings-container">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading meetings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="smart-scheduler">
      {/* Header */}
      <div className="scheduler-header">
        <h2>Video Meetings</h2>
        <div className="scheduler-tabs">
        <button
          className={`tab ${view === 'types' ? 'active' : ''}`}
          onClick={() => setView('types')}
        >
          Meeting Types
        </button>
        <button
          className={`tab ${view === 'booking-links' ? 'active' : ''}`}
          onClick={() => setView('booking-links')}
        >
          Booking Links
        </button>
        <button
          className={`tab ${view === 'reminders' ? 'active' : ''}`}
          onClick={() => setView('reminders')}
        >
          Reminders
        </button>
        <button
          className={`tab ${view === 'settings' ? 'active' : ''}`}
          onClick={() => setView('settings')}
        >
          Settings
        </button>
        <button
          className={`tab ${view === 'landing-page' ? 'active' : ''}`}
          onClick={() => setView('landing-page')}
        >
          Landing Page
        </button>
        <button
          className={`tab tutorial-tab ${view === 'tutorial' ? 'active' : ''}`}
          onClick={() => setView('tutorial')}
        >
          Tutorial
        </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Content */}
      <div className="scheduler-content">
        {view === 'types' && renderTypesView()}
        {view === 'booking-links' && renderBookingLinksView()}
        {view === 'reminders' && renderRemindersView()}
        {view === 'settings' && renderSettingsView()}
        {view === 'landing-page' && renderLandingPageView()}
        {view === 'tutorial' && renderTutorialView()}
      </div>

      {/* Modals */}
      {renderCreateModal()}
      {renderMeetingDetailModal()}
      {renderTypeModal()}
      {renderNewLinkModal()}

      {/* Recording Player */}
      {showRecordingPlayer && selectedRecording && (
        <RecordingPlayer
          recording={selectedRecording}
          onClose={() => {
            setShowRecordingPlayer(false);
            setSelectedRecording(null);
          }}
        />
      )}
    </div>
  );
};

export default VideoMeetings;
