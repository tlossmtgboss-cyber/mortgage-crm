import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from '../../utils/toast';
import { getCurrentUserId } from '../../utils/auth';
import {
  getCandidateFullProfile,
  updateCandidateStatus,
  updateCandidateProduction,
  updateCandidateBasicInfo,
  addCandidateNote,
  scheduleInterview,
  createCandidatePortalWorkspace
} from '../../services/masterManagerApi';
import {
  getCandidateAssessment,
  createAssessment,
  updateAssessment,
  getAssessmentHistory
} from '../../services/candidateGradingApi';
import CandidateGradeCircle, { getGrade, GradeBadge } from '../../components/recruiting/CandidateGradeCircle';
import DISCProfileChart from '../../components/recruiting/DISCProfileChart';
import { DISCResultsSummary, DISCGraphs, DISCWheel, MotivatorsBarchart } from '../../components/recruiting/disc';
import * as discApi from '../../services/discApi';
import { AssessmentScoreGrid, AssessmentScoreSummary } from '../../components/recruiting/AssessmentScoreCard';
import AIAnalysisPanel from '../../components/recruiting/AIAnalysisPanel';
import AssessmentQuizModal from '../../components/recruiting/AssessmentQuizModal';
import ScheduleInterviewModal from '../../components/recruiting/ScheduleInterviewModal';
import EditScoreCategoryModal from '../../components/recruiting/EditScoreCategoryModal';
import VideoRecorder from '../../components/recruiting/VideoRecorder';
import { usePermissions } from '../../contexts/PermissionContext';
import SMSAccordionPanel from '../../components/sms/SMSAccordionPanel';
import './MasterManager.css';
import './RecruitDetail.css';
import { getToken } from '../../utils/tokenStore';

// Dispositions that require quiz completion
const QUIZ_REQUIRED_DISPOSITIONS = ['screening', 'phone_screen', 'interview', 'assessment', 'offer'];

