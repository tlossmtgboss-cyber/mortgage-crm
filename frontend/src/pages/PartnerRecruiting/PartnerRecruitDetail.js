import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getPartnerCandidate,
  updatePartnerCandidate,
  updatePartnerStatus,
  getPartnerMeetings,
  scheduleMeeting,
  completeMeeting,
  getPartnerProposals,
  createProposal,
  sendProposal,
  getPartnerNotes,
  addPartnerNote,
  getPartnerActivities,
  logCall,
  logEmail,
  getPartnerAssessment,
  updatePartnerAssessment,
  onboardPartner,
  hireEmployeeCandidate,
  getStatusColor,
  getStatusLabel,
  getPartnerTypeLabel,
  getAvailableStatuses,
  formatPhoneNumber,
  PARTNER_STATUSES,
  PARTNER_TYPES,
  EMPLOYEE_STATUSES,
  EMPLOYEE_ROLES,
  MEETING_TYPES,
  MEETING_OUTCOMES,
  CALL_OUTCOMES
} from '../../services/partnerRecruitingApi';
import './PartnerRecruiting.css';

// Pipeline stages in order — category-aware
const PARTNER_PIPELINE_STAGES = ['new', 'contacted', 'qualified', 'meeting_scheduled', 'met', 'proposal_sent', 'negotiating', 'onboarded'];
const EMPLOYEE_PIPELINE_STAGES = ['new', 'contacted', 'qualified', 'meeting_scheduled', 'met', 'screening', 'interview', 'offer', 'hired'];

