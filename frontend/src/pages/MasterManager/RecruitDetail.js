import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getCandidateFullProfile,
  updateCandidateStatus,
  updateCandidateSocialMedia,
  updateCandidateProduction,
  addCandidateNote,
  scheduleInterview
} from '../../services/masterManagerApi';
import {
  getCandidateAssessment,
  createAssessment,
  updateAssessment,
  getAssessmentHistory
} from '../../services/candidateGradingApi';
import CandidateGradeCircle, { getGrade, GradeBadge } from '../../components/recruiting/CandidateGradeCircle';
import DISCProfileChart from '../../components/recruiting/DISCProfileChart';
import { AssessmentScoreGrid, AssessmentScoreSummary } from '../../components/recruiting/AssessmentScoreCard';
import AIAnalysisPanel from '../../components/recruiting/AIAnalysisPanel';
import AssessmentQuizModal from '../../components/recruiting/AssessmentQuizModal';
import ScheduleInterviewModal from '../../components/recruiting/ScheduleInterviewModal';
import EditScoreCategoryModal from '../../components/recruiting/EditScoreCategoryModal';
import VideoRecorder from '../../components/recruiting/VideoRecorder';
import { usePermissions } from '../../contexts/PermissionContext';
import './MasterManager.css';
import './RecruitDetail.css';

// Dispositions that require quiz completion
const QUIZ_REQUIRED_DISPOSITIONS = ['screening', 'phone_screen', 'interview', 'assessment', 'offer'];