const CANDIDATE_STATUSES = [
  { value: 'new', label: 'New', color: '#3b82f6', icon: '📥' },
  { value: 'screening', label: 'Screening', color: '#B8924A', icon: '🔍' },
  { value: 'phone_screen', label: 'Phone Screen', color: '#C9A44E', icon: '📞' },
  { value: 'interview', label: 'Interview', color: '#f59e0b', icon: '🎯' },
  { value: 'assessment', label: 'Assessment', color: '#eab308', icon: '📋' },
  { value: 'offer', label: 'Offer', color: '#22c55e', icon: '📝' },
  { value: 'hired', label: 'Hired', color: '#2D7A52', icon: '✅' },
  { value: 'rejected', label: 'Rejected', color: '#ef4444', icon: '❌' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#6b7280', icon: '🚫' }
];

// Pipeline stages in order (excluding terminal states)
const PIPELINE_STAGES = ['new', 'screening', 'phone_screen', 'interview', 'assessment', 'offer', 'hired'];

// Get user ID from localStorage (set at login) — no JWT decoding needed
const getUserIdFromToken = getCurrentUserId;

const RecruitDetail = () => {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const { currentUserId } = usePermissions();
  const [candidate, setCandidate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showEditProduction, setShowEditProduction] = useState(false);
  const [newNote, setNewNote] = useState('');
  const [activeTab, setActiveTab] = useState('overview');

  // Assessment state
  const [assessment, setAssessment] = useState(null);
  const [assessmentLoading, setAssessmentLoading] = useState(false);
  const [assessmentError, setAssessmentError] = useState(null);

  // DISC + Motivators state
  const [discResults, setDiscResults] = useState(null);
  const [motivatorResults, setMotivatorResults] = useState(null);
  const [discLoading, setDiscLoading] = useState(false);
  const [showDISCInviteModal, setShowDISCInviteModal] = useState(false);

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

  // Escalate modal state
  const [showEscalateModal, setShowEscalateModal] = useState(false);
  const [escalateUsers, setEscalateUsers] = useState([]);
  const [selectedEscalateUser, setSelectedEscalateUser] = useState('');
  const [escalateNote, setEscalateNote] = useState('');

  // Video recorder modal state
  const [showVideoRecorder, setShowVideoRecorder] = useState(false);

  // Edit form states
  const [recruitForm, setRecruitForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
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
      setRecruitForm({
        first_name: data.first_name || '',
        last_name: data.last_name || '',
        email: data.email || '',
        phone: data.phone || '',
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

  // Load DISC + Motivators results
  const loadDISCResults = useCallback(async () => {
    try {
      setDiscLoading(true);
      const results = await discApi.getDISCResults(candidateId);
      if (results) {
        setDiscResults(results.disc);
        setMotivatorResults(results.motivators);
      }
    } catch (err) {
      // 404 means no DISC assessment yet - that's okay
      console.log('No DISC results yet:', err.message);
    } finally {
      setDiscLoading(false);
    }
  }, [candidateId]);

  // Send DISC assessment invite
  const handleSendDISCInvite = async () => {
    try {
      await discApi.sendAssessmentInvite(candidateId, { sendEmail: true });
      setShowDISCInviteModal(false);
      // Show success toast or message
    } catch (err) {
      console.error('Failed to send DISC invite:', err);
    }
  };

  // Download DISC PDF report
  const handleDownloadDISCPDF = async () => {
    try {
      await discApi.downloadDISCReport(candidateId);
    } catch (err) {
      console.error('Failed to download DISC report:', err);
    }
  };

  useEffect(() => {
    loadCandidate();
  }, [loadCandidate]);

  // Load assessment and DISC on component mount (for sidebar display)
  useEffect(() => {
    if (!assessment && !assessmentLoading) {
      loadAssessment();
    }
    if (!discResults && !discLoading) {
      loadDISCResults();
    }
  }, [candidateId]); // eslint-disable-line react-hooks/exhaustive-deps

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
        const token = getToken();
        const userId = getUserIdFromToken();
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
              assigned_to: userId
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

  // Load users for escalation
  const loadEscalateUsers = async () => {
    const token = getToken();
    const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';
    try {
      const response = await fetch(`${API_URL}/api/v1/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setEscalateUsers(data.users || data || []);
      }
    } catch (err) {
      console.error('Failed to load users for escalation:', err);
    }
  };

  // Handle escalation
  const handleEscalate = async () => {
    if (!selectedEscalateUser) {
      setError('Please select a user to escalate to');
      return;
    }

    const token = getToken();
    const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

    try {
      const response = await fetch(`${API_URL}/api/v1/recruiting/candidates/${candidateId}/escalate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          assigned_to: parseInt(selectedEscalateUser),
          note: escalateNote
        })
      });

      if (response.ok) {
        setShowEscalateModal(false);
        setSelectedEscalateUser('');
        setEscalateNote('');
        loadCandidate(); // Refresh candidate data
      } else {
        const err = await response.json();
        setError(err.detail || 'Failed to escalate candidate');
      }
    } catch (err) {
      setError('Failed to escalate candidate');
    }
  };

  // Click-to-call handler
  const handleClickToCall = async () => {
    if (!candidate?.phone) {
      setError('No phone number available for this candidate');
      return;
    }

    setIsCallInProgress(true);
    const token = getToken();
    const userId = getUserIdFromToken();
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
        // In a real implementation, this would trigger the actual Telnyx call
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
    const token = getToken();
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

    const token = getToken();
    const userId = getUserIdFromToken();
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

  const handleSaveRecruit = async () => {
    try {
      // Update basic info
      await updateCandidateBasicInfo(candidateId, {
        first_name: recruitForm.first_name,
        last_name: recruitForm.last_name,
        email: recruitForm.email,
        phone: recruitForm.phone
      });
      // Update production data
      await updateCandidateProduction(candidateId, {
        annual_volume: recruitForm.annual_volume,
        annual_units: recruitForm.annual_units,
        nmls_id: recruitForm.nmls_id,
        current_company: recruitForm.current_company,
        current_title: recruitForm.current_title
      });
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

  // Calculate overall score display from assessment data
  const getOverallScoreDisplay = () => {
    if (assessment?.overall?.score) {
      return assessment.overall.score.toFixed(1);
    }
    return '-';
  };

  // Get overall grade letter
  const getOverallGradeDisplay = () => {
    return assessment?.overall?.grade || '-';
  };

  // Color based on 0-100 score scale
  const getScoreColor = (score) => {
    if (!score && score !== 0) return '#6b7280';
    if (score >= 80) return '#2D7A52'; // Green - B+ and above
    if (score >= 60) return '#f59e0b'; // Yellow - C to B
    if (score >= 40) return '#ef4444'; // Red - D to C-
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
            Edit Recruit
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
            <div className="recruit-contact-item">
              <span className="recruit-contact-icon">📱</span>
              <a href={`tel:${candidate.phone}`}>{candidate.phone || '-'}</a>
            </div>
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
                style={{ borderColor: getScoreColor(assessment?.overall?.score) }}
              >
                <span className="recruit-score-value" style={{ color: getScoreColor(assessment?.overall?.score) }}>
                  {getOverallGradeDisplay()}
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
                      width: `${assessment?.culture_fit?.score || 0}%`,
                      backgroundColor: getScoreColor(assessment?.culture_fit?.score)
                    }}
                  />
                </span>
                <span className="recruit-score-num">{assessment?.culture_fit?.score?.toFixed(0) || '-'}</span>
              </div>
              <div className="recruit-score-item">
                <span className="recruit-score-name">Skills</span>
                <span className="recruit-score-bar">
                  <span
                    className="recruit-score-fill"
                    style={{
                      width: `${assessment?.skills?.score || 0}%`,
                      backgroundColor: getScoreColor(assessment?.skills?.score)
                    }}
                  />
                </span>
                <span className="recruit-score-num">{assessment?.skills?.score?.toFixed(0) || '-'}</span>
              </div>
              <div className="recruit-score-item">
                <span className="recruit-score-name">Character</span>
                <span className="recruit-score-bar">
                  <span
                    className="recruit-score-fill"
                    style={{
                      width: `${assessment?.character?.score || 0}%`,
                      backgroundColor: getScoreColor(assessment?.character?.score)
                    }}
                  />
                </span>
                <span className="recruit-score-num">{assessment?.character?.score?.toFixed(0) || '-'}</span>
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
          className={`recruit-tab ${activeTab === 'pipeline' ? 'active' : ''}`}
          onClick={() => setActiveTab('pipeline')}
        >
          Pipeline
        </button>
        <button
          className={`recruit-tab ${activeTab === 'interviews' ? 'active' : ''}`}
          onClick={() => setActiveTab('interviews')}
        >
          Interviews
        </button>
        <button
          className={`recruit-tab ${activeTab === 'notes' ? 'active' : ''}`}
          onClick={() => setActiveTab('notes')}
        >
          Notes
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

        {/* Center Column - AI Recruiting Agent */}
        <div className="recruit-body-section recruit-ai-section">
          <div className="recruit-section-header">
            <h3>AI Recruiting Agent</h3>
          </div>
          <div className="recruit-ai-content">
            <div className="recruit-ai-status">
              <div className="recruit-ai-avatar">
                <span>🤖</span>
              </div>
              <div className="recruit-ai-info">
                <span className="recruit-ai-label">Agent Status</span>
                <span className="recruit-ai-status-badge active">Active</span>
              </div>
            </div>

            <div className="recruit-ai-instructions">
              <h4>Next Steps</h4>
              <div className="recruit-ai-task-list">
                {candidate.status === 'new' && (
                  <>
                    <button
                      className="recruit-ai-task"
                      onClick={handleClickToCall}
                      disabled={!candidate.phone || isCallInProgress}
                    >
                      <span className="recruit-ai-task-icon">📞</span>
                      <div className="recruit-ai-task-content">
                        <strong>Initial Contact</strong>
                        <p>Make first contact call to introduce yourself and gauge interest</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                    <button
                      className="recruit-ai-task"
                      onClick={() => setShowEditProduction(true)}
                    >
                      <span className="recruit-ai-task-icon">📋</span>
                      <div className="recruit-ai-task-content">
                        <strong>Review Profile</strong>
                        <p>Review production history and social media presence</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                  </>
                )}
                {candidate.status === 'screening' && (
                  <>
                    <button
                      className="recruit-ai-task"
                      onClick={() => setShowEditProduction(true)}
                    >
                      <span className="recruit-ai-task-icon">📊</span>
                      <div className="recruit-ai-task-content">
                        <strong>Verify Production</strong>
                        <p>Confirm annual volume and units with NMLS lookup</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                    <button
                      className="recruit-ai-task"
                      onClick={() => setShowScheduleInterviewModal(true)}
                    >
                      <span className="recruit-ai-task-icon">📅</span>
                      <div className="recruit-ai-task-content">
                        <strong>Schedule Phone Screen</strong>
                        <p>Set up 15-minute phone screening call</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                  </>
                )}
                {candidate.status === 'phone_screen' && (
                  <>
                    <button
                      className="recruit-ai-task"
                      onClick={handleClickToCall}
                      disabled={!candidate.phone || isCallInProgress}
                    >
                      <span className="recruit-ai-task-icon">🎯</span>
                      <div className="recruit-ai-task-content">
                        <strong>Complete Phone Screen</strong>
                        <p>Discuss goals, motivations, and interest level</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                    <button
                      className="recruit-ai-task"
                      onClick={() => {
                        setPendingStatusChange('interview');
                        setShowQuizModal(true);
                      }}
                    >
                      <span className="recruit-ai-task-icon">✅</span>
                      <div className="recruit-ai-task-content">
                        <strong>Complete Assessment Quiz</strong>
                        <p>Grade candidate on initial impressions</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                  </>
                )}
                {candidate.status === 'interview' && (
                  <>
                    <button
                      className="recruit-ai-task"
                      onClick={() => setShowScheduleInterviewModal(true)}
                    >
                      <span className="recruit-ai-task-icon">🎥</span>
                      <div className="recruit-ai-task-content">
                        <strong>Schedule Interview</strong>
                        <p>Set up formal interview with hiring manager</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                    <button
                      className="recruit-ai-task"
                      onClick={() => setShowVideoRecorder(true)}
                    >
                      <span className="recruit-ai-task-icon">📝</span>
                      <div className="recruit-ai-task-content">
                        <strong>Send Video Message</strong>
                        <p>Record personalized video to share company culture</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                  </>
                )}
                {candidate.status === 'assessment' && (
                  <>
                    <button
                      className="recruit-ai-task"
                      onClick={() => setActiveTab('assessment')}
                    >
                      <span className="recruit-ai-task-icon">📋</span>
                      <div className="recruit-ai-task-content">
                        <strong>Complete Full Assessment</strong>
                        <p>Fill out all grading categories for final evaluation</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                    <button
                      className="recruit-ai-task"
                      onClick={() => setActiveTab('assessment')}
                    >
                      <span className="recruit-ai-task-icon">🤖</span>
                      <div className="recruit-ai-task-content">
                        <strong>Run AI Analysis</strong>
                        <p>Get AI-powered insights and recommendations</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                  </>
                )}
                {candidate.status === 'offer' && (
                  <>
                    <button
                      className="recruit-ai-task"
                      onClick={() => setActiveTab('assessment')}
                    >
                      <span className="recruit-ai-task-icon">💰</span>
                      <div className="recruit-ai-task-content">
                        <strong>Prepare Offer Package</strong>
                        <p>Generate compensation proposal based on production</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                    <button
                      className="recruit-ai-task"
                      onClick={() => window.open(`mailto:${candidate.email}?subject=Offer%20from%20Perennia`, '_blank')}
                      disabled={!candidate.email}
                    >
                      <span className="recruit-ai-task-icon">📄</span>
                      <div className="recruit-ai-task-content">
                        <strong>Send Offer Letter</strong>
                        <p>Present formal offer and discuss terms</p>
                      </div>
                      <span className="recruit-ai-task-arrow">→</span>
                    </button>
                  </>
                )}
                {candidate.status === 'hired' && (
                  <div className="recruit-ai-success">
                    <span className="recruit-ai-success-icon">🎉</span>
                    <div>
                      <strong>Candidate Hired!</strong>
                      <p>Begin onboarding process</p>
                    </div>
                  </div>
                )}
                {(candidate.status === 'rejected' || candidate.status === 'withdrawn') && (
                  <div className="recruit-ai-closed">
                    <span className="recruit-ai-closed-icon">📁</span>
                    <div>
                      <strong>File Closed</strong>
                      <p>Candidate is no longer active in pipeline</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="recruit-ai-tips">
              <h4>Talking Points</h4>
              <ul>
                <li>Technology stack: Perennia AI platform, automated workflows</li>
                <li>Lead generation: AI-powered prospecting and nurturing</li>
                <li>Compensation: Competitive splits + volume bonuses</li>
                <li>Support: Dedicated ops team, 24/7 processing</li>
              </ul>
            </div>
          </div>
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
                {isCallInProgress ? 'Calling...' : 'Call'}
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => window.open(`mailto:${candidate.email}`, '_blank')}
                disabled={!candidate.email}
              >
                Email
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => setShowScheduleInterviewModal(true)}
              >
                Schedule
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => setShowVideoRecorder(true)}
              >
                Video
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => window.open(`sms:${candidate.phone}`, '_blank')}
                disabled={!candidate.phone}
              >
                SMS
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => handleStatusChange('rejected')}
                disabled={candidate.status === 'rejected' || candidate.status === 'hired'}
              >
                Reject
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={() => setShowEscalateModal(true)}
              >
                Escalate
              </button>
              <button
                className="recruit-quick-action-btn"
                onClick={async () => {
                  // Use the portal slug from the API if available
                  let portalSlug = candidate.portal?.slug;

                  if (!portalSlug) {
                    // No portal exists - create one automatically
                    try {
                      const suggestedSlug = `${candidate.first_name}-${candidate.last_name}`.toLowerCase().replace(/\s+/g, '-');
                      const workspace = await createCandidatePortalWorkspace(candidate.id, suggestedSlug);
                      portalSlug = workspace.slug;
                      // Refresh candidate data to get the new portal info
                      const refreshed = await getCandidateFullProfile(candidate.id);
                      setCandidate(refreshed);
                    } catch (err) {
                      console.error('Failed to create portal workspace:', err);
                      toast.error('Failed to create portal. Please try again.');
                      return;
                    }
                  }

                  if (portalSlug) {
                    window.open(`/join/${portalSlug}`, '_blank');
                  }
                }}
              >
                View Portal
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

      {/* Pipeline Tab */}
      {activeTab === 'pipeline' && (
        <div className="recruit-tab-content">
          <div className="recruit-pipeline-section">
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

            {/* Quick Actions */}
            <div className="recruit-quick-actions" style={{ marginTop: '2rem' }}>
              <div className="recruit-section-header">
                <h3>Quick Actions</h3>
              </div>
              <div className="recruit-quick-actions-grid">
                <button
                  className="recruit-quick-action-btn"
                  onClick={handleClickToCall}
                  disabled={!candidate.phone || isCallInProgress}
                >
                  {isCallInProgress ? 'Calling...' : 'Call'}
                </button>
                <button
                  className="recruit-quick-action-btn"
                  onClick={() => window.open(`mailto:${candidate.email}`, '_blank')}
                  disabled={!candidate.email}
                >
                  Email
                </button>
                <button
                  className="recruit-quick-action-btn"
                  onClick={() => setShowScheduleInterviewModal(true)}
                >
                  Schedule
                </button>
                <button
                  className="recruit-quick-action-btn"
                  onClick={() => setShowVideoRecorder(true)}
                >
                  Video
                </button>
                <button
                  className="recruit-quick-action-btn"
                  onClick={() => window.open(`sms:${candidate.phone}`, '_blank')}
                  disabled={!candidate.phone}
                >
                  SMS
                </button>
                <button
                  className="recruit-quick-action-btn"
                  onClick={() => handleStatusChange('rejected')}
                  disabled={candidate.status === 'rejected' || candidate.status === 'hired'}
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Interviews Tab */}
      {activeTab === 'interviews' && (
        <div className="recruit-tab-content">
          <div className="recruit-interviews-section">
            <div className="recruit-section-header">
              <h3>Interview History</h3>
              <button
                className="mm-btn mm-btn-primary"
                onClick={() => setShowScheduleInterviewModal(true)}
              >
                Schedule Interview
              </button>
            </div>

            {!candidate.interviews?.length ? (
              <div className="recruit-empty-state">
                <span className="recruit-empty-icon">📅</span>
                <p>No interviews scheduled yet</p>
                <button
                  className="mm-btn mm-btn-primary"
                  onClick={() => setShowScheduleInterviewModal(true)}
                >
                  Schedule First Interview
                </button>
              </div>
            ) : (
              <div className="recruit-interviews-list-full">
                {candidate.interviews.map((interview) => (
                  <div key={interview.id} className="recruit-interview-card">
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
                    <div className="recruit-interview-body">
                      <div className="recruit-interview-type">{interview.type}</div>
                      <div className="recruit-interview-date">
                        {interview.scheduled_at ? new Date(interview.scheduled_at).toLocaleString() : '-'}
                      </div>
                      {interview.score && (
                        <div className="recruit-interview-score">
                          Score: <strong>{interview.score.toFixed(1)}</strong>
                        </div>
                      )}
                      {interview.notes && (
                        <div className="recruit-interview-notes">{interview.notes}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Notes Tab */}
      {activeTab === 'notes' && (
        <div className="recruit-tab-content">
          <div className="recruit-notes-section-full">
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
                rows="4"
              />
              <button
                className="mm-btn mm-btn-primary"
                onClick={handleAddNote}
                disabled={!newNote.trim()}
              >
                Add Note
              </button>
            </div>

            {/* Notes List */}
            <div className="recruit-notes-list-full">
              {candidate.notes?.length > 0 ? (
                candidate.notes.map((note) => (
                  <div key={note.id} className="recruit-note-card">
                    <p className="recruit-note-content">{note.content}</p>
                    <div className="recruit-note-meta">
                      <span className="recruit-note-author">{note.created_by_name || 'Team Member'}</span>
                      <span className="recruit-note-date">
                        {note.created_at ? new Date(note.created_at).toLocaleString() : ''}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <p className="recruit-empty-text">No notes yet</p>
              )}
            </div>

            {/* Activity Timeline */}
            {candidate.activities?.length > 0 && (
              <div className="recruit-activity-section">
                <h4>Activity Timeline</h4>
                <div className="recruit-activity-timeline-full">
                  {candidate.activities.map((activity) => (
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
                    score={assessment?.overall?.score}
                    grade={assessment?.overall?.grade}
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
                {/* DISC + Motivators Section */}
                <div className="recruit-assessment-disc">
                  <div className="recruit-section-header">
                    <h3>DISC + Motivators Assessment</h3>
                    {!discResults && !discLoading && (
                      <button
                        className="recruit-btn recruit-btn-sm"
                        onClick={() => setShowDISCInviteModal(true)}
                      >
                        Send Assessment Invite
                      </button>
                    )}
                    {discResults && (
                      <button
                        className="recruit-btn recruit-btn-sm recruit-btn-secondary"
                        onClick={handleDownloadDISCPDF}
                      >
                        Download PDF
                      </button>
                    )}
                  </div>

                  {discLoading ? (
                    <div className="recruit-loading">Loading DISC results...</div>
                  ) : discResults ? (
                    <div className="recruit-disc-full">
                      {/* DISC Graphs - Adapted & Natural */}
                      <DISCGraphs
                        adaptedScores={{
                          D: discResults.adapted_d,
                          I: discResults.adapted_i,
                          S: discResults.adapted_s,
                          C: discResults.adapted_c
                        }}
                        naturalScores={{
                          D: discResults.natural_d,
                          I: discResults.natural_i,
                          S: discResults.natural_s,
                          C: discResults.natural_c
                        }}
                        adaptedStyle={discResults.adapted_style}
                        naturalStyle={discResults.natural_style}
                      />

                      {/* Behavioral Pattern Wheel */}
                      <div className="recruit-disc-wheel-section">
                        <DISCWheel
                          zone={discResults.wheel_zone}
                          position={discResults.wheel_position}
                          zoneName={discResults.zone_name}
                          size={240}
                        />
                      </div>

                      {/* Motivators Chart */}
                      {motivatorResults && (
                        <MotivatorsBarchart
                          scores={{
                            aesthetic: motivatorResults.aesthetic,
                            economic: motivatorResults.economic,
                            individualistic: motivatorResults.individualistic,
                            political: motivatorResults.political,
                            altruistic: motivatorResults.altruistic,
                            regulatory: motivatorResults.regulatory,
                            theoretical: motivatorResults.theoretical
                          }}
                          ranking={motivatorResults.ranking}
                          topMotivator={motivatorResults.top_motivator}
                        />
                      )}
                    </div>
                  ) : assessment?.disc ? (
                    /* Fallback to AI-generated DISC if no formal assessment */
                    <DISCProfileChart
                      scores={{
                        D: assessment.disc.d_score || 0,
                        I: assessment.disc.i_score || 0,
                        S: assessment.disc.s_score || 0,
                        C: assessment.disc.c_score || 0,
                      }}
                      primaryStyle={assessment.disc.primary_style}
                      secondaryStyle={assessment.disc.secondary_style}
                      showIdealProfile={true}
                    />
                  ) : (
                    <div className="recruit-empty-disc">
                      <p>No DISC assessment data available</p>
                      <p className="recruit-empty-hint">Send an assessment invite or run AI Analysis</p>
                      <button
                        className="recruit-btn recruit-btn-primary"
                        onClick={() => setShowDISCInviteModal(true)}
                        style={{ marginTop: '12px' }}
                      >
                        Send DISC Assessment Invite
                      </button>
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
                        // Create or update assessment with AI-suggested scores
                        if (!assessment || assessment.has_assessment === false) {
                          await createAssessment(candidateId, scores, currentUserId || 1);
                        } else {
                          await updateAssessment(candidateId, scores, currentUserId || 1);
                        }
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

      {/* Edit Recruit Modal */}
      {showEditProduction && (
        <div className="mm-modal-overlay">
          <div className="mm-modal" style={{ maxWidth: '600px' }}>
            <h3>Edit Recruit</h3>

            {/* Basic Information Section */}
            <div className="mm-form-section">
              <h4 style={{ marginBottom: '12px', color: '#374151', fontSize: '14px', fontWeight: 600 }}>Basic Information</h4>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>First Name</label>
                  <input
                    type="text"
                    value={recruitForm.first_name}
                    onChange={(e) => setRecruitForm({ ...recruitForm, first_name: e.target.value })}
                    className="mm-input"
                    placeholder="John"
                  />
                </div>
                <div className="mm-form-group">
                  <label>Last Name</label>
                  <input
                    type="text"
                    value={recruitForm.last_name}
                    onChange={(e) => setRecruitForm({ ...recruitForm, last_name: e.target.value })}
                    className="mm-input"
                    placeholder="Doe"
                  />
                </div>
              </div>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={recruitForm.email}
                    onChange={(e) => setRecruitForm({ ...recruitForm, email: e.target.value })}
                    className="mm-input"
                    placeholder="john@example.com"
                  />
                </div>
                <div className="mm-form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={recruitForm.phone}
                    onChange={(e) => setRecruitForm({ ...recruitForm, phone: e.target.value })}
                    className="mm-input"
                    placeholder="(555) 123-4567"
                  />
                </div>
              </div>
            </div>

            {/* Production Information Section */}
            <div className="mm-form-section" style={{ marginTop: '20px' }}>
              <h4 style={{ marginBottom: '12px', color: '#374151', fontSize: '14px', fontWeight: 600 }}>Production Information</h4>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>Annual Volume ($)</label>
                  <input
                    type="number"
                    value={recruitForm.annual_volume}
                    onChange={(e) => setRecruitForm({ ...recruitForm, annual_volume: e.target.value })}
                    className="mm-input"
                    placeholder="50000000"
                  />
                </div>
                <div className="mm-form-group">
                  <label>Annual Units</label>
                  <input
                    type="number"
                    value={recruitForm.annual_units}
                    onChange={(e) => setRecruitForm({ ...recruitForm, annual_units: e.target.value })}
                    className="mm-input"
                    placeholder="100"
                  />
                </div>
              </div>
              <div className="mm-form-group">
                <label>NMLS ID</label>
                <input
                  type="text"
                  value={recruitForm.nmls_id}
                  onChange={(e) => setRecruitForm({ ...recruitForm, nmls_id: e.target.value })}
                  className="mm-input"
                  placeholder="12345678"
                />
              </div>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>Current Company</label>
                  <input
                    type="text"
                    value={recruitForm.current_company}
                    onChange={(e) => setRecruitForm({ ...recruitForm, current_company: e.target.value })}
                    className="mm-input"
                    placeholder="Premier Mortgage"
                  />
                </div>
                <div className="mm-form-group">
                  <label>Current Title</label>
                  <input
                    type="text"
                    value={recruitForm.current_title}
                    onChange={(e) => setRecruitForm({ ...recruitForm, current_title: e.target.value })}
                    className="mm-input"
                    placeholder="Senior Loan Officer"
                  />
                </div>
              </div>
            </div>

            <div className="mm-modal-actions">
              <button className="mm-btn mm-btn-secondary" onClick={() => setShowEditProduction(false)}>
                Cancel
              </button>
              <button className="mm-btn mm-btn-primary" onClick={handleSaveRecruit}>
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
          currentScore={assessment?.[editingCategory.key]?.score ? Math.round(assessment[editingCategory.key].score / 20) : undefined}
          onSave={async (score, notes) => {
            try {
              // Scale score from 1-5 to 0-100 (modal uses 1-5, API expects 0-100)
              const scaledScore = score * 20;

              // Special handling for DISC - has 4 separate scores
              if (editingCategory.key === 'disc') {
                const { updateDISCScores } = await import('../../services/candidateGradingApi');
                // Set all DISC scores to the same value for simple 1-5 rating
                await updateDISCScores(candidateId, {
                  d_score: scaledScore,
                  i_score: scaledScore,
                  s_score: scaledScore,
                  c_score: scaledScore,
                  notes: notes || null,
                  assessment_source: 'manual'
                }, currentUserId || 1);
              } else {
                // Map category key to API field name
                const categoryToField = {
                  'production': 'production_score',
                  'character': 'character_score',
                  'skills': 'skills_score',
                  'culture_fit': 'culture_fit_score'
                };
                const fieldName = categoryToField[editingCategory.key];
                if (!fieldName) {
                  throw new Error(`Unknown category: ${editingCategory.key}`);
                }

                const updateData = { [fieldName]: scaledScore };

                // Check if assessment exists - if not, create it first
                if (!assessment || assessment.has_assessment === false) {
                  await createAssessment(candidateId, updateData, currentUserId || 1);
                } else {
                  await updateAssessment(candidateId, updateData, currentUserId || 1);
                }
              }
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

      {/* Escalate Modal */}
      {showEscalateModal && (
        <div className="modal-overlay" onClick={() => setShowEscalateModal(false)}>
          <div className="modal-content escalate-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Escalate Candidate</h3>
              <button className="modal-close" onClick={() => setShowEscalateModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <p>Assign this candidate to another team member:</p>
              <div className="form-group">
                <label>Assign To</label>
                <select
                  value={selectedEscalateUser}
                  onChange={(e) => setSelectedEscalateUser(e.target.value)}
                  onFocus={() => escalateUsers.length === 0 && loadEscalateUsers()}
                  className="mm-select"
                >
                  <option value="">Select a team member...</option>
                  {escalateUsers.map(user => (
                    <option key={user.id} value={user.id}>
                      {user.full_name || user.name || user.email}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Note (optional)</label>
                <textarea
                  value={escalateNote}
                  onChange={(e) => setEscalateNote(e.target.value)}
                  placeholder="Add a note for the recipient..."
                  className="mm-textarea"
                  rows="3"
                />
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="mm-btn mm-btn-secondary"
                onClick={() => setShowEscalateModal(false)}
              >
                Cancel
              </button>
              <button
                className="mm-btn mm-btn-primary"
                onClick={handleEscalate}
                disabled={!selectedEscalateUser}
              >
                Escalate
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DISC Assessment Invite Modal */}
      {showDISCInviteModal && (
        <div className="modal-overlay" onClick={() => setShowDISCInviteModal(false)}>
          <div className="modal-content disc-invite-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Send DISC + Motivators Assessment</h3>
              <button className="modal-close" onClick={() => setShowDISCInviteModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <p>
                Send a DISC + Motivators assessment invite to <strong>{candidate?.first_name || candidate?.name}</strong>.
              </p>
              <p className="modal-hint">
                The candidate will receive an email with a link to complete the assessment.
                Results will be available here once completed.
              </p>
              <div className="disc-assessment-features">
                <div className="disc-feature">
                  <span className="disc-feature-icon">📊</span>
                  <span>DISC Behavioral Profile</span>
                </div>
                <div className="disc-feature">
                  <span className="disc-feature-icon">🎯</span>
                  <span>7 Motivators Analysis</span>
                </div>
                <div className="disc-feature">
                  <span className="disc-feature-icon">📄</span>
                  <span>Downloadable PDF Report</span>
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="mm-btn mm-btn-secondary"
                onClick={() => setShowDISCInviteModal(false)}
              >
                Cancel
              </button>
              <button
                className="mm-btn mm-btn-primary"
                onClick={handleSendDISCInvite}
              >
                Send Assessment Invite
              </button>
            </div>
          </div>
        </div>
      )}
      {candidate && candidate.phone && (
        <SMSAccordionPanel
          contactId={candidate.id || candidateId}
          contactName={candidate.name || `${candidate.first_name || ''} ${candidate.last_name || ''}`.trim()}
          phone={candidate.phone}
          pageType="recruit"
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