const PartnerRecruitDetail = () => {
  const { partnerId } = useParams();
  const navigate = useNavigate();

  // State
  const [partner, setPartner] = useState(null);
  const [meetings, setMeetings] = useState([]);
  const [proposals, setProposals] = useState([]);
  const [notes, setNotes] = useState([]);
  const [activities, setActivities] = useState([]);
  const [assessment, setAssessment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  // Modal states
  const [showScheduleMeeting, setShowScheduleMeeting] = useState(false);
  const [showCreateProposal, setShowCreateProposal] = useState(false);
  const [showLogCall, setShowLogCall] = useState(false);
  const [showEditPartner, setShowEditPartner] = useState(false);
  const [showCompleteMeeting, setShowCompleteMeeting] = useState(null);

  // Form states
  const [newNote, setNewNote] = useState('');
  const [meetingForm, setMeetingForm] = useState({
    meeting_type: 'coffee',
    title: '',
    scheduled_at: '',
    duration_minutes: 30,
    location: ''
  });
  const [proposalForm, setProposalForm] = useState({
    proposal_type: 'standard',
    referral_commission_structure: { type: 'per_closed', amount: 250 },
    co_marketing_benefits: [],
    additional_benefits: ''
  });
  const [callForm, setCallForm] = useState({
    outcome: 'connected',
    duration_seconds: 300,
    notes: ''
  });
  const [editForm, setEditForm] = useState({});

  const loadPartner = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getPartnerCandidate(partnerId);
      setPartner(data);
      const isEmployee = data.candidate_category === 'employee';
      setEditForm({
        first_name: data.first_name || '',
        last_name: data.last_name || '',
        email: data.email || '',
        phone: data.phone || '',
        company_name: data.company_name || '',
        license_number: data.license_number || '',
        city: data.city || '',
        state: data.state || '',
        years_in_business: data.years_in_business || '',
        notes: data.notes || '',
        // Employee fields
        ...(isEmployee && {
          employee_role: data.employee_role || '',
          nmls_id: data.nmls_id || '',
          current_employer: data.current_employer || '',
          years_experience: data.years_experience || '',
          desired_compensation: data.desired_compensation || '',
        }),
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [partnerId]);

  const loadMeetings = useCallback(async () => {
    try {
      const data = await getPartnerMeetings(partnerId);
      setMeetings(data.meetings || []);
    } catch (err) {
      console.error('Failed to load meetings:', err);
    }
  }, [partnerId]);

  const loadProposals = useCallback(async () => {
    try {
      const data = await getPartnerProposals(partnerId);
      setProposals(data.proposals || []);
    } catch (err) {
      console.error('Failed to load proposals:', err);
    }
  }, [partnerId]);

  const loadNotes = useCallback(async () => {
    try {
      const data = await getPartnerNotes(partnerId);
      setNotes(data.notes || []);
    } catch (err) {
      console.error('Failed to load notes:', err);
    }
  }, [partnerId]);

  const loadActivities = useCallback(async () => {
    try {
      const data = await getPartnerActivities(partnerId);
      setActivities(data.activities || []);
    } catch (err) {
      console.error('Failed to load activities:', err);
    }
  }, [partnerId]);

  const loadAssessment = useCallback(async () => {
    try {
      const data = await getPartnerAssessment(partnerId);
      setAssessment(data);
    } catch (err) {
      // No assessment yet is okay
      console.log('No assessment yet:', err.message);
    }
  }, [partnerId]);

  useEffect(() => {
    loadPartner();
    loadMeetings();
    loadProposals();
    loadNotes();
    loadActivities();
    loadAssessment();
  }, [loadPartner, loadMeetings, loadProposals, loadNotes, loadActivities, loadAssessment]);

  const handleStatusChange = async (newStatus) => {
    try {
      await updatePartnerStatus(partnerId, newStatus);
      setPartner({ ...partner, status: newStatus });
      loadActivities();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) return;
    try {
      await addPartnerNote(partnerId, { content: newNote, note_type: 'general' });
      setNewNote('');
      loadNotes();
      loadActivities();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleScheduleMeeting = async (e) => {
    e.preventDefault();
    try {
      await scheduleMeeting(partnerId, meetingForm);
      setShowScheduleMeeting(false);
      setMeetingForm({
        meeting_type: 'coffee',
        title: '',
        scheduled_at: '',
        duration_minutes: 30,
        location: ''
      });
      loadMeetings();
      loadActivities();
      // Auto-update status if needed
      if (partner.status === 'qualified' || partner.status === 'contacted') {
        handleStatusChange('meeting_scheduled');
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCompleteMeeting = async (meetingId, outcome, notes) => {
    try {
      await completeMeeting(meetingId, { outcome, next_steps: notes });
      setShowCompleteMeeting(null);
      loadMeetings();
      loadActivities();
      // Auto-update status if needed
      if (partner.status === 'meeting_scheduled') {
        handleStatusChange('met');
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCreateProposal = async (e) => {
    e.preventDefault();
    try {
      await createProposal(partnerId, proposalForm);
      setShowCreateProposal(false);
      loadProposals();
      loadActivities();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSendProposal = async (proposalId) => {
    try {
      await sendProposal(proposalId);
      loadProposals();
      loadActivities();
      if (partner.status === 'met' || partner.status === 'qualified') {
        handleStatusChange('proposal_sent');
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleLogCall = async (e) => {
    e.preventDefault();
    try {
      await logCall(partnerId, callForm);
      setShowLogCall(false);
      setCallForm({ outcome: 'connected', duration_seconds: 300, notes: '' });
      loadActivities();
      // Auto-update status if first contact
      if (partner.status === 'new') {
        handleStatusChange('contacted');
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleOnboard = async () => {
    if (!window.confirm('Onboard this partner? This will create a Referral Partner record.')) {
      return;
    }
    try {
      await onboardPartner(partnerId);
      loadPartner();
      loadActivities();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleHire = async () => {
    if (!window.confirm('Mark this candidate as hired?')) {
      return;
    }
    try {
      await hireEmployeeCandidate(partnerId);
      loadPartner();
      loadActivities();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSavePartner = async () => {
    try {
      await updatePartnerCandidate(partnerId, editForm);
      setShowEditPartner(false);
      loadPartner();
    } catch (err) {
      setError(err.message);
    }
  };

  const isEmployee = partner?.candidate_category === 'employee';
  const pipelineStages = isEmployee ? EMPLOYEE_PIPELINE_STAGES : PARTNER_PIPELINE_STAGES;
  const statusList = isEmployee ? EMPLOYEE_STATUSES : PARTNER_STATUSES;

  const getCurrentStageIndex = () => {
    return pipelineStages.indexOf(partner?.status);
  };

  if (loading) {
    return (
      <div className="pr-loading">
        <div className="pr-spinner"></div>
        <p>Loading Profile...</p>
      </div>
    );
  }

  if (error && !partner) {
    return (
      <div className="pr-container">
        <div className="pr-error">
          <span>{error}</span>
          <button onClick={() => navigate(-1)}>Go Back</button>
        </div>
      </div>
    );
  }

  if (!partner) {
    return (
      <div className="pr-container">
        <div className="pr-error">
          <span>Candidate not found</span>
          <button onClick={() => navigate(-1)}>Go Back</button>
        </div>
      </div>
    );
  }

  return (
    <div className="pr-container pr-detail">
      {/* Header */}
      <div className="pr-header pr-detail-header">
        <div className="pr-header-left">
          <button className="pr-btn pr-btn-secondary" onClick={() => navigate(-1)}>
            ← Back
          </button>
          <div className="pr-detail-info">
            <div className="pr-detail-name-row">
              <h1>{partner.first_name} {partner.last_name}</h1>
              <span
                className="pr-status-badge"
                style={{ backgroundColor: getStatusColor(partner.status, partner.candidate_category) }}
              >
                {getStatusLabel(partner.status, partner.candidate_category)}
              </span>
            </div>
            <p className="pr-detail-subtitle">
              {isEmployee
                ? getPartnerTypeLabel(partner.employee_role)
                : getPartnerTypeLabel(partner.partner_type)}
              {!isEmployee && partner.company_name && ` at ${partner.company_name}`}
              {isEmployee && partner.current_employer && ` at ${partner.current_employer}`}
              {!isEmployee && partner.license_number && <span className="pr-license"> | License #{partner.license_number}</span>}
              {isEmployee && partner.nmls_id && <span className="pr-license"> | NMLS #{partner.nmls_id}</span>}
            </p>
          </div>
        </div>
        <div className="pr-header-actions">
          <button className="pr-btn pr-btn-secondary" onClick={() => setShowEditPartner(true)}>
            Edit
          </button>
          {!isEmployee && partner.status === 'negotiating' && (
            <button className="pr-btn pr-btn-primary" onClick={handleOnboard}>
              Onboard Partner
            </button>
          )}
          {isEmployee && partner.status === 'offer' && (
            <button className="pr-btn pr-btn-primary" onClick={handleHire}>
              Mark as Hired
            </button>
          )}
          <select
            value={partner.status}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="pr-select"
            style={{ backgroundColor: getStatusColor(partner.status, partner.candidate_category), color: 'white' }}
          >
            {getAvailableStatuses(partner.candidate_category).map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="pr-error">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Hero Card */}
      <div className="pr-hero-card">
        <div className="pr-hero-left">
          <div
            className="pr-avatar-large"
            style={{ backgroundColor: getStatusColor(partner.status) }}
          >
            {partner.first_name?.charAt(0)}
          </div>
          <div className="pr-contact-info">
            <div className="pr-contact-item">
              <span className="pr-contact-icon">@</span>
              <a href={`mailto:${partner.email}`}>{partner.email || '-'}</a>
            </div>
            <div className="pr-contact-item">
              <span className="pr-contact-icon">#</span>
              <a href={`tel:${partner.phone}`}>{formatPhoneNumber(partner.phone) || '-'}</a>
            </div>
            {partner.city && partner.state && (
              <div className="pr-contact-item">
                <span className="pr-contact-icon">@</span>
                <span>{partner.city}, {partner.state}</span>
              </div>
            )}
          </div>
        </div>

        <div className="pr-hero-stats">
          <h4>{isEmployee ? 'Employee Info' : 'Partner Info'}</h4>
          <div className="pr-stats-row">
            {isEmployee ? (
              <>
                <div className="pr-stat-item">
                  <span className="pr-stat-value">{partner.years_experience || '-'}</span>
                  <span className="pr-stat-label">Years Experience</span>
                </div>
                <div className="pr-stat-item">
                  <span className="pr-stat-value">{getPartnerTypeLabel(partner.employee_role) || '-'}</span>
                  <span className="pr-stat-label">Target Role</span>
                </div>
                <div className="pr-stat-item">
                  <span className="pr-stat-value">{partner.current_employer || '-'}</span>
                  <span className="pr-stat-label">Current Employer</span>
                </div>
              </>
            ) : (
              <>
                <div className="pr-stat-item">
                  <span className="pr-stat-value">{partner.years_in_business || '-'}</span>
                  <span className="pr-stat-label">Years in Business</span>
                </div>
                <div className="pr-stat-item">
                  <span className="pr-stat-value">{partner.avg_referrals_per_month || '-'}</span>
                  <span className="pr-stat-label">Avg Referrals/Mo</span>
                </div>
                <div className="pr-stat-item">
                  <span className="pr-stat-value">${(partner.production_volume || 0).toLocaleString()}</span>
                  <span className="pr-stat-label">Production Volume</span>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="pr-hero-scores">
          <h4>Assessment Score</h4>
          <div className="pr-score-display">
            <div
              className="pr-score-circle"
              style={{ borderColor: partner.overall_score >= 70 ? '#2D7A52' : partner.overall_score >= 50 ? '#f59e0b' : '#ef4444' }}
            >
              <span className="pr-score-value">
                {partner.overall_score ? Math.round(partner.overall_score) : '-'}
              </span>
              <span className="pr-score-label">Overall</span>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="pr-tabs">
        <button
          className={`pr-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`pr-tab ${activeTab === 'meetings' ? 'active' : ''}`}
          onClick={() => setActiveTab('meetings')}
        >
          Meetings
        </button>
        {!isEmployee && (
          <button
            className={`pr-tab ${activeTab === 'proposals' ? 'active' : ''}`}
            onClick={() => setActiveTab('proposals')}
          >
            Proposals
          </button>
        )}
        <button
          className={`pr-tab ${activeTab === 'notes' ? 'active' : ''}`}
          onClick={() => setActiveTab('notes')}
        >
          Notes
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="pr-detail-grid">
          {/* Left Column - Pipeline */}
          <div className="pr-detail-section">
            <h3>Recruiting Pipeline</h3>
            <div className="pr-pipeline-tracker">
              {pipelineStages.map((stage, index) => {
                const stageInfo = statusList.find(s => s.value === stage);
                const currentIndex = getCurrentStageIndex();
                const isStageCompleted = currentIndex > index;
                const isCurrent = currentIndex === index;

                return (
                  <div
                    key={stage}
                    className={`pr-pipeline-step ${isStageCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''}`}
                    onClick={() => handleStatusChange(stage)}
                  >
                    <div
                      className="pr-step-marker"
                      style={{
                        backgroundColor: isStageCompleted || isCurrent ? stageInfo?.color : '#e5e7eb'
                      }}
                    >
                      {isStageCompleted ? '✓' : index + 1}
                    </div>
                    <span className="pr-step-label">{stageInfo?.label}</span>
                    {index < pipelineStages.length - 1 && (
                      <div className={`pr-step-connector ${isStageCompleted ? 'completed' : ''}`} />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Terminal Status */}
            {['declined', 'inactive', 'withdrawn'].includes(partner.status) && (
              <div className="pr-terminal-status">
                <span>Candidate was {getStatusLabel(partner.status, partner.candidate_category)?.toLowerCase()}</span>
              </div>
            )}

            {/* Upcoming Meetings */}
            <div className="pr-upcoming-meetings">
              <h4>Upcoming Meetings</h4>
              {meetings.filter(m => m.status === 'scheduled').length > 0 ? (
                meetings.filter(m => m.status === 'scheduled').slice(0, 3).map(meeting => (
                  <div key={meeting.id} className="pr-meeting-item">
                    <div className="pr-meeting-info">
                      <span className="pr-meeting-type">{MEETING_TYPES.find(t => t.value === meeting.meeting_type)?.label || meeting.meeting_type}</span>
                      <span className="pr-meeting-date">
                        {new Date(meeting.scheduled_at).toLocaleDateString()} at {new Date(meeting.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <button
                      className="pr-btn pr-btn-small pr-btn-primary"
                      onClick={() => setShowCompleteMeeting(meeting)}
                    >
                      Complete
                    </button>
                  </div>
                ))
              ) : (
                <p className="pr-empty-text">No upcoming meetings</p>
              )}
            </div>
          </div>

          {/* Center Column - Next Steps */}
          <div className="pr-detail-section">
            <h3>Next Steps</h3>
            <div className="pr-task-list">
              {/* Shared early stages */}
              {partner.status === 'new' && (
                <button className="pr-task-item" onClick={() => setShowLogCall(true)}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Make Initial Contact</strong>
                    <p>Introduce yourself and gauge interest</p>
                  </div>
                </button>
              )}
              {partner.status === 'contacted' && (
                <>
                  <button className="pr-task-item" onClick={() => setShowScheduleMeeting(true)}>
                    <span className="pr-task-icon">@</span>
                    <div className="pr-task-content">
                      <strong>Schedule Meeting</strong>
                      <p>{isEmployee ? 'Set up an introductory meeting' : 'Set up coffee or lunch to discuss partnership'}</p>
                    </div>
                  </button>
                  <button className="pr-task-item" onClick={() => handleStatusChange('qualified')}>
                    <span className="pr-task-icon">@</span>
                    <div className="pr-task-content">
                      <strong>Mark as Qualified</strong>
                      <p>{isEmployee ? 'Confirm this is a strong candidate' : 'Confirm this is a good partnership fit'}</p>
                    </div>
                  </button>
                </>
              )}
              {(partner.status === 'qualified' || partner.status === 'meeting_scheduled') && (
                <button className="pr-task-item" onClick={() => setShowScheduleMeeting(true)}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Schedule/Confirm Meeting</strong>
                    <p>{isEmployee ? 'Meet to discuss the opportunity' : 'Meet to discuss partnership details'}</p>
                  </div>
                </button>
              )}

              {/* Partner-specific stages */}
              {!isEmployee && partner.status === 'met' && (
                <button className="pr-task-item" onClick={() => setShowCreateProposal(true)}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Create Proposal</strong>
                    <p>Draft partnership proposal with terms</p>
                  </div>
                </button>
              )}
              {!isEmployee && partner.status === 'proposal_sent' && (
                <button className="pr-task-item" onClick={() => setShowLogCall(true)}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Follow Up on Proposal</strong>
                    <p>Check in on their decision</p>
                  </div>
                </button>
              )}
              {!isEmployee && partner.status === 'negotiating' && (
                <button className="pr-task-item" onClick={handleOnboard}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Finalize & Onboard</strong>
                    <p>Complete partnership onboarding</p>
                  </div>
                </button>
              )}
              {!isEmployee && partner.status === 'onboarded' && (
                <div className="pr-success-state">
                  <span className="pr-success-icon">@</span>
                  <div>
                    <strong>Partnership Active!</strong>
                    <p>Partner is now onboarded and ready for referrals</p>
                  </div>
                </div>
              )}

              {/* Employee-specific stages */}
              {isEmployee && partner.status === 'met' && (
                <button className="pr-task-item" onClick={() => handleStatusChange('screening')}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Begin Screening</strong>
                    <p>Review qualifications, background, and references</p>
                  </div>
                </button>
              )}
              {isEmployee && partner.status === 'screening' && (
                <button className="pr-task-item" onClick={() => handleStatusChange('interview')}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Schedule Interview</strong>
                    <p>Conduct formal interview with hiring team</p>
                  </div>
                </button>
              )}
              {isEmployee && partner.status === 'interview' && (
                <button className="pr-task-item" onClick={() => handleStatusChange('offer')}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Extend Offer</strong>
                    <p>Present compensation package and offer letter</p>
                  </div>
                </button>
              )}
              {isEmployee && partner.status === 'offer' && (
                <button className="pr-task-item" onClick={handleHire}>
                  <span className="pr-task-icon">@</span>
                  <div className="pr-task-content">
                    <strong>Mark as Hired</strong>
                    <p>Candidate accepted the offer</p>
                  </div>
                </button>
              )}
              {isEmployee && partner.status === 'hired' && (
                <div className="pr-success-state">
                  <span className="pr-success-icon">@</span>
                  <div>
                    <strong>Hired!</strong>
                    <p>Employee has been onboarded to the team</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right Column - Quick Actions & Notes */}
          <div className="pr-detail-section">
            <h3>Quick Actions</h3>
            <div className="pr-quick-actions-grid">
              <button className="pr-quick-btn" onClick={() => setShowLogCall(true)}>
                Call
              </button>
              <button
                className="pr-quick-btn"
                onClick={() => window.open(`mailto:${partner.email}`, '_blank')}
                disabled={!partner.email}
              >
                Email
              </button>
              <button className="pr-quick-btn" onClick={() => setShowScheduleMeeting(true)}>
                Schedule
              </button>
              {!isEmployee && (
                <button className="pr-quick-btn" onClick={() => setShowCreateProposal(true)}>
                  Proposal
                </button>
              )}
            </div>

            <h3 style={{ marginTop: '24px' }}>Recent Activity</h3>
            <div className="pr-activity-list">
              {activities.slice(0, 5).map((activity, idx) => (
                <div key={idx} className="pr-activity-item">
                  <div className="pr-activity-marker" />
                  <div className="pr-activity-content">
                    <span className="pr-activity-type">{activity.activity_type}</span>
                    <p className="pr-activity-desc">{activity.description}</p>
                    <span className="pr-activity-date">
                      {new Date(activity.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))}
              {activities.length === 0 && (
                <p className="pr-empty-text">No activity yet</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Meetings Tab */}
      {activeTab === 'meetings' && (
        <div className="pr-section">
          <div className="pr-section-header">
            <h3>Meeting History</h3>
            <button className="pr-btn pr-btn-primary" onClick={() => setShowScheduleMeeting(true)}>
              Schedule Meeting
            </button>
          </div>
          {meetings.length > 0 ? (
            <div className="pr-meetings-list">
              {meetings.map(meeting => (
                <div key={meeting.id} className="pr-card pr-meeting-card">
                  <div className="pr-meeting-header">
                    <span className="pr-meeting-type">
                      {MEETING_TYPES.find(t => t.value === meeting.meeting_type)?.label || meeting.meeting_type}
                    </span>
                    <span
                      className="pr-meeting-status"
                      style={{
                        backgroundColor: meeting.status === 'completed' ? '#dcfce7' :
                                        meeting.status === 'scheduled' ? '#dbeafe' : '#f3f4f6',
                        color: meeting.status === 'completed' ? '#16a34a' :
                              meeting.status === 'scheduled' ? '#1d4ed8' : '#6b7280'
                      }}
                    >
                      {meeting.status}
                    </span>
                  </div>
                  <div className="pr-meeting-body">
                    <p className="pr-meeting-datetime">
                      {new Date(meeting.scheduled_at).toLocaleDateString()} at{' '}
                      {new Date(meeting.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </p>
                    {meeting.location && <p className="pr-meeting-location">{meeting.location}</p>}
                    {meeting.outcome && (
                      <p className="pr-meeting-outcome">
                        Outcome: {MEETING_OUTCOMES.find(o => o.value === meeting.outcome)?.label || meeting.outcome}
                      </p>
                    )}
                    {meeting.next_steps && <p className="pr-meeting-notes">{meeting.next_steps}</p>}
                  </div>
                  {meeting.status === 'scheduled' && (
                    <button
                      className="pr-btn pr-btn-primary pr-btn-full"
                      onClick={() => setShowCompleteMeeting(meeting)}
                    >
                      Complete Meeting
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="pr-empty-state">
              <p>No meetings scheduled yet</p>
              <button className="pr-btn pr-btn-primary" onClick={() => setShowScheduleMeeting(true)}>
                Schedule First Meeting
              </button>
            </div>
          )}
        </div>
      )}

      {/* Proposals Tab */}
      {activeTab === 'proposals' && (
        <div className="pr-section">
          <div className="pr-section-header">
            <h3>Proposals</h3>
            <button className="pr-btn pr-btn-primary" onClick={() => setShowCreateProposal(true)}>
              Create Proposal
            </button>
          </div>
          {proposals.length > 0 ? (
            <div className="pr-proposals-list">
              {proposals.map(proposal => (
                <div key={proposal.id} className="pr-card pr-proposal-card">
                  <div className="pr-proposal-header">
                    <span className="pr-proposal-number">{proposal.proposal_number}</span>
                    <span
                      className="pr-proposal-status"
                      style={{
                        backgroundColor: proposal.status === 'accepted' ? '#dcfce7' :
                                        proposal.status === 'sent' ? '#dbeafe' :
                                        proposal.status === 'declined' ? '#fee2e2' : '#f3f4f6',
                        color: proposal.status === 'accepted' ? '#16a34a' :
                              proposal.status === 'sent' ? '#1d4ed8' :
                              proposal.status === 'declined' ? '#dc2626' : '#6b7280'
                      }}
                    >
                      {proposal.status}
                    </span>
                  </div>
                  <div className="pr-proposal-body">
                    <p className="pr-proposal-type">{proposal.proposal_type} Proposal</p>
                    {proposal.sent_at && (
                      <p className="pr-proposal-sent">Sent: {new Date(proposal.sent_at).toLocaleDateString()}</p>
                    )}
                    {proposal.expires_at && (
                      <p className="pr-proposal-expires">Expires: {new Date(proposal.expires_at).toLocaleDateString()}</p>
                    )}
                  </div>
                  {proposal.status === 'draft' && (
                    <button
                      className="pr-btn pr-btn-primary pr-btn-full"
                      onClick={() => handleSendProposal(proposal.id)}
                    >
                      Send Proposal
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="pr-empty-state">
              <p>No proposals created yet</p>
              <button className="pr-btn pr-btn-primary" onClick={() => setShowCreateProposal(true)}>
                Create First Proposal
              </button>
            </div>
          )}
        </div>
      )}

      {/* Notes Tab */}
      {activeTab === 'notes' && (
        <div className="pr-section">
          <h3>Notes</h3>
          <div className="pr-add-note">
            <textarea
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              placeholder={isEmployee ? "Add a note about this candidate..." : "Add a note about this partner..."}
              className="pr-textarea"
              rows="3"
            />
            <button
              className="pr-btn pr-btn-primary"
              onClick={handleAddNote}
              disabled={!newNote.trim()}
            >
              Add Note
            </button>
          </div>
          <div className="pr-notes-list">
            {notes.map(note => (
              <div key={note.id} className="pr-card pr-note-card">
                <p className="pr-note-content">{note.content}</p>
                <div className="pr-note-meta">
                  <span className="pr-note-type">{note.note_type}</span>
                  <span className="pr-note-date">
                    {new Date(note.created_at).toLocaleString()}
                  </span>
                </div>
              </div>
            ))}
            {notes.length === 0 && (
              <p className="pr-empty-text">No notes yet</p>
            )}
          </div>
        </div>
      )}

      {/* Schedule Meeting Modal */}
      {showScheduleMeeting && (
        <div className="pr-modal-overlay">
          <div className="pr-modal">
            <div className="pr-modal-header">
              <h3>Schedule Meeting</h3>
              <button className="pr-modal-close" onClick={() => setShowScheduleMeeting(false)}>&times;</button>
            </div>
            <form onSubmit={handleScheduleMeeting}>
              <div className="pr-form-group">
                <label>Meeting Type*</label>
                <select
                  value={meetingForm.meeting_type}
                  onChange={(e) => setMeetingForm({ ...meetingForm, meeting_type: e.target.value })}
                  required
                  className="pr-select"
                >
                  {MEETING_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div className="pr-form-group">
                <label>Title</label>
                <input
                  type="text"
                  value={meetingForm.title}
                  onChange={(e) => setMeetingForm({ ...meetingForm, title: e.target.value })}
                  placeholder="Partnership Discussion"
                  className="pr-input"
                />
              </div>
              <div className="pr-form-group">
                <label>Date & Time*</label>
                <input
                  type="datetime-local"
                  value={meetingForm.scheduled_at}
                  onChange={(e) => setMeetingForm({ ...meetingForm, scheduled_at: e.target.value })}
                  required
                  className="pr-input"
                />
              </div>
              <div className="pr-form-row">
                <div className="pr-form-group">
                  <label>Duration (minutes)</label>
                  <select
                    value={meetingForm.duration_minutes}
                    onChange={(e) => setMeetingForm({ ...meetingForm, duration_minutes: parseInt(e.target.value) })}
                    className="pr-select"
                  >
                    <option value={15}>15 min</option>
                    <option value={30}>30 min</option>
                    <option value={45}>45 min</option>
                    <option value={60}>1 hour</option>
                    <option value={90}>1.5 hours</option>
                  </select>
                </div>
                <div className="pr-form-group">
                  <label>Location</label>
                  <input
                    type="text"
                    value={meetingForm.location}
                    onChange={(e) => setMeetingForm({ ...meetingForm, location: e.target.value })}
                    placeholder="Starbucks on Main St"
                    className="pr-input"
                  />
                </div>
              </div>
              <div className="pr-modal-actions">
                <button type="button" className="pr-btn pr-btn-secondary" onClick={() => setShowScheduleMeeting(false)}>
                  Cancel
                </button>
                <button type="submit" className="pr-btn pr-btn-primary">
                  Schedule
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Complete Meeting Modal */}
      {showCompleteMeeting && (
        <CompleteMeetingModal
          meeting={showCompleteMeeting}
          onComplete={(outcome, notes) => handleCompleteMeeting(showCompleteMeeting.id, outcome, notes)}
          onClose={() => setShowCompleteMeeting(null)}
        />
      )}

      {/* Create Proposal Modal */}
      {showCreateProposal && (
        <div className="pr-modal-overlay">
          <div className="pr-modal pr-modal-large">
            <div className="pr-modal-header">
              <h3>Create Proposal</h3>
              <button className="pr-modal-close" onClick={() => setShowCreateProposal(false)}>&times;</button>
            </div>
            <form onSubmit={handleCreateProposal}>
              <div className="pr-form-group">
                <label>Proposal Type</label>
                <select
                  value={proposalForm.proposal_type}
                  onChange={(e) => setProposalForm({ ...proposalForm, proposal_type: e.target.value })}
                  className="pr-select"
                >
                  <option value="standard">Standard</option>
                  <option value="premium">Premium</option>
                  <option value="custom">Custom</option>
                  <option value="exclusive">Exclusive Territory</option>
                </select>
              </div>
              <div className="pr-form-group">
                <label>Referral Commission</label>
                <input
                  type="number"
                  value={proposalForm.referral_commission_structure.amount}
                  onChange={(e) => setProposalForm({
                    ...proposalForm,
                    referral_commission_structure: { ...proposalForm.referral_commission_structure, amount: parseInt(e.target.value) }
                  })}
                  placeholder="250"
                  className="pr-input"
                />
                <span className="pr-form-hint">Per closed referral</span>
              </div>
              <div className="pr-form-group">
                <label>Additional Benefits</label>
                <textarea
                  value={proposalForm.additional_benefits}
                  onChange={(e) => setProposalForm({ ...proposalForm, additional_benefits: e.target.value })}
                  placeholder="List any additional benefits..."
                  className="pr-textarea"
                  rows="3"
                />
              </div>
              <div className="pr-modal-actions">
                <button type="button" className="pr-btn pr-btn-secondary" onClick={() => setShowCreateProposal(false)}>
                  Cancel
                </button>
                <button type="submit" className="pr-btn pr-btn-primary">
                  Create Proposal
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Log Call Modal */}
      {showLogCall && (
        <div className="pr-modal-overlay">
          <div className="pr-modal">
            <div className="pr-modal-header">
              <h3>Log Call</h3>
              <button className="pr-modal-close" onClick={() => setShowLogCall(false)}>&times;</button>
            </div>
            <form onSubmit={handleLogCall}>
              <div className="pr-form-group">
                <label>Call Outcome</label>
                <select
                  value={callForm.outcome}
                  onChange={(e) => setCallForm({ ...callForm, outcome: e.target.value })}
                  className="pr-select"
                >
                  {CALL_OUTCOMES.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div className="pr-form-group">
                <label>Duration (minutes)</label>
                <input
                  type="number"
                  value={Math.round(callForm.duration_seconds / 60)}
                  onChange={(e) => setCallForm({ ...callForm, duration_seconds: parseInt(e.target.value) * 60 })}
                  className="pr-input"
                />
              </div>
              <div className="pr-form-group">
                <label>Notes</label>
                <textarea
                  value={callForm.notes}
                  onChange={(e) => setCallForm({ ...callForm, notes: e.target.value })}
                  placeholder="What was discussed..."
                  className="pr-textarea"
                  rows="4"
                />
              </div>
              <div className="pr-modal-actions">
                <button type="button" className="pr-btn pr-btn-secondary" onClick={() => setShowLogCall(false)}>
                  Cancel
                </button>
                <button type="submit" className="pr-btn pr-btn-primary">
                  Log Call
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Partner/Employee Modal */}
      {showEditPartner && (
        <div className="pr-modal-overlay">
          <div className="pr-modal pr-modal-large">
            <div className="pr-modal-header">
              <h3>{isEmployee ? 'Edit Employee' : 'Edit Partner'}</h3>
              <button className="pr-modal-close" onClick={() => setShowEditPartner(false)}>&times;</button>
            </div>
            <div className="pr-form-row">
              <div className="pr-form-group">
                <label>First Name</label>
                <input
                  type="text"
                  value={editForm.first_name}
                  onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                  className="pr-input"
                />
              </div>
              <div className="pr-form-group">
                <label>Last Name</label>
                <input
                  type="text"
                  value={editForm.last_name}
                  onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                  className="pr-input"
                />
              </div>
            </div>
            <div className="pr-form-row">
              <div className="pr-form-group">
                <label>Email</label>
                <input
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                  className="pr-input"
                />
              </div>
              <div className="pr-form-group">
                <label>Phone</label>
                <input
                  type="tel"
                  value={editForm.phone}
                  onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                  className="pr-input"
                />
              </div>
            </div>
            {isEmployee ? (
              <>
                <div className="pr-form-row">
                  <div className="pr-form-group">
                    <label>Role</label>
                    <select
                      value={editForm.employee_role || ''}
                      onChange={(e) => setEditForm({ ...editForm, employee_role: e.target.value })}
                      className="pr-select"
                    >
                      <option value="">Select Role</option>
                      {EMPLOYEE_ROLES.map(r => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="pr-form-group">
                    <label>NMLS ID</label>
                    <input
                      type="text"
                      value={editForm.nmls_id || ''}
                      onChange={(e) => setEditForm({ ...editForm, nmls_id: e.target.value })}
                      className="pr-input"
                    />
                  </div>
                </div>
                <div className="pr-form-row">
                  <div className="pr-form-group">
                    <label>Current Employer</label>
                    <input
                      type="text"
                      value={editForm.current_employer || ''}
                      onChange={(e) => setEditForm({ ...editForm, current_employer: e.target.value })}
                      className="pr-input"
                    />
                  </div>
                  <div className="pr-form-group">
                    <label>Years Experience</label>
                    <input
                      type="number"
                      value={editForm.years_experience || ''}
                      onChange={(e) => setEditForm({ ...editForm, years_experience: parseInt(e.target.value) || '' })}
                      className="pr-input"
                    />
                  </div>
                </div>
                <div className="pr-form-group">
                  <label>Desired Compensation</label>
                  <input
                    type="text"
                    value={editForm.desired_compensation || ''}
                    onChange={(e) => setEditForm({ ...editForm, desired_compensation: e.target.value })}
                    placeholder="e.g., $80K base + 50bps"
                    className="pr-input"
                  />
                </div>
              </>
            ) : (
              <>
                <div className="pr-form-row">
                  <div className="pr-form-group">
                    <label>Company Name</label>
                    <input
                      type="text"
                      value={editForm.company_name}
                      onChange={(e) => setEditForm({ ...editForm, company_name: e.target.value })}
                      className="pr-input"
                    />
                  </div>
                  <div className="pr-form-group">
                    <label>License Number</label>
                    <input
                      type="text"
                      value={editForm.license_number}
                      onChange={(e) => setEditForm({ ...editForm, license_number: e.target.value })}
                      className="pr-input"
                    />
                  </div>
                </div>
                <div className="pr-form-group">
                  <label>Years in Business</label>
                  <input
                    type="number"
                    value={editForm.years_in_business}
                    onChange={(e) => setEditForm({ ...editForm, years_in_business: parseInt(e.target.value) || '' })}
                    className="pr-input"
                  />
                </div>
              </>
            )}
            <div className="pr-form-row">
              <div className="pr-form-group">
                <label>City</label>
                <input
                  type="text"
                  value={editForm.city}
                  onChange={(e) => setEditForm({ ...editForm, city: e.target.value })}
                  className="pr-input"
                />
              </div>
              <div className="pr-form-group">
                <label>State</label>
                <input
                  type="text"
                  value={editForm.state}
                  onChange={(e) => setEditForm({ ...editForm, state: e.target.value })}
                  maxLength={2}
                  className="pr-input"
                />
              </div>
            </div>
            <div className="pr-form-group">
              <label>Notes</label>
              <textarea
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                className="pr-textarea"
                rows="3"
              />
            </div>
            <div className="pr-modal-actions">
              <button className="pr-btn pr-btn-secondary" onClick={() => setShowEditPartner(false)}>
                Cancel
              </button>
              <button className="pr-btn pr-btn-primary" onClick={handleSavePartner}>
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Complete Meeting Modal Component
const CompleteMeetingModal = ({ meeting, onComplete, onClose }) => {
  const [outcome, setOutcome] = useState('positive');
  const [notes, setNotes] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onComplete(outcome, notes);
  };

  return (
    <div className="pr-modal-overlay">
      <div className="pr-modal">
        <div className="pr-modal-header">
          <h3>Complete Meeting</h3>
          <button className="pr-modal-close" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="pr-form-group">
            <label>Meeting Outcome</label>
            <select
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
              className="pr-select"
            >
              {MEETING_OUTCOMES.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="pr-form-group">
            <label>Next Steps / Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="What are the next steps?"
              className="pr-textarea"
              rows="4"
            />
          </div>
          <div className="pr-modal-actions">
            <button type="button" className="pr-btn pr-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="pr-btn pr-btn-primary">
              Complete
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default PartnerRecruitDetail;