const CANDIDATE_STATUSES = [
  { value: 'new', label: 'New', color: '#3b82f6', icon: '📥' },
  { value: 'screening', label: 'Screening', color: '#8b5cf6', icon: '🔍' },
  { value: 'phone_screen', label: 'Phone Screen', color: '#a855f7', icon: '📞' },
  { value: 'interview', label: 'Interview', color: '#f59e0b', icon: '🎯' },
  { value: 'assessment', label: 'Assessment', color: '#eab308', icon: '📋' },
  { value: 'offer', label: 'Offer', color: '#22c55e', icon: '📝' },
  { value: 'hired', label: 'Hired', color: '#10b981', icon: '✅' },
  { value: 'rejected', label: 'Rejected', color: '#ef4444', icon: '❌' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#6b7280', icon: '🚫' }
];

// Pipeline stages in order (excluding terminal states)
const PIPELINE_STAGES = ['new', 'screening', 'phone_screen', 'interview', 'assessment', 'offer', 'hired'];

const RecruitDetail = () => {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const { currentUserId } = usePermissions();
  const [candidate, setCandidate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showEditSocial, setShowEditSocial] = useState(false);
  const [showEditProduction, setShowEditProduction] = useState(false);
  const [newNote, setNewNote] = useState('');
  const [activeTab, setActiveTab] = useState('overview');

  // Assessment state
  const [assessment, setAssessment] = useState(null);
  const [assessmentLoading, setAssessmentLoading] = useState(false);
  const [assessmentError, setAssessmentError] = useState(null);

  // Quiz modal state
  const [showQuizModal, setShowQuizModal] = useState(false);
  const [pendingStatusChange, setPendingStatusChange] = useState(null);
  const [quizScores, setQuizScores] = useState(null);

  // Call/dialer state
  const [isCallInProgress, setIsCallInProgress] = useState(false);
  const [callHistory, setCallHistory] = useState([]);
  const [showCallNotesModal, setShowCallNotesModal] = useState(false);
  const [activeCallId, setActiveCallId] = useState(null);

  // Schedule interview modal state
  const [showScheduleInterviewModal, setShowScheduleInterviewModal] = useState(false);

  // Edit category modal state
  const [showEditCategoryModal, setShowEditCategoryModal] = useState(false);
  const [editingCategory, setEditingCategory] = useState(null);

  // Video recorder modal state
  const [showVideoRecorder, setShowVideoRecorder] = useState(false);

  // Edit form states
  const [socialForm, setSocialForm] = useState({
    linkedin_url: '',
    facebook_url: '',
    instagram_url: '',
    twitter_url: ''
  });

  const [productionForm, setProductionForm] = useState({
    annual_volume: '',
    annual_units: '',
    nmls_id: '',
    current_company: '',
    current_title: ''
  });

  const loadCandidate = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getCandidateFullProfile(candidateId);
      setCandidate(data);

      // Initialize form states
      setSocialForm({
        linkedin_url: data.social_media?.linkedin || '',
        facebook_url: data.social_media?.facebook || '',
        instagram_url: data.social_media?.instagram || '',
        twitter_url: data.social_media?.twitter || ''
      });

      setProductionForm({
        annual_volume: data.production?.annual_volume || '',
        annual_units: data.production?.annual_units || '',
        nmls_id: data.production?.nmls_id || '',
        current_company: data.production?.current_company || '',
        current_title: data.production?.current_title || ''
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [candidateId]);

  const loadAssessment = useCallback(async () => {
    try {
      setAssessmentLoading(true);
      setAssessmentError(null);
      const data = await getCandidateAssessment(candidateId);
      setAssessment(data);
    } catch (err) {
      // 404 means no assessment exists yet - that's okay
      if (!err.message?.includes('404') && !err.message?.includes('not found')) {
        setAssessmentError(err.message);
      }
    } finally {
      setAssessmentLoading(false);
    }
  }, [candidateId]);

  useEffect(() => {
    loadCandidate();
  }, [loadCandidate]);

  // Load assessment when tab changes to assessment
  useEffect(() => {
    if (activeTab === 'assessment' && !assessment && !assessmentLoading) {
      loadAssessment();
    }
  }, [activeTab, assessment, assessmentLoading, loadAssessment]);

  const handleStatusChange = async (newStatus) => {
    // Check if quiz is required for this disposition change
    if (QUIZ_REQUIRED_DISPOSITIONS.includes(newStatus)) {
      // Store the pending status change and show quiz
      setPendingStatusChange(newStatus);
      setShowQuizModal(true);
      return; // Don't change status until quiz is completed
    }

    // For non-quiz dispositions, proceed directly
    try {
      await updateCandidateStatus(candidateId, newStatus);
      setCandidate({ ...candidate, status: newStatus });
    } catch (err) {
      setError(err.message);
    }
  };

  const handleQuizComplete = async (scores) => {
    // Update the quiz scores
    setQuizScores(scores);

    // Now complete the status change
    if (pendingStatusChange) {
      try {
        await updateCandidateStatus(candidateId, pendingStatusChange);
        setCandidate(prev => ({
          ...prev,
          status: pendingStatusChange,
          scores: {
            overall: scores.overall_score,
            production: scores.production_score,
            disc: scores.disc_score,
            character: scores.character_score,
            skills: scores.skills_score,
            culture_fit: scores.culture_fit_score
          }
        }));

        // Create workflow tasks for the new disposition
        const token = localStorage.getItem('token');
        const userId = JSON.parse(atob(token.split('.')[1])).user_id || 1;
        const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

        try {
          await fetch(`${API_URL}/api/v1/recruiting/workflow/candidates/${candidateId}/create-tasks`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              disposition: pendingStatusChange,
              assigned_to: userId,
              organization_id: 1
            })
          });
        } catch (taskErr) {
          console.warn('Failed to create workflow tasks:', taskErr);
          // Don't fail the overall operation if task creation fails
        }

        setPendingStatusChange(null);
      } catch (err) {
        setError(err.message);
      }
    }
  };

  const handleQuizClose = () => {
    setShowQuizModal(false);
    setPendingStatusChange(null);
  };

  // Click-to-call handler
  const handleClickToCall = async () => {
    if (!candidate?.phone) {
      setError('No phone number available for this candidate');
      return;
    }

    setIsCallInProgress(true);
    const token = localStorage.getItem('token');
    const userId = JSON.parse(atob(token.split('.')[1])).user_id || 1;
    const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

    try {
      const response = await fetch(`${API_URL}/api/v1/recruiting/dialer/candidates/${candidateId}/call`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ caller_id: userId })
      });

      const data = await response.json();
      if (data.call_id) {
        setActiveCallId(data.call_id);
        // In a real implementation, this would trigger the actual Twilio call
        // For now, we'll show a modal to add call notes
        setTimeout(() => {
          setIsCallInProgress(false);
          setShowCallNotesModal(true);
        }, 2000);
      }
    } catch (err) {
      setError('Failed to initiate call: ' + err.message);
      setIsCallInProgress(false);
    }
  };

  // Load call history
  const loadCallHistory = useCallback(async () => {
    const token = localStorage.getItem('token');
    const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

    try {
      const response = await fetch(`${API_URL}/api/v1/recruiting/dialer/candidates/${candidateId}/call-history`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      setCallHistory(data.history || []);
    } catch (err) {
      console.warn('Failed to load call history:', err);
    }
  }, [candidateId]);

  // Save call notes
  const handleSaveCallNotes = async (note, outcome, callbackRequested, callbackDate) => {
    if (!activeCallId) return;

    const token = localStorage.getItem('token');
    const userId = JSON.parse(atob(token.split('.')[1])).user_id || 1;
    const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

    try {
      await fetch(`${API_URL}/api/v1/recruiting/dialer/calls/${activeCallId}/notes`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          note,
          outcome,
          callback_requested: callbackRequested,
          callback_date: callbackDate,
          user_id: userId
        })
      });

      setShowCallNotesModal(false);
      setActiveCallId(null);
      loadCallHistory();
    } catch (err) {
      setError('Failed to save call notes: ' + err.message);
    }
  };

  const handleSaveSocial = async () => {
    try {
      await updateCandidateSocialMedia(candidateId, socialForm);
      await loadCandidate();
      setShowEditSocial(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSaveProduction = async () => {
    try {
      await updateCandidateProduction(candidateId, productionForm);
      await loadCandidate();
      setShowEditProduction(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) return;
    try {
      await addCandidateNote(candidateId, { content: newNote, note_type: 'general' });
      setNewNote('');
      await loadCandidate();
    } catch (err) {
      setError(err.message);
    }
  };

  const getStatusColor = (status) => {
    const statusObj = CANDIDATE_STATUSES.find(s => s.value === status);
    return statusObj?.color || '#6b7280';
  };

  const formatCurrency = (value) => {
    if (!value) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  if (loading) {
    return (
      <div className="mm-loading">
        <div className="mm-spinner"></div>
        <p>Loading Recruit Profile...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mm-container">
        <div className="mm-error">
          <span>{error}</span>
          <button onClick={() => navigate(-1)}>Go Back</button>
        </div>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div className="mm-container">
        <div className="mm-error">
          <span>Candidate not found</span>
          <button onClick={() => navigate(-1)}>Go Back</button>
        </div>
      </div>
    );
  }

  // Get current stage index for pipeline visualization
  const getCurrentStageIndex = () => {
    return PIPELINE_STAGES.indexOf(candidate?.status);
  };

  // Calculate overall score display
  const getOverallScoreDisplay = () => {
    if (candidate?.scores?.overall) {
      return candidate.scores.overall.toFixed(1);
    }
    return '-';
  };

  const getScoreColor = (score) => {
    if (!score) return '#6b7280';
    if (score >= 8) return '#10b981';
    if (score >= 6) return '#f59e0b';
    if (score >= 4) return '#ef4444';
    return '#6b7280';
  };

  return (
    <div className="mm-container recruit-detail">
      {/* Compact Header */}
      <div className="mm-header recruit-header">
        <div className="mm-header-left">
          <button className="mm-btn mm-btn-secondary" onClick={() => navigate(-1)}>
            ← Back
          </button>
          <div className="recruit-header-info">
            <div className="recruit-name-row">
              <h1>{candidate.name}</h1>
              <span
                className="recruit-status-badge"
                style={{ backgroundColor: getStatusColor(candidate.status) }}
              >
                {CANDIDATE_STATUSES.find(s => s.value === candidate.status)?.label || candidate.status}
              </span>
            </div>
            <p className="recruit-subtitle">
              {candidate.production?.current_title || candidate.target_role || 'Candidate'}
              {candidate.production?.current_company ? ` at ${candidate.production.current_company}` : ''}
              {candidate.production?.nmls_id && <span className="recruit-nmls"> • NMLS #{candidate.production.nmls_id}</span>}
            </p>
          </div>
        </div>
        <div className="mm-header-actions">
          <button className="mm-btn mm-btn-secondary" onClick={() => setShowEditProduction(true)}>
            Edit Production
          </button>
          <select
            value={candidate.status}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="mm-select recruit-status-select"
          >
            {CANDIDATE_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Enhanced Header Card with Production & Scores */}
      <div className="recruit-hero-card">
        <div className="recruit-hero-left">
          {/* Avatar */}
          <div
            className="recruit-avatar"
            style={{
              backgroundColor: getStatusColor(candidate.status),
              backgroundImage: candidate.profile?.headshot_url ? `url(${candidate.profile.headshot_url})` : 'none',
            }}
          >
            {!candidate.profile?.headshot_url && candidate.first_name?.charAt(0)}
          </div>

          {/* Contact Info */}
          <div className="recruit-contact-info">
            <div className="recruit-contact-item">
              <span className="recruit-contact-icon">📧</span>
              <a href={`mailto:${candidate.email}`}>{candidate.email || '-'}</a>
            </div>
            <div className="recruit-contact-item recruit-contact-phone">
              <span className="recruit-contact-icon">📱</span>
              <a href={`tel:${candidate.phone}`}>{candidate.phone || '-'}</a>
              {candidate.phone && (
                <button
                  className="recruit-call-btn"
                  onClick={handleClickToCall}
                  disabled={isCallInProgress}
                  title="Click to call"
                >
                  {isCallInProgress ? '📞 Calling...' : '📞 Call'}
                </button>
              )}
            </div>
            <div className="recruit-contact-item">
              <span className="recruit-contact-icon">📅</span>
              <span>Applied {candidate.applied_at ? new Date(candidate.applied_at).toLocaleDateString() : '-'}</span>
            </div>
            {candidate.source && (
              <div className="recruit-contact-item">
                <span className="recruit-contact-icon">📍</span>
                <span>Source: {candidate.source === 'retr' ? <span className="mm-badge mm-badge-info">RETR</span> : candidate.source}</span>
              </div>
            )}
          </div>
        </div>

        {/* Production Stats */}
        <div className="recruit-hero-stats">
          <div className="recruit-stat-group">
            <h4>Production</h4>
            <div className="recruit-stats-row">
              <div className="recruit-stat">
                <span className="recruit-stat-value" style={{ color: '#22c55e' }}>
                  {formatCurrency(candidate.production?.annual_volume)}
                </span>
                <span className="recruit-stat-label">Annual Volume</span>
              </div>
              <div className="recruit-stat">
                <span className="recruit-stat-value">
                  {candidate.production?.annual_units || 0}
                </span>
                <span className="recruit-stat-label">Units</span>
              </div>
              <div className="recruit-stat">
                <span className="recruit-stat-value">
                  {formatCurrency(candidate.production?.avg_loan_size || (candidate.production?.annual_volume && candidate.production?.annual_units ? candidate.production.annual_volume / candidate.production.annual_units : 0))}
                </span>
                <span className="recruit-stat-label">Avg Loan</span>
              </div>
              <div className="recruit-stat">
                <span className="recruit-stat-value">
                  {candidate.experience?.years_mortgage || candidate.experience?.years_total || 0}
                </span>
                <span className="recruit-stat-label">Yrs Exp</span>
              </div>
            </div>
          </div>
        </div>

        {/* Scores */}
        <div className="recruit-hero-scores">
          <h4>Assessment Scores</h4>
          <div className="recruit-scores-grid">
            <div className="recruit-score-main">
              <div
                className="recruit-score-circle"
                style={{ borderColor: getScoreColor(candidate.scores?.overall) }}
              >
                <span className="recruit-score-value" style={{ color: getScoreColor(candidate.scores?.overall) }}>
                  {getOverallScoreDisplay()}
                </span>
                <span className="recruit-score-label">Overall</span>
              </div>
            </div>
            <div className="recruit-score-details">
              <div className="recruit-score-item">
                <span className="recruit-score-name">Culture Fit</span>
                <span className="recruit-score-bar">
                  <span
                    className="recruit-score-fill"
                    style={{
                      width: `${(candidate.scores?.culture_fit || 0) * 10}%`,
                      backgroundColor: getScoreColor(candidate.scores?.culture_fit)
                    }}
                  />
                </span>
                <span className="recruit-score-num">{candidate.scores?.culture_fit?.toFixed(1) || '-'}</span>
              </div>
              <div className="recruit-score-item">
                <span className="recruit-score-name">Technical</span>
                <span className="recruit-score-bar">
                  <span
                    className="recruit-score-fill"
                    style={{
                      width: `${(candidate.scores?.technical || 0) * 10}%`,
                      backgroundColor: getScoreColor(candidate.scores?.technical)
                    }}
                  />
                </span>
                <span className="recruit-score-num">{candidate.scores?.technical?.toFixed(1) || '-'}</span>
              </div>
              <div className="recruit-score-item">
                <span className="recruit-score-name">Behavioral</span>
                <span className="recruit-score-bar">
                  <span
                    className="recruit-score-fill"
                    style={{
                      width: `${(candidate.scores?.behavioral || 0) * 10}%`,
                      backgroundColor: getScoreColor(candidate.scores?.behavioral)
                    }}
                  />
                </span>
                <span className="recruit-score-num">{candidate.scores?.behavioral?.toFixed(1) || '-'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="recruit-tabs">
        <button
          className={`recruit-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`recruit-tab ${activeTab === 'assessment' ? 'active' : ''}`}
          onClick={() => setActiveTab('assessment')}
        >
          Assessment & Grading
        </button>
      </div>

      {/* Main Body - 3 Column Layout (Overview Tab) */}
      {activeTab === 'overview' && (
      <div className="recruit-body-grid">
        {/* Left Column - Recruiting Pipeline */}
        <div className="recruit-body-section recruit-pipeline-section">
          <div className="recruit-section-header">
            <h3>Recruiting Pipeline</h3>
          </div>

          {/* Pipeline Tracker */}
          <div className="recruit-pipeline-tracker">
            {PIPELINE_STAGES.map((stage, index) => {
              const stageInfo = CANDIDATE_STATUSES.find(s => s.value === stage);
              const currentIndex = getCurrentStageIndex();
              const isCompleted = currentIndex > index;
              const isCurrent = currentIndex === index;
              const isTerminal = ['rejected', 'withdrawn'].includes(candidate.status);

              return (
                <div
                  key={stage}
                  className={`recruit-pipeline-step ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''} ${isTerminal && isCurrent ? 'terminal' : ''}`}
                  onClick={() => handleStatusChange(stage)}
                >
                  <div
                    className="recruit-step-marker"
                    style={{
                      backgroundColor: isCompleted || isCurrent ? stageInfo?.color : '#e5e7eb',
                      borderColor: isCurrent ? stageInfo?.color : 'transparent'
                    }}
                  >
                    {isCompleted ? '✓' : stageInfo?.icon || (index + 1)}
                  </div>
                  <span className="recruit-step-label">{stageInfo?.label}</span>
                  {index < PIPELINE_STAGES.length - 1 && (
                    <div className={`recruit-step-connector ${isCompleted ? 'completed' : ''}`} />
                  )}
                </div>
              );
            })}
          </div>

          {/* Terminal Status Warning */}
          {['rejected', 'withdrawn'].includes(candidate.status) && (
            <div className="recruit-terminal-status">
              <span className="recruit-terminal-icon">
                {candidate.status === 'rejected' ? '❌' : '🚫'}
              </span>
              <span>
                Candidate was {candidate.status === 'rejected' ? 'rejected' : 'withdrawn'}
              </span>
            </div>
          )}

          {/* Interview History */}
          <div className="recruit-interviews-section">
            <h4>Interview History</h4>
            {!candidate.interviews?.length ? (
              <p className="recruit-empty-text">No interviews scheduled yet</p>
            ) : (
              <div className="recruit-interviews-list">
                {candidate.interviews.map((interview) => (
                  <div key={interview.id} className="recruit-interview-item">
                    <div className="recruit-interview-header">
                      <span className="recruit-interview-round">Round {interview.round}</span>
                      <span
                        className="recruit-interview-status"
                        style={{
                          backgroundColor: interview.status === 'completed' ? '#dcfce7' :
                                          interview.status === 'scheduled' ? '#dbeafe' : '#f3f4f6',
                          color: interview.status === 'completed' ? '#16a34a' :
                                interview.status === 'scheduled' ? '#1d4ed8' : '#6b7280'
                        }}
                      >
                        {interview.status}
                      </span>
                    </div>
                    <div className="recruit-interview-details">
                      <span>{interview.type}</span>
                      <span>{interview.scheduled_at ? new Date(interview.scheduled_at).toLocaleDateString() : '-'}</span>
                      {interview.score && <span className="recruit-interview-score">Score: {interview.score.toFixed(1)}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Middle Column - Social Media */}
        <div className="recruit-body-section recruit-social-section">
          <div className="recruit-section-header">
            <h3>Social Media</h3>
            <button className="mm-btn mm-btn-small mm-btn-secondary" onClick={() => setShowEditSocial(true)}>
              Edit
            </button>
          </div>

          <div className="recruit-social-grid">
            {/* LinkedIn */}
            <a
              href={candidate.social_media?.linkedin || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className={`recruit-social-card ${candidate.social_media?.linkedin ? 'connected' : 'not-connected'}`}
            >
              <div className="recruit-social-icon linkedin">in</div>
              <span className="recruit-social-name">LinkedIn</span>
              <span className="recruit-social-status">
                {candidate.social_media?.linkedin ? 'View Profile' : 'Not Connected'}
              </span>
            </a>

            {/* Facebook */}
            <a
              href={candidate.social_media?.facebook || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className={`recruit-social-card ${candidate.social_media?.facebook ? 'connected' : 'not-connected'}`}
            >
              <div className="recruit-social-icon facebook">f</div>
              <span className="recruit-social-name">Facebook</span>
              <span className="recruit-social-status">
                {candidate.social_media?.facebook ? 'View Profile' : 'Not Connected'}
              </span>
            </a>

            {/* Instagram */}
            <a
              href={candidate.social_media?.instagram || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className={`recruit-social-card ${candidate.social_media?.instagram ? 'connected' : 'not-connected'}`}
            >
              <div className="recruit-social-icon instagram">ig</div>
              <span className="recruit-social-name">Instagram</span>
              <span className="recruit-social-status">
                {candidate.social_media?.instagram ? 'View Profile' : 'Not Connected'}
              </span>
            </a>

            {/* Twitter */}
            <a
              href={candidate.social_media?.twitter || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className={`recruit-social-card ${candidate.social_media?.twitter ? 'connected' : 'not-connected'}`}
            >
              <div className="recruit-social-icon twitter">X</div>
              <span className="recruit-social-name">Twitter/X</span>
              <span className="recruit-social-status">
                {candidate.social_media?.twitter ? 'View Profile' : 'Not Connected'}
              </span>
            </a>
          </div>

          {/* Recent Social Posts */}
          {candidate.social_media?.recent_posts?.length > 0 && (
            <div className="recruit-recent-posts">
              <h4>Recent Activity</h4>
              {candidate.social_media.recent_posts.slice(0, 3).map((post, idx) => (
                <div key={idx} className="recruit-post-item">
                  <div className="recruit-post-header">
                    <span className="mm-badge">{post.platform}</span>
                    <span className="recruit-post-date">{new Date(post.posted_at).toLocaleDateString()}</span>
                  </div>
                  <p className="recruit-post-content">{post.content}</p>
                  {post.engagement && (
                    <div className="recruit-post-engagement">
                      <span>👍 {post.engagement.likes || 0}</span>
                      <span>💬 {post.engagement.comments || 0}</span>
                      <span>🔄 {post.engagement.shares || 0}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Column - Quick Actions + Notes */}
        <div className="recruit-body-section recruit-notes-section">
          {/* Quick Actions */}
          <div className="recruit-quick-actions">
            <div className="recruit-section-header">
              <h3>Quick Actions</h3>
            </div>
            <div className="recruit-quick-actions-grid">
              <button
                className="recruit-quick-action-btn"
                onClick={handleClickToCall}
                disabled={!candidate.phone || isCallInProgress}
              >
                <span className="recruit-quick-action-icon">📞</span>
                <span>{isCallInProgress ? 'Calling...' : 'Call'}</span>
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => window.open(`mailto:${candidate.email}`, '_blank')}
                disabled={!candidate.email}
              >
                <span className="recruit-quick-action-icon">✉️</span>
                <span>Email</span>
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => setShowScheduleInterviewModal(true)}
              >
                <span className="recruit-quick-action-icon">📅</span>
                <span>Schedule Interview</span>
              </button>
              <button
                className="recruit-quick-action-btn recruit-quick-action-video"
                onClick={() => setShowVideoRecorder(true)}
              >
                <span className="recruit-quick-action-icon">🎬</span>
                <span>Record Video</span>
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => handleStatusChange('offer')}
                disabled={candidate.status === 'offer' || candidate.status === 'hired'}
              >
                <span className="recruit-quick-action-icon">📝</span>
                <span>Make Offer</span>
              </button>
              <button
                className="recruit-quick-action-btn recruit-quick-action-danger"
                onClick={() => handleStatusChange('rejected')}
                disabled={candidate.status === 'rejected' || candidate.status === 'hired'}
              >
                <span className="recruit-quick-action-icon">❌</span>
                <span>Reject</span>
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => handleStatusChange('hired')}
                disabled={candidate.status === 'hired'}
              >
                <span className="recruit-quick-action-icon">✅</span>
                <span>Mark Hired</span>
              </button>
            </div>
          </div>

          <div className="recruit-section-header">
            <h3>Notes & Activity</h3>
          </div>

          {/* Add Note */}
          <div className="recruit-add-note">
            <textarea
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              placeholder="Add a note about this candidate..."
              className="mm-textarea"
              rows="3"
            />
            <button
              className="mm-btn mm-btn-primary mm-btn-small"
              onClick={handleAddNote}
              disabled={!newNote.trim()}
            >
              Add Note
            </button>
          </div>

          {/* Notes List */}
          <div className="recruit-notes-list">
            {candidate.notes?.map((note) => (
              <div key={note.id} className="recruit-note-item">
                <p className="recruit-note-content">{note.content}</p>
                <span className="recruit-note-date">
                  {note.created_at ? new Date(note.created_at).toLocaleString() : ''}
                </span>
              </div>
            ))}
            {!candidate.notes?.length && (
              <p className="recruit-empty-text">No notes yet</p>
            )}
          </div>

          {/* Activity Timeline */}
          {candidate.activities?.length > 0 && (
            <div className="recruit-activity-timeline">
              <h4>Activity</h4>
              {candidate.activities.slice(0, 5).map((activity) => (
                <div key={activity.id} className="recruit-activity-item">
                  <div className="recruit-activity-marker" />
                  <div className="recruit-activity-content">
                    <span className="mm-badge">{activity.type}</span>
                    <p>{activity.description}</p>
                    <span className="recruit-activity-date">
                      {activity.timestamp ? new Date(activity.timestamp).toLocaleString() : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      )}

      {/* Assessment & Grading Tab */}
      {activeTab === 'assessment' && (
        <div className="recruit-assessment-tab">
          {assessmentLoading ? (
            <div className="mm-loading">
              <div className="mm-spinner"></div>
              <p>Loading Assessment...</p>
            </div>
          ) : assessmentError ? (
            <div className="mm-error">
              <span>{assessmentError}</span>
              <button onClick={loadAssessment}>Retry</button>
            </div>
          ) : (
            <div className="recruit-assessment-content">
              {/* Top Row - Overall Grade + Category Scores */}
              <div className="recruit-assessment-header">
                {/* Overall Grade Circle */}
                <div className="recruit-assessment-overall">
                  <CandidateGradeCircle
                    score={assessment?.overall_score}
                    grade={assessment?.overall_grade}
                    label="Overall Grade"
                    size="xl"
                  />
                  {assessment?.assessed_at && (
                    <p className="recruit-assessment-date">
                      Last assessed: {new Date(assessment.assessed_at).toLocaleDateString()}
                    </p>
                  )}
                </div>

                {/* Category Scores Summary */}
                <div className="recruit-assessment-categories">
                  <h4>Category Scores</h4>
                  <AssessmentScoreSummary assessment={assessment} />
                </div>
              </div>

              {/* Middle Row - DISC Profile + Detailed Scores */}
              <div className="recruit-assessment-middle">
                {/* DISC Profile Chart */}
                <div className="recruit-assessment-disc">
                  <div className="recruit-section-header">
                    <h3>DISC Personality Profile</h3>
                  </div>
                  {assessment?.disc ? (
                    <DISCProfileChart
                      scores={{
                        d: assessment.disc.d_score,
                        i: assessment.disc.i_score,
                        s: assessment.disc.s_score,
                        c: assessment.disc.c_score,
                      }}
                      primaryStyle={assessment.disc.primary_style}
                      secondaryStyle={assessment.disc.secondary_style}
                      showIdealProfile={true}
                    />
                  ) : (
                    <div className="recruit-empty-disc">
                      <p>No DISC assessment data available</p>
                      <p className="recruit-empty-hint">Run AI Analysis to assess personality profile</p>
                    </div>
                  )}
                </div>

                {/* Detailed Score Cards */}
                <div className="recruit-assessment-details">
                  <div className="recruit-section-header">
                    <h3>Score Breakdown</h3>
                  </div>
                  <AssessmentScoreGrid
                    assessment={assessment}
                    isEditable={true}
                    onEditCategory={(category) => {
                      setEditingCategory(category);
                      setShowEditCategoryModal(true);
                    }}
                  />
                </div>
              </div>

              {/* Bottom Row - Strengths/Weaknesses + AI Analysis */}
              <div className="recruit-assessment-bottom">
                {/* Strengths */}
                <div className="recruit-assessment-strengths">
                  <div className="recruit-section-header">
                    <h3>Strengths</h3>
                  </div>
                  <div className="recruit-traits-list">
                    {assessment?.strengths?.length > 0 ? (
                      assessment.strengths.map((strength, idx) => (
                        <div key={idx} className="recruit-trait-item strength">
                          <span className="recruit-trait-icon">+</span>
                          <span>{strength}</span>
                        </div>
                      ))
                    ) : (
                      <p className="recruit-empty-text">No strengths identified yet</p>
                    )}
                  </div>
                </div>

                {/* Weaknesses */}
                <div className="recruit-assessment-weaknesses">
                  <div className="recruit-section-header">
                    <h3>Areas for Development</h3>
                  </div>
                  <div className="recruit-traits-list">
                    {assessment?.weaknesses?.length > 0 ? (
                      assessment.weaknesses.map((weakness, idx) => (
                        <div key={idx} className="recruit-trait-item weakness">
                          <span className="recruit-trait-icon">-</span>
                          <span>{weakness}</span>
                        </div>
                      ))
                    ) : (
                      <p className="recruit-empty-text">No development areas identified yet</p>
                    )}
                  </div>
                </div>

                {/* AI Analysis Panel */}
                <div className="recruit-assessment-ai">
                  <AIAnalysisPanel
                    candidateId={candidateId}
                    candidateName={candidate?.name}
                    currentAssessment={assessment}
                    onApplyScores={async (scores) => {
                      try {
                        // Update assessment with AI-suggested scores
                        await updateAssessment(candidateId, scores, currentUserId || 1);
                        await loadAssessment();
                      } catch (err) {
                        setAssessmentError(err.message);
                      }
                    }}
                    onRefresh={loadAssessment}
                  />
                </div>
              </div>

              {/* No Assessment State */}
              {!assessment && (
                <div className="recruit-no-assessment">
                  <div className="recruit-no-assessment-content">
                    <span className="recruit-no-assessment-icon">📋</span>
                    <h3>No Assessment Yet</h3>
                    <p>This candidate hasn't been assessed. Create an assessment to start grading.</p>
                    <button
                      className="mm-btn mm-btn-primary"
                      onClick={async () => {
                        try {
                          await createAssessment(candidateId, {}, currentUserId || 1);
                          loadAssessment();
                        } catch (err) {
                          setAssessmentError(err.message);
                        }
                      }}
                    >
                      Create Assessment
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Edit Social Media Modal */}
      {showEditSocial && (
        <div className="mm-modal-overlay">
          <div className="mm-modal">
            <h3>Edit Social Media</h3>
            <div className="mm-form-group">
              <label>LinkedIn URL</label>
              <input
                type="url"
                value={socialForm.linkedin_url}
                onChange={(e) => setSocialForm({ ...socialForm, linkedin_url: e.target.value })}
                className="mm-input"
                placeholder="https://linkedin.com/in/..."
              />
            </div>
            <div className="mm-form-group">
              <label>Facebook URL</label>
              <input
                type="url"
                value={socialForm.facebook_url}
                onChange={(e) => setSocialForm({ ...socialForm, facebook_url: e.target.value })}
                className="mm-input"
                placeholder="https://facebook.com/..."
              />
            </div>
            <div className="mm-form-group">
              <label>Instagram URL</label>
              <input
                type="url"
                value={socialForm.instagram_url}
                onChange={(e) => setSocialForm({ ...socialForm, instagram_url: e.target.value })}
                className="mm-input"
                placeholder="https://instagram.com/..."
              />
            </div>
            <div className="mm-form-group">
              <label>Twitter/X URL</label>
              <input
                type="url"
                value={socialForm.twitter_url}
                onChange={(e) => setSocialForm({ ...socialForm, twitter_url: e.target.value })}
                className="mm-input"
                placeholder="https://twitter.com/..."
              />
            </div>
            <div className="mm-modal-actions">
              <button className="mm-btn mm-btn-secondary" onClick={() => setShowEditSocial(false)}>
                Cancel
              </button>
              <button className="mm-btn mm-btn-primary" onClick={handleSaveSocial}>
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Production Modal */}
      {showEditProduction && (
        <div className="mm-modal-overlay">
          <div className="mm-modal">
            <h3>Edit Production Data</h3>
            <div className="mm-form-row">
              <div className="mm-form-group">
                <label>Annual Volume ($)</label>
                <input
                  type="number"
                  value={productionForm.annual_volume}
                  onChange={(e) => setProductionForm({ ...productionForm, annual_volume: e.target.value })}
                  className="mm-input"
                  placeholder="50000000"
                />
              </div>
              <div className="mm-form-group">
                <label>Annual Units</label>
                <input
                  type="number"
                  value={productionForm.annual_units}
                  onChange={(e) => setProductionForm({ ...productionForm, annual_units: e.target.value })}
                  className="mm-input"
                  placeholder="100"
                />
              </div>
            </div>
            <div className="mm-form-group">
              <label>NMLS ID</label>
              <input
                type="text"
                value={productionForm.nmls_id}
                onChange={(e) => setProductionForm({ ...productionForm, nmls_id: e.target.value })}
                className="mm-input"
                placeholder="12345678"
              />
            </div>
            <div className="mm-form-row">
              <div className="mm-form-group">
                <label>Current Company</label>
                <input
                  type="text"
                  value={productionForm.current_company}
                  onChange={(e) => setProductionForm({ ...productionForm, current_company: e.target.value })}
                  className="mm-input"
                  placeholder="Premier Mortgage"
                />
              </div>
              <div className="mm-form-group">
                <label>Current Title</label>
                <input
                  type="text"
                  value={productionForm.current_title}
                  onChange={(e) => setProductionForm({ ...productionForm, current_title: e.target.value })}
                  className="mm-input"
                  placeholder="Senior Loan Officer"
                />
              </div>
            </div>
            <div className="mm-modal-actions">
              <button className="mm-btn mm-btn-secondary" onClick={() => setShowEditProduction(false)}>
                Cancel
              </button>
              <button className="mm-btn mm-btn-primary" onClick={handleSaveProduction}>
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Assessment Quiz Modal */}
      <AssessmentQuizModal
        isOpen={showQuizModal}
        onClose={handleQuizClose}
        candidateId={parseInt(candidateId)}
        candidateName={`${candidate?.first_name || ''} ${candidate?.last_name || ''}`}
        disposition={pendingStatusChange}
        onQuizComplete={handleQuizComplete}
      />

      {/* Call Notes Modal */}
      {showCallNotesModal && (
        <CallNotesModal
          candidateName={`${candidate?.first_name || ''} ${candidate?.last_name || ''}`}
          onSave={handleSaveCallNotes}
          onClose={() => {
            setShowCallNotesModal(false);
            setActiveCallId(null);
          }}
        />
      )}

      {/* Schedule Interview Modal */}
      {showScheduleInterviewModal && (
        <ScheduleInterviewModal
          isOpen={showScheduleInterviewModal}
          onClose={() => setShowScheduleInterviewModal(false)}
          candidate={candidate}
          onSuccess={async (interviewData) => {
            try {
              await scheduleInterview(candidateId, interviewData);
              setShowScheduleInterviewModal(false);
              loadCandidate(); // Refresh to show updated interview info
            } catch (err) {
              setError(err.message);
            }
          }}
        />
      )}

      {/* Edit Score Category Modal */}
      {showEditCategoryModal && editingCategory && (
        <EditScoreCategoryModal
          isOpen={showEditCategoryModal}
          onClose={() => {
            setShowEditCategoryModal(false);
            setEditingCategory(null);
          }}
          category={editingCategory}
          currentScore={assessment?.scores?.[editingCategory.key]}
          onSave={async (score, notes) => {
            try {
              const updatedScores = {
                ...assessment?.scores,
                [editingCategory.key]: score
              };
              await updateAssessment(candidateId, { scores: updatedScores }, currentUserId || 1);
              await loadAssessment();
              setShowEditCategoryModal(false);
              setEditingCategory(null);
            } catch (err) {
              setAssessmentError(err.message);
            }
          }}
        />
      )}

      {/* Video Recorder Modal */}
      {showVideoRecorder && (
        <VideoRecorder
          candidateId={parseInt(candidateId)}
          candidateName={`${candidate?.first_name || ''} ${candidate?.last_name || ''}`.trim() || candidate?.name}
          onVideoSent={(result) => {
            console.log('Video sent successfully:', result);
            // Could add a toast notification here
          }}
          onClose={() => setShowVideoRecorder(false)}
        />
      )}
    </div>
  );
};

// Call Notes Modal Component
const CallNotesModal = ({ candidateName, onSave, onClose }) => {
  const [note, setNote] = useState('');
  const [outcome, setOutcome] = useState('answered');
  const [callbackRequested, setCallbackRequested] = useState(false);
  const [callbackDate, setCallbackDate] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(note, outcome, callbackRequested, callbackDate);
  };

  return (
    <div className="call-notes-modal" onClick={onClose}>
      <div className="call-notes-content" onClick={e => e.stopPropagation()}>
        <h3>Call with {candidateName}</h3>
        <form className="call-notes-form" onSubmit={handleSubmit}>
          <div>
            <label>Call Outcome</label>
            <select value={outcome} onChange={e => setOutcome(e.target.value)}>
              <option value="answered">Answered - Spoke with candidate</option>
              <option value="voicemail">Left Voicemail</option>
              <option value="no_answer">No Answer</option>
              <option value="busy">Busy</option>
              <option value="callback">Callback Requested</option>
            </select>
          </div>

          <div>
            <label>Notes</label>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Enter call notes..."
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input
              type="checkbox"
              id="callbackRequested"
              checked={callbackRequested}
              onChange={e => setCallbackRequested(e.target.checked)}
            />
            <label htmlFor="callbackRequested" style={{ margin: 0, cursor: 'pointer' }}>
              Schedule callback
            </label>
          </div>

          {callbackRequested && (
            <div>
              <label>Callback Date & Time</label>
              <input
                type="datetime-local"
                value={callbackDate}
                onChange={e => setCallbackDate(e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: '1px solid #d1d5db',
                  borderRadius: '8px',
                  fontSize: '14px'
                }}
              />
            </div>
          )}

          <div className="call-notes-actions">
            <button type="button" className="mm-btn mm-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="mm-btn mm-btn-primary">
              Save Notes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default RecruitDetail;
