import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import {
  getRecruitingDashboardStats,
  getRecruitingPipelineMetrics,
  getUpcomingInterviews,
  getCandidates,
  getJobPostings,
  getOffers,
  updateCandidateStatus,
  createCandidate,
  createJobPosting,
  publishJobPosting,
  getPartnerRecruits,
  updatePartnerRecruitStatus,
  getPartnerRecruitStats
} from '../../services/masterManagerApi';
import './MasterManager.css';

const CANDIDATE_STATUSES = [
  { value: 'new', label: 'New', color: '#3b82f6' },
  { value: 'screening', label: 'Screening', color: '#B8924A' },
  { value: 'phone_screen', label: 'Phone Screen', color: '#C9A44E' },
  { value: 'interview', label: 'Interview', color: '#f59e0b' },
  { value: 'assessment', label: 'Assessment', color: '#eab308' },
  { value: 'offer', label: 'Offer', color: '#22c55e' },
  { value: 'hired', label: 'Hired', color: '#2D7A52' },
  { value: 'rejected', label: 'Rejected', color: '#ef4444' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#6b7280' }
];

const PARTNER_STATUSES = [
  { value: 'new', label: 'New', color: '#3b82f6' },
  { value: 'active', label: 'Active', color: '#22c55e' },
  { value: 'contacted', label: 'Contacted', color: '#B8924A' },
  { value: 'meeting_scheduled', label: 'Meeting Scheduled', color: '#f59e0b' },
  { value: 'in_negotiation', label: 'In Negotiation', color: '#eab308' },
  { value: 'onboarded', label: 'Onboarded', color: '#2D7A52' },
  { value: 'inactive', label: 'Inactive', color: '#6b7280' },
  { value: 'declined', label: 'Declined', color: '#ef4444' }
];

const RecruitingDashboard = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require team management or recruiting access
  // Use isAdmin from context which has robust admin detection
  const canAccessRecruiting = isAdmin || hasAnyPermission(['team.view_all', 'team.manage_permissions', 'recruiting.view', 'recruiting.manage', 'capacity.view']) || userRole === 'management' || userRole === 'admin';

  // Main tab: 'employee' or 'partner'
  const [mainTab, setMainTab] = useState('employee');
  const [activeTab, setActiveTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [upcomingInterviews, setUpcomingInterviews] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [jobPostings, setJobPostings] = useState([]);
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Partner Recruit State
  const [partnerRecruits, setPartnerRecruits] = useState([]);
  const [partnerStats, setPartnerStats] = useState(null);
  const [partnerStatusFilter, setPartnerStatusFilter] = useState('');
  const [partnerSearchQuery, setPartnerSearchQuery] = useState('');
  const [selectedPartner, setSelectedPartner] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [showAddCandidate, setShowAddCandidate] = useState(false);
  const [showAddJob, setShowAddJob] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);

  // Form states
  const [newCandidate, setNewCandidate] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    source: 'direct',
    target_role_name: '',
    years_experience: 0,
    has_mortgage_experience: false,
    linkedin_url: ''
  });

  const [newJob, setNewJob] = useState({
    title: '',
    summary: '',
    description: '',
    salary_min: '',
    salary_max: '',
    employment_type: 'full_time',
    is_remote: false,
    location: ''
  });

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [statsData, metricsData, interviewsData] = await Promise.all([
        getRecruitingDashboardStats().catch(() => null),
        getRecruitingPipelineMetrics().catch(() => null),
        getUpcomingInterviews(5).catch(() => ({ interviews: [] }))
      ]);

      setStats(statsData);
      setMetrics(metricsData);
      setUpcomingInterviews(interviewsData.interviews || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCandidates = useCallback(async () => {
    try {
      const data = await getCandidates({
        status: statusFilter,
        search: searchQuery,
        limit: 50
      });
      setCandidates(data.candidates || []);
    } catch (err) {
      console.error('Failed to load candidates:', err);
    }
  }, [statusFilter, searchQuery]);

  const loadJobPostings = useCallback(async () => {
    try {
      const data = await getJobPostings({ limit: 50 });
      setJobPostings(data.job_postings || []);
    } catch (err) {
      console.error('Failed to load job postings:', err);
    }
  }, []);

  const loadOffers = useCallback(async () => {
    try {
      const data = await getOffers();
      setOffers(data.offers || []);
    } catch (err) {
      console.error('Failed to load offers:', err);
    }
  }, []);

  const loadPartnerRecruits = useCallback(async () => {
    try {
      const data = await getPartnerRecruits({
        status: partnerStatusFilter,
        search: partnerSearchQuery,
        limit: 50
      });
      setPartnerRecruits(data.partners || []);
    } catch (err) {
      console.error('Failed to load partner recruits:', err);
    }
  }, [partnerStatusFilter, partnerSearchQuery]);

  const loadPartnerStats = useCallback(async () => {
    try {
      const data = await getPartnerRecruitStats();
      setPartnerStats(data);
    } catch (err) {
      console.error('Failed to load partner stats:', err);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (mainTab === 'employee') {
      if (activeTab === 'candidates') {
        loadCandidates();
      } else if (activeTab === 'jobs') {
        loadJobPostings();
      } else if (activeTab === 'offers') {
        loadOffers();
      }
    } else if (mainTab === 'partner') {
      loadPartnerRecruits();
      loadPartnerStats();
    }
  }, [mainTab, activeTab, loadCandidates, loadJobPostings, loadOffers, loadPartnerRecruits, loadPartnerStats]);

  const handleStatusChange = async (candidateId, newStatus) => {
    try {
      await updateCandidateStatus(candidateId, newStatus);
      await loadCandidates();
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handlePartnerStatusChange = async (partnerId, newStatus) => {
    try {
      await updatePartnerRecruitStatus(partnerId, newStatus);
      await loadPartnerRecruits();
      await loadPartnerStats();
    } catch (err) {
      setError(err.message);
    }
  };

  const getPartnerStatusColor = (status) => {
    const statusObj = PARTNER_STATUSES.find(s => s.value === status);
    return statusObj?.color || '#6b7280';
  };

  const handleAddCandidate = async (e) => {
    e.preventDefault();
    try {
      await createCandidate(newCandidate);
      setShowAddCandidate(false);
      setNewCandidate({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        source: 'direct',
        target_role_name: '',
        years_experience: 0,
        has_mortgage_experience: false,
        linkedin_url: ''
      });
      await loadCandidates();
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAddJob = async (e) => {
    e.preventDefault();
    try {
      await createJobPosting({
        ...newJob,
        salary_min: parseInt(newJob.salary_min) || null,
        salary_max: parseInt(newJob.salary_max) || null
      });
      setShowAddJob(false);
      setNewJob({
        title: '',
        summary: '',
        description: '',
        salary_min: '',
        salary_max: '',
        employment_type: 'full_time',
        is_remote: false,
        location: ''
      });
      await loadJobPostings();
    } catch (err) {
      setError(err.message);
    }
  };

  const handlePublishJob = async (jobId) => {
    try {
      await publishJobPosting(jobId);
      await loadJobPostings();
    } catch (err) {
      setError(err.message);
    }
  };

  const getStatusColor = (status) => {
    const statusObj = CANDIDATE_STATUSES.find(s => s.value === status);
    return statusObj?.color || '#6b7280';
  };

  if (loading && !stats) {
    return (
      <div className="mm-loading">
        <div className="mm-spinner"></div>
        <p>Loading Recruiting Dashboard...</p>
      </div>
    );
  }

  // Access denied if user doesn't have recruiting permissions
  if (!canAccessRecruiting) {
    return (
      <div className="mm-container">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access the Recruiting Dashboard.</p>
          <button className="mm-btn mm-btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mm-container">
      {/* Header */}
      <div className="mm-header">
        <div className="mm-header-left">
          <h1>Recruiting Engine</h1>
          <p>{mainTab === 'employee' ? 'Employee candidate pipeline management' : 'Partner (Realtor) recruiting from RETR'}</p>
        </div>
        <div className="mm-header-actions">
          {mainTab === 'employee' && (
            <>
              <button
                className="mm-btn mm-btn-secondary"
                onClick={() => setShowAddJob(true)}
              >
                + Job Posting
              </button>
              <button
                className="mm-btn mm-btn-primary"
                onClick={() => setShowAddCandidate(true)}
              >
                + Add Candidate
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mm-error">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Main Tabs: Employee Recruit / Partner Recruit */}
      <div className="mm-main-tabs" style={{ marginBottom: '20px' }}>
        <button
          className={`mm-tab mm-main-tab ${mainTab === 'employee' ? 'active' : ''}`}
          onClick={() => { setMainTab('employee'); setActiveTab('overview'); }}
          style={{
            fontSize: '16px',
            padding: '12px 24px',
            fontWeight: mainTab === 'employee' ? 'bold' : 'normal',
            borderBottom: mainTab === 'employee' ? '3px solid #3b82f6' : '3px solid transparent'
          }}
        >
          Employee Recruit
        </button>
        <button
          className={`mm-tab mm-main-tab ${mainTab === 'partner' ? 'active' : ''}`}
          onClick={() => setMainTab('partner')}
          style={{
            fontSize: '16px',
            padding: '12px 24px',
            fontWeight: mainTab === 'partner' ? 'bold' : 'normal',
            borderBottom: mainTab === 'partner' ? '3px solid #22c55e' : '3px solid transparent'
          }}
        >
          Partner Recruit
        </button>
      </div>

      {/* Employee Recruit Sub-tabs */}
      {mainTab === 'employee' && (
        <div className="mm-tabs">
          <button
            className={`mm-tab ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview
          </button>
          <button
            className={`mm-tab ${activeTab === 'candidates' ? 'active' : ''}`}
            onClick={() => setActiveTab('candidates')}
          >
            Candidates
          </button>
          <button
            className={`mm-tab ${activeTab === 'jobs' ? 'active' : ''}`}
            onClick={() => setActiveTab('jobs')}
          >
            Job Postings
          </button>
          <button
            className={`mm-tab ${activeTab === 'offers' ? 'active' : ''}`}
            onClick={() => setActiveTab('offers')}
          >
            Offers
          </button>
        </div>
      )}

      {/* Employee Recruit Content */}
      {mainTab === 'employee' && activeTab === 'overview' && (
        <>
          {/* Stats Cards */}
          {stats && (
            <div className="mm-overview-grid">
              <div
                className="mm-card mm-stat-card mm-clickable"
                onClick={() => { setStatusFilter(''); setActiveTab('candidates'); }}
                title="View all active candidates"
              >
                <div className="mm-stat-value">{stats.candidates?.total_active || 0}</div>
                <div className="mm-stat-label">Active Candidates</div>
              </div>
              <div
                className="mm-card mm-stat-card mm-clickable"
                onClick={() => { setStatusFilter('new'); setActiveTab('candidates'); }}
                title="View new candidates"
              >
                <div className="mm-stat-value" style={{ color: '#3b82f6' }}>
                  {stats.candidates?.new || 0}
                </div>
                <div className="mm-stat-label">New This Week</div>
              </div>
              <div
                className="mm-card mm-stat-card mm-clickable"
                onClick={() => { setStatusFilter('interview'); setActiveTab('candidates'); }}
                title="View candidates in interview stage"
              >
                <div className="mm-stat-value" style={{ color: '#f59e0b' }}>
                  {stats.candidates?.interviewing || 0}
                </div>
                <div className="mm-stat-label">Interviewing</div>
              </div>
              <div
                className="mm-card mm-stat-card mm-clickable"
                onClick={() => { setStatusFilter('offer'); setActiveTab('candidates'); }}
                title="View candidates in offer stage"
              >
                <div className="mm-stat-value" style={{ color: '#22c55e' }}>
                  {stats.candidates?.offer_stage || 0}
                </div>
                <div className="mm-stat-label">Offer Stage</div>
              </div>
              <div
                className="mm-card mm-stat-card mm-clickable"
                onClick={() => setActiveTab('jobs')}
                title="View open job postings"
              >
                <div className="mm-stat-value">{stats.positions?.open || 0}</div>
                <div className="mm-stat-label">Open Positions</div>
              </div>
              <div className="mm-card mm-stat-card">
                <div className="mm-stat-value">{stats.interviews?.upcoming || 0}</div>
                <div className="mm-stat-label">Upcoming Interviews</div>
              </div>
            </div>
          )}

          {/* Pipeline Metrics */}
          {metrics && (
            <div className="mm-section">
              <h2>Pipeline Performance</h2>
              <div className="mm-metrics-grid">
                <div className="mm-card mm-metric-card">
                  <div className="mm-metric-header">
                    <span className="mm-metric-label">Avg Time to Hire</span>
                    <span className="mm-metric-value">{metrics.avg_time_to_hire_days || 0} days</span>
                  </div>
                </div>
                <div className="mm-card mm-metric-card">
                  <div className="mm-metric-header">
                    <span className="mm-metric-label">Apply to Screen Rate</span>
                    <span className="mm-metric-value">{metrics.conversion_rates?.apply_to_screen || 0}%</span>
                  </div>
                  <div className="mm-capacity-bar-container">
                    <div
                      className="mm-capacity-bar"
                      style={{
                        width: `${metrics.conversion_rates?.apply_to_screen || 0}%`,
                        backgroundColor: '#B8924A'
                      }}
                    />
                  </div>
                </div>
                <div className="mm-card mm-metric-card">
                  <div className="mm-metric-header">
                    <span className="mm-metric-label">Interview to Offer Rate</span>
                    <span className="mm-metric-value">{metrics.conversion_rates?.interview_to_offer || 0}%</span>
                  </div>
                  <div className="mm-capacity-bar-container">
                    <div
                      className="mm-capacity-bar"
                      style={{
                        width: `${metrics.conversion_rates?.interview_to_offer || 0}%`,
                        backgroundColor: '#22c55e'
                      }}
                    />
                  </div>
                </div>
                <div className="mm-card mm-metric-card">
                  <div className="mm-metric-header">
                    <span className="mm-metric-label">Overall Conversion</span>
                    <span className="mm-metric-value">{metrics.conversion_rates?.overall || 0}%</span>
                  </div>
                  <div className="mm-capacity-bar-container">
                    <div
                      className="mm-capacity-bar"
                      style={{
                        width: `${metrics.conversion_rates?.overall || 0}%`,
                        backgroundColor: '#2D7A52'
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Pipeline by Status */}
          {metrics?.by_status && (
            <div className="mm-section">
              <h2>Pipeline by Stage</h2>
              <div className="mm-pipeline-stages">
                {CANDIDATE_STATUSES.slice(0, 7).map((status) => (
                  <div
                    key={status.value}
                    className="mm-pipeline-stage mm-clickable"
                    onClick={() => { setStatusFilter(status.value); setActiveTab('candidates'); }}
                    title={`View ${status.label} candidates`}
                  >
                    <div
                      className="mm-stage-count"
                      style={{ backgroundColor: status.color }}
                    >
                      {metrics.by_status[status.value] || 0}
                    </div>
                    <div className="mm-stage-label">{status.label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Upcoming Interviews */}
          {upcomingInterviews.length > 0 && (
            <div className="mm-section">
              <h2>Upcoming Interviews</h2>
              <div className="mm-interviews-list">
                {upcomingInterviews.map((interview) => (
                  <div
                    key={interview.id}
                    className="mm-card mm-interview-card mm-clickable"
                    onClick={() => interview.candidate_id && navigate(`/master-manager/recruiting/${interview.candidate_id}`)}
                    style={{ cursor: interview.candidate_id ? 'pointer' : 'default' }}
                  >
                    <div className="mm-interview-time">
                      {new Date(interview.scheduled_at).toLocaleString([], {
                        weekday: 'short',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </div>
                    <div className="mm-interview-details">
                      <div className="mm-interview-candidate">{interview.candidate_name}</div>
                      <div className="mm-interview-type">{interview.type} - {interview.duration_minutes} min</div>
                    </div>
                    <div className="mm-interview-interviewer">
                      with {interview.interviewer || 'TBD'}
                    </div>
                    {interview.meeting_link && (
                      <a
                        href={interview.meeting_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mm-btn mm-btn-small mm-btn-primary"
                        onClick={(e) => e.stopPropagation()}
                      >
                        Join
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Candidates Tab */}
      {mainTab === 'employee' && activeTab === 'candidates' && (
        <div className="mm-section">
          <div className="mm-section-header">
            <h2>All Candidates</h2>
            <div className="mm-filters">
              <input
                type="text"
                placeholder="Search candidates..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="mm-input"
              />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="mm-select"
              >
                <option value="">All Statuses</option>
                {CANDIDATE_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="mm-table-container">
            <table className="mm-table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Target Role</th>
                  <th>Source</th>
                  <th>Experience</th>
                  <th>Score</th>
                  <th>Interviews</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {candidates.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="mm-table-empty">
                      No candidates found. Click "+ Add Candidate" to add one.
                    </td>
                  </tr>
                ) : (
                  candidates.map((candidate) => (
                    <tr
                      key={candidate.id}
                      onClick={() => navigate(`/master-manager/recruiting/${candidate.id}`)}
                      style={{ cursor: 'pointer' }}
                      className="mm-clickable-row"
                    >
                      <td>
                        <div className="mm-user-cell">
                          <div className="mm-user-avatar" style={{ backgroundColor: getStatusColor(candidate.status) }}>
                            {candidate.first_name?.charAt(0) || '?'}
                          </div>
                          <div>
                            <div className="mm-user-name">{candidate.name}</div>
                            <div className="mm-user-email">{candidate.email}</div>
                          </div>
                        </div>
                      </td>
                      <td>{candidate.target_role || '-'}</td>
                      <td>{candidate.source || 'Direct'}</td>
                      <td>
                        {candidate.years_experience ? `${candidate.years_experience} yrs` : '-'}
                        {candidate.has_mortgage_experience && <span className="mm-badge mm-badge-info">Mortgage</span>}
                      </td>
                      <td>
                        {candidate.assessment_score ? (
                          <span
                            className="mm-score-badge"
                            style={{
                              backgroundColor: candidate.assessment_score >= 80 ? '#dcfce7' :
                                             candidate.assessment_score >= 60 ? '#fef3c7' :
                                             candidate.assessment_score >= 40 ? '#ffedd5' : '#fee2e2',
                              color: candidate.assessment_score >= 80 ? '#166534' :
                                    candidate.assessment_score >= 60 ? '#92400e' :
                                    candidate.assessment_score >= 40 ? '#9a3412' : '#991b1b',
                              padding: '4px 8px',
                              borderRadius: '4px',
                              fontWeight: '600',
                              fontSize: '13px'
                            }}
                          >
                            {candidate.assessment_score}
                            {candidate.assessment_grade && ` (${candidate.assessment_grade})`}
                          </span>
                        ) : (
                          <span style={{ color: '#9ca3af' }}>-</span>
                        )}
                      </td>
                      <td>{candidate.interview_count || 0}</td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <select
                          value={candidate.status}
                          onChange={(e) => handleStatusChange(candidate.id, e.target.value)}
                          className="mm-select mm-select-inline"
                          style={{ backgroundColor: getStatusColor(candidate.status), color: 'white' }}
                        >
                          {CANDIDATE_STATUSES.map((s) => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </select>
                      </td>
                      <td className="mm-actions-cell" onClick={(e) => e.stopPropagation()}>
                        <button
                          className="mm-btn mm-btn-small mm-btn-primary"
                          onClick={() => navigate(`/master-manager/recruiting/${candidate.id}`)}
                          title="View full profile"
                        >
                          View
                        </button>
                        <button
                          className="mm-btn mm-btn-small mm-btn-secondary"
                          onClick={() => setSelectedCandidate(candidate)}
                          title="Quick view"
                        >
                          ...
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Job Postings Tab */}
      {mainTab === 'employee' && activeTab === 'jobs' && (
        <div className="mm-section">
          <h2>Job Postings</h2>
          <div className="mm-jobs-grid">
            {jobPostings.length === 0 ? (
              <div className="mm-card mm-empty-card">
                <p>No job postings yet. Click "+ Job Posting" to create one.</p>
              </div>
            ) : (
              jobPostings.map((job) => (
                <div
                  key={job.id}
                  className="mm-card mm-job-card mm-clickable"
                  onClick={() => setSelectedJob(job)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="mm-job-header">
                    <div className="mm-job-title">{job.title}</div>
                    <span className={`mm-status-badge ${job.is_published ? 'mm-status-published' : 'mm-status-draft'}`}>
                      {job.is_published ? 'Published' : 'Draft'}
                    </span>
                  </div>
                  <div className="mm-job-meta">
                    {job.location && <span>{job.location}</span>}
                    {job.is_remote && <span>Remote</span>}
                    <span>{job.employment_type?.replace('_', ' ')}</span>
                  </div>
                  {job.salary_range && (
                    <div className="mm-job-salary">{job.salary_range}</div>
                  )}
                  <div className="mm-job-stats">
                    <div className="mm-job-stat">
                      <span className="mm-stat-value">{job.views || 0}</span>
                      <span className="mm-stat-label">Views</span>
                    </div>
                    <div className="mm-job-stat">
                      <span className="mm-stat-value">{job.applications || 0}</span>
                      <span className="mm-stat-label">Applications</span>
                    </div>
                    <div className="mm-job-stat">
                      <span className="mm-stat-value">{job.active_candidates || 0}</span>
                      <span className="mm-stat-label">Active</span>
                    </div>
                  </div>
                  {!job.is_published && (
                    <button
                      className="mm-btn mm-btn-primary mm-btn-full"
                      onClick={(e) => { e.stopPropagation(); handlePublishJob(job.id); }}
                    >
                      Publish
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Offers Tab */}
      {mainTab === 'employee' && activeTab === 'offers' && (
        <div className="mm-section">
          <h2>Offers</h2>
          <div className="mm-table-container">
            <table className="mm-table">
              <thead>
                <tr>
                  <th>Offer #</th>
                  <th>Candidate</th>
                  <th>Role</th>
                  <th>Salary</th>
                  <th>Status</th>
                  <th>Sent</th>
                  <th>Expires</th>
                </tr>
              </thead>
              <tbody>
                {offers.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="mm-table-empty">
                      No offers yet. Create offers from candidate profiles.
                    </td>
                  </tr>
                ) : (
                  offers.map((offer) => (
                    <tr
                      key={offer.id}
                      onClick={() => offer.candidate_id && navigate(`/master-manager/recruiting/${offer.candidate_id}`)}
                      style={{ cursor: offer.candidate_id ? 'pointer' : 'default' }}
                      className={offer.candidate_id ? 'mm-clickable-row' : ''}
                    >
                      <td><strong>{offer.offer_number}</strong></td>
                      <td>{offer.candidate_name}</td>
                      <td>{offer.role_title}</td>
                      <td>${offer.salary_amount?.toLocaleString()}</td>
                      <td>
                        <span className={`mm-status-badge mm-status-${offer.status}`}>
                          {offer.status}
                        </span>
                      </td>
                      <td>{offer.sent_at ? new Date(offer.sent_at).toLocaleDateString() : '-'}</td>
                      <td>{offer.expires_at ? new Date(offer.expires_at).toLocaleDateString() : '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Partner Recruit Content */}
      {mainTab === 'partner' && (
        <>
          {/* Partner Stats Cards */}
          {partnerStats && (
            <div className="mm-overview-grid">
              <div className="mm-card mm-stat-card">
                <div className="mm-stat-value">{partnerStats.total || 0}</div>
                <div className="mm-stat-label">Total Partners</div>
              </div>
              <div className="mm-card mm-stat-card">
                <div className="mm-stat-value" style={{ color: '#3b82f6' }}>
                  {partnerStats.new_this_week || 0}
                </div>
                <div className="mm-stat-label">New This Week</div>
              </div>
              <div className="mm-card mm-stat-card">
                <div className="mm-stat-value" style={{ color: '#B8924A' }}>
                  {partnerStats.contacted || 0}
                </div>
                <div className="mm-stat-label">Contacted</div>
              </div>
              <div className="mm-card mm-stat-card">
                <div className="mm-stat-value" style={{ color: '#f59e0b' }}>
                  {partnerStats.meeting_scheduled || 0}
                </div>
                <div className="mm-stat-label">Meeting Scheduled</div>
              </div>
              <div className="mm-card mm-stat-card">
                <div className="mm-stat-value" style={{ color: '#2D7A52' }}>
                  {partnerStats.onboarded || 0}
                </div>
                <div className="mm-stat-label">Onboarded</div>
              </div>
              <div className="mm-card mm-stat-card">
                <div className="mm-stat-value" style={{ color: '#22c55e' }}>
                  {partnerStats.from_retr || 0}
                </div>
                <div className="mm-stat-label">From RETR</div>
              </div>
            </div>
          )}

          {/* Partner Pipeline Metrics */}
          {partnerStats && partnerStats.conversion_rates && (
            <div className="mm-section">
              <h2>Pipeline Performance</h2>
              <div className="mm-metrics-grid">
                <div className="mm-card mm-metric-card">
                  <div className="mm-metric-header">
                    <span className="mm-metric-label">New to Contacted Rate</span>
                    <span className="mm-metric-value">{partnerStats.conversion_rates?.new_to_contacted || 0}%</span>
                  </div>
                  <div className="mm-capacity-bar-container">
                    <div
                      className="mm-capacity-bar"
                      style={{
                        width: `${partnerStats.conversion_rates?.new_to_contacted || 0}%`,
                        backgroundColor: '#B8924A'
                      }}
                    />
                  </div>
                </div>
                <div className="mm-card mm-metric-card">
                  <div className="mm-metric-header">
                    <span className="mm-metric-label">Contacted to Onboarded</span>
                    <span className="mm-metric-value">{partnerStats.conversion_rates?.contacted_to_onboarded || 0}%</span>
                  </div>
                  <div className="mm-capacity-bar-container">
                    <div
                      className="mm-capacity-bar"
                      style={{
                        width: `${partnerStats.conversion_rates?.contacted_to_onboarded || 0}%`,
                        backgroundColor: '#22c55e'
                      }}
                    />
                  </div>
                </div>
                <div className="mm-card mm-metric-card">
                  <div className="mm-metric-header">
                    <span className="mm-metric-label">Overall Conversion</span>
                    <span className="mm-metric-value">{partnerStats.conversion_rates?.overall || 0}%</span>
                  </div>
                  <div className="mm-capacity-bar-container">
                    <div
                      className="mm-capacity-bar"
                      style={{
                        width: `${partnerStats.conversion_rates?.overall || 0}%`,
                        backgroundColor: '#2D7A52'
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Partner Pipeline by Status */}
          {partnerStats && partnerStats.by_status && (
            <div className="mm-section">
              <h2>Pipeline by Stage</h2>
              <div className="mm-pipeline-stages">
                {PARTNER_STATUSES.slice(0, 6).map((status) => (
                  <div key={status.value} className="mm-pipeline-stage">
                    <div
                      className="mm-stage-count"
                      style={{ backgroundColor: status.color }}
                    >
                      {partnerStats.by_status[status.value] || 0}
                    </div>
                    <div className="mm-stage-label">{status.label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Partner Recruits Table */}
          <div className="mm-section">
            <div className="mm-section-header">
              <h2>Partner Recruits (Realtors)</h2>
              <div className="mm-filters">
                <input
                  type="text"
                  placeholder="Search partners..."
                  value={partnerSearchQuery}
                  onChange={(e) => setPartnerSearchQuery(e.target.value)}
                  className="mm-input"
                />
                <select
                  value={partnerStatusFilter}
                  onChange={(e) => setPartnerStatusFilter(e.target.value)}
                  className="mm-select"
                >
                  <option value="">All Statuses</option>
                  {PARTNER_STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mm-table-container">
              <table className="mm-table">
                <thead>
                  <tr>
                    <th>Partner</th>
                    <th>Company</th>
                    <th>Source</th>
                    <th>Phone</th>
                    <th>Added</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {partnerRecruits.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="mm-table-empty">
                        No partner recruits found. Import realtors from RETR to see them here.
                      </td>
                    </tr>
                  ) : (
                    partnerRecruits.map((partner) => (
                      <tr
                        key={partner.id}
                        onClick={() => setSelectedPartner(partner)}
                        style={{ cursor: 'pointer' }}
                        className="mm-clickable-row"
                      >
                        <td>
                          <div className="mm-user-cell">
                            <div className="mm-user-avatar" style={{ backgroundColor: getPartnerStatusColor(partner.status) }}>
                              {partner.name?.charAt(0) || '?'}
                            </div>
                            <div>
                              <div className="mm-user-name">{partner.name || partner.contact_name}</div>
                              <div className="mm-user-email">{partner.email}</div>
                            </div>
                          </div>
                        </td>
                        <td>{partner.company || partner.business_name || '-'}</td>
                        <td>
                          {partner.source === 'retr' ? (
                            <span className="mm-badge mm-badge-info">RETR</span>
                          ) : (
                            partner.source || 'Direct'
                          )}
                        </td>
                        <td>{partner.phone || '-'}</td>
                        <td>{partner.created_at ? new Date(partner.created_at).toLocaleDateString() : '-'}</td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <select
                            value={partner.status || 'new'}
                            onChange={(e) => handlePartnerStatusChange(partner.id, e.target.value)}
                            className="mm-select mm-select-inline"
                            style={{ backgroundColor: getPartnerStatusColor(partner.status), color: 'white' }}
                          >
                            {PARTNER_STATUSES.map((s) => (
                              <option key={s.value} value={s.value}>{s.label}</option>
                            ))}
                          </select>
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <button
                            className="mm-btn mm-btn-small mm-btn-secondary"
                            onClick={() => setSelectedPartner(partner)}
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Partner Detail Modal */}
      {selectedPartner && (
        <div className="mm-modal-overlay">
          <div className="mm-modal mm-modal-large">
            <div className="mm-modal-header">
              <h3>{selectedPartner.name || selectedPartner.contact_name}</h3>
              <button className="mm-modal-close" onClick={() => setSelectedPartner(null)}>&times;</button>
            </div>
            <div className="mm-candidate-detail">
              <div className="mm-detail-section">
                <h4>Contact Information</h4>
                <p><strong>Email:</strong> {selectedPartner.email || 'Not provided'}</p>
                <p><strong>Phone:</strong> {selectedPartner.phone || 'Not provided'}</p>
              </div>
              <div className="mm-detail-section">
                <h4>Business Details</h4>
                <p><strong>Company:</strong> {selectedPartner.company || selectedPartner.business_name || 'Not specified'}</p>
                <p><strong>License #:</strong> {selectedPartner.license_number || 'Not provided'}</p>
                <p><strong>Source:</strong> {selectedPartner.source || 'Direct'}</p>
                <p><strong>Added:</strong> {selectedPartner.created_at ? new Date(selectedPartner.created_at).toLocaleDateString() : 'N/A'}</p>
              </div>
              {selectedPartner.notes && (
                <div className="mm-detail-section">
                  <h4>Notes</h4>
                  <p>{selectedPartner.notes}</p>
                </div>
              )}
              <div className="mm-detail-section">
                <h4>Status</h4>
                <select
                  value={selectedPartner.status || 'new'}
                  onChange={(e) => {
                    handlePartnerStatusChange(selectedPartner.id, e.target.value);
                    setSelectedPartner({ ...selectedPartner, status: e.target.value });
                  }}
                  className="mm-select"
                >
                  {PARTNER_STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mm-modal-actions">
              <button className="mm-btn mm-btn-secondary" onClick={() => setSelectedPartner(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Candidate Modal */}
      {showAddCandidate && (
        <div className="mm-modal-overlay">
          <div className="mm-modal mm-modal-large">
            <h3>Add Candidate</h3>
            <form onSubmit={handleAddCandidate}>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>First Name*</label>
                  <input
                    type="text"
                    value={newCandidate.first_name}
                    onChange={(e) => setNewCandidate({ ...newCandidate, first_name: e.target.value })}
                    required
                    className="mm-input"
                  />
                </div>
                <div className="mm-form-group">
                  <label>Last Name*</label>
                  <input
                    type="text"
                    value={newCandidate.last_name}
                    onChange={(e) => setNewCandidate({ ...newCandidate, last_name: e.target.value })}
                    required
                    className="mm-input"
                  />
                </div>
              </div>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>Email*</label>
                  <input
                    type="email"
                    value={newCandidate.email}
                    onChange={(e) => setNewCandidate({ ...newCandidate, email: e.target.value })}
                    required
                    className="mm-input"
                  />
                </div>
                <div className="mm-form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={newCandidate.phone}
                    onChange={(e) => setNewCandidate({ ...newCandidate, phone: e.target.value })}
                    className="mm-input"
                  />
                </div>
              </div>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>Target Role</label>
                  <input
                    type="text"
                    value={newCandidate.target_role_name}
                    onChange={(e) => setNewCandidate({ ...newCandidate, target_role_name: e.target.value })}
                    placeholder="e.g., Loan Officer, Processor"
                    className="mm-input"
                  />
                </div>
                <div className="mm-form-group">
                  <label>Source</label>
                  <select
                    value={newCandidate.source}
                    onChange={(e) => setNewCandidate({ ...newCandidate, source: e.target.value })}
                    className="mm-select"
                  >
                    <option value="direct">Direct Application</option>
                    <option value="referral">Employee Referral</option>
                    <option value="linkedin">LinkedIn</option>
                    <option value="indeed">Indeed</option>
                    <option value="recruiter">Recruiter</option>
                    <option value="other">Other</option>
                  </select>
                </div>
              </div>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>Years of Experience</label>
                  <input
                    type="number"
                    value={newCandidate.years_experience}
                    onChange={(e) => setNewCandidate({ ...newCandidate, years_experience: parseInt(e.target.value) || 0 })}
                    min="0"
                    className="mm-input"
                  />
                </div>
                <div className="mm-form-group">
                  <label>LinkedIn URL</label>
                  <input
                    type="url"
                    value={newCandidate.linkedin_url}
                    onChange={(e) => setNewCandidate({ ...newCandidate, linkedin_url: e.target.value })}
                    placeholder="https://linkedin.com/in/..."
                    className="mm-input"
                  />
                </div>
              </div>
              <div className="mm-form-group">
                <label className="mm-checkbox-label">
                  <input
                    type="checkbox"
                    checked={newCandidate.has_mortgage_experience}
                    onChange={(e) => setNewCandidate({ ...newCandidate, has_mortgage_experience: e.target.checked })}
                  />
                  Has Mortgage Industry Experience
                </label>
              </div>
              <div className="mm-modal-actions">
                <button type="button" className="mm-btn mm-btn-secondary" onClick={() => setShowAddCandidate(false)}>
                  Cancel
                </button>
                <button type="submit" className="mm-btn mm-btn-primary">
                  Add Candidate
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Job Modal */}
      {showAddJob && (
        <div className="mm-modal-overlay">
          <div className="mm-modal mm-modal-large">
            <h3>Create Job Posting</h3>
            <form onSubmit={handleAddJob}>
              <div className="mm-form-group">
                <label>Job Title*</label>
                <input
                  type="text"
                  value={newJob.title}
                  onChange={(e) => setNewJob({ ...newJob, title: e.target.value })}
                  required
                  placeholder="e.g., Senior Loan Officer"
                  className="mm-input"
                />
              </div>
              <div className="mm-form-group">
                <label>Summary</label>
                <textarea
                  value={newJob.summary}
                  onChange={(e) => setNewJob({ ...newJob, summary: e.target.value })}
                  placeholder="Brief summary of the role..."
                  rows="2"
                  className="mm-textarea"
                />
              </div>
              <div className="mm-form-group">
                <label>Description</label>
                <textarea
                  value={newJob.description}
                  onChange={(e) => setNewJob({ ...newJob, description: e.target.value })}
                  placeholder="Full job description..."
                  rows="4"
                  className="mm-textarea"
                />
              </div>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>Salary Min</label>
                  <input
                    type="number"
                    value={newJob.salary_min}
                    onChange={(e) => setNewJob({ ...newJob, salary_min: e.target.value })}
                    placeholder="50000"
                    className="mm-input"
                  />
                </div>
                <div className="mm-form-group">
                  <label>Salary Max</label>
                  <input
                    type="number"
                    value={newJob.salary_max}
                    onChange={(e) => setNewJob({ ...newJob, salary_max: e.target.value })}
                    placeholder="80000"
                    className="mm-input"
                  />
                </div>
              </div>
              <div className="mm-form-row">
                <div className="mm-form-group">
                  <label>Employment Type</label>
                  <select
                    value={newJob.employment_type}
                    onChange={(e) => setNewJob({ ...newJob, employment_type: e.target.value })}
                    className="mm-select"
                  >
                    <option value="full_time">Full Time</option>
                    <option value="part_time">Part Time</option>
                    <option value="contract">Contract</option>
                  </select>
                </div>
                <div className="mm-form-group">
                  <label>Location</label>
                  <input
                    type="text"
                    value={newJob.location}
                    onChange={(e) => setNewJob({ ...newJob, location: e.target.value })}
                    placeholder="e.g., San Francisco, CA"
                    className="mm-input"
                  />
                </div>
              </div>
              <div className="mm-form-group">
                <label className="mm-checkbox-label">
                  <input
                    type="checkbox"
                    checked={newJob.is_remote}
                    onChange={(e) => setNewJob({ ...newJob, is_remote: e.target.checked })}
                  />
                  Remote Position
                </label>
              </div>
              <div className="mm-modal-actions">
                <button type="button" className="mm-btn mm-btn-secondary" onClick={() => setShowAddJob(false)}>
                  Cancel
                </button>
                <button type="submit" className="mm-btn mm-btn-primary">
                  Create Job Posting
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Candidate Detail Modal */}
      {selectedCandidate && (
        <div className="mm-modal-overlay">
          <div className="mm-modal mm-modal-large">
            <div className="mm-modal-header">
              <h3>{selectedCandidate.name}</h3>
              <button className="mm-modal-close" onClick={() => setSelectedCandidate(null)}>&times;</button>
            </div>
            <div className="mm-candidate-detail">
              <div className="mm-detail-section">
                <h4>Contact Information</h4>
                <p><strong>Email:</strong> {selectedCandidate.email}</p>
                <p><strong>Phone:</strong> {selectedCandidate.phone || 'Not provided'}</p>
              </div>
              <div className="mm-detail-section">
                <h4>Application Details</h4>
                <p><strong>Target Role:</strong> {selectedCandidate.target_role || 'Not specified'}</p>
                <p><strong>Source:</strong> {selectedCandidate.source}</p>
                <p><strong>Experience:</strong> {selectedCandidate.years_experience || 0} years</p>
                <p><strong>Mortgage Experience:</strong> {selectedCandidate.has_mortgage_experience ? 'Yes' : 'No'}</p>
                <p><strong>Applied:</strong> {selectedCandidate.applied_at ? new Date(selectedCandidate.applied_at).toLocaleDateString() : 'N/A'}</p>
              </div>
              <div className="mm-detail-section">
                <h4>Status</h4>
                <select
                  value={selectedCandidate.status}
                  onChange={(e) => {
                    handleStatusChange(selectedCandidate.id, e.target.value);
                    setSelectedCandidate({ ...selectedCandidate, status: e.target.value });
                  }}
                  className="mm-select"
                >
                  {CANDIDATE_STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mm-modal-actions">
              <button className="mm-btn mm-btn-secondary" onClick={() => setSelectedCandidate(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Job Detail Modal */}
      {selectedJob && (
        <div className="mm-modal-overlay">
          <div className="mm-modal mm-modal-large">
            <div className="mm-modal-header">
              <h3>{selectedJob.title}</h3>
              <button className="mm-modal-close" onClick={() => setSelectedJob(null)}>&times;</button>
            </div>
            <div className="mm-candidate-detail">
              <div className="mm-detail-section">
                <h4>Job Details</h4>
                <p><strong>Status:</strong> {selectedJob.is_published ? 'Published' : 'Draft'}</p>
                <p><strong>Employment Type:</strong> {selectedJob.employment_type?.replace('_', ' ') || 'Not specified'}</p>
                <p><strong>Location:</strong> {selectedJob.location || 'Not specified'}</p>
                <p><strong>Remote:</strong> {selectedJob.is_remote ? 'Yes' : 'No'}</p>
              </div>
              {(selectedJob.salary_min || selectedJob.salary_max || selectedJob.salary_range) && (
                <div className="mm-detail-section">
                  <h4>Compensation</h4>
                  <p><strong>Salary Range:</strong> {selectedJob.salary_range || `$${selectedJob.salary_min?.toLocaleString() || '0'} - $${selectedJob.salary_max?.toLocaleString() || '0'}`}</p>
                </div>
              )}
              {selectedJob.summary && (
                <div className="mm-detail-section">
                  <h4>Summary</h4>
                  <p>{selectedJob.summary}</p>
                </div>
              )}
              {selectedJob.description && (
                <div className="mm-detail-section">
                  <h4>Description</h4>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{selectedJob.description}</p>
                </div>
              )}
              <div className="mm-detail-section">
                <h4>Statistics</h4>
                <p><strong>Views:</strong> {selectedJob.views || 0}</p>
                <p><strong>Applications:</strong> {selectedJob.applications || 0}</p>
                <p><strong>Active Candidates:</strong> {selectedJob.active_candidates || 0}</p>
              </div>
              {selectedJob.created_at && (
                <div className="mm-detail-section">
                  <h4>Dates</h4>
                  <p><strong>Created:</strong> {new Date(selectedJob.created_at).toLocaleDateString()}</p>
                  {selectedJob.published_at && (
                    <p><strong>Published:</strong> {new Date(selectedJob.published_at).toLocaleDateString()}</p>
                  )}
                </div>
              )}
            </div>
            <div className="mm-modal-actions">
              {!selectedJob.is_published && (
                <button
                  className="mm-btn mm-btn-primary"
                  onClick={() => { handlePublishJob(selectedJob.id); setSelectedJob({ ...selectedJob, is_published: true }); }}
                >
                  Publish
                </button>
              )}
              <button className="mm-btn mm-btn-secondary" onClick={() => setSelectedJob(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RecruitingDashboard;
