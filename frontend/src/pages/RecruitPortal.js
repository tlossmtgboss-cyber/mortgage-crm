import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import './RecruitPortal.css';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const RecruitPortal = () => {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const [candidate, setCandidate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [showInterestModal, setShowInterestModal] = useState(false);

  // Get token from URL param or query string
  const accessToken = token || searchParams.get('token');

  useEffect(() => {
    const loadCandidatePortal = async () => {
      if (!accessToken) {
        setError('No access token provided. Please use the link from your email.');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_URL}/api/v1/recruit-portal/${accessToken}`);
        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('Portal access link is invalid or expired.');
          }
          throw new Error('Failed to load portal');
        }
        const data = await response.json();
        setCandidate(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    loadCandidatePortal();
  }, [accessToken]);

  const getStatusBadge = (status) => {
    const statusConfig = {
      new: { label: 'Application Received', color: '#3b82f6', icon: '📋' },
      screening: { label: 'Under Review', color: '#B8924A', icon: '🔍' },
      phone_screen: { label: 'Phone Screen', color: '#C9A44E', icon: '📞' },
      interview: { label: 'Interview Stage', color: '#f59e0b', icon: '🤝' },
      assessment: { label: 'Assessment', color: '#eab308', icon: '📝' },
      offer: { label: 'Offer Pending', color: '#22c55e', icon: '🎉' },
      hired: { label: 'Hired!', color: '#2D7A52', icon: '✅' },
      rejected: { label: 'Not Selected', color: '#ef4444', icon: '❌' },
      withdrawn: { label: 'Withdrawn', color: '#6b7280', icon: '↩️' }
    };
    const config = statusConfig[status] || { label: status, color: '#6b7280', icon: '📋' };
    return (
      <div className="rp-status-badge" style={{ backgroundColor: `${config.color}15`, borderColor: config.color }}>
        <span className="rp-status-icon">{config.icon}</span>
        <span style={{ color: config.color }}>{config.label}</span>
      </div>
    );
  };

  const getProgressPercentage = (status) => {
    const stages = ['new', 'screening', 'phone_screen', 'interview', 'assessment', 'offer', 'hired'];
    const index = stages.indexOf(status);
    if (index === -1) return 0;
    return Math.round(((index + 1) / stages.length) * 100);
  };

  const handleExpressInterest = async (jobId) => {
    try {
      await fetch(`${API_URL}/api/v1/recruit-portal/${accessToken}/express-interest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId })
      });
      setShowInterestModal(false);
      // Reload to get updated data
      window.location.reload();
    } catch (err) {
      console.error('Failed to express interest:', err);
    }
  };

  if (loading) {
    return (
      <div className="rp-container">
        <div className="rp-loading">
          <div className="rp-spinner"></div>
          <p>Loading your application portal...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rp-container">
        <div className="rp-error-page">
          <div className="rp-error-icon">🔒</div>
          <h2>Access Denied</h2>
          <p>{error}</p>
          <p className="rp-error-help">
            If you believe this is an error, please contact the hiring team.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rp-container">
      {/* Header */}
      <header className="rp-header">
        <div className="rp-header-content">
          <div className="rp-logo">
            <span className="rp-logo-icon">🏢</span>
            <span className="rp-logo-text">Candidate Portal</span>
          </div>
          <div className="rp-user-info">
            <span className="rp-user-name">{candidate?.name}</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="rp-main">
        {/* Welcome Banner */}
        <section className="rp-welcome-banner">
          <div className="rp-welcome-content">
            <h1>Welcome, {candidate?.first_name}! 👋</h1>
            <p>Track your application progress and stay connected with our team.</p>
          </div>
          <div className="rp-status-section">
            {getStatusBadge(candidate?.status)}
          </div>
        </section>

        {/* Progress Bar */}
        <section className="rp-progress-section">
          <div className="rp-progress-header">
            <h3>Application Progress</h3>
            <span className="rp-progress-percent">{getProgressPercentage(candidate?.status)}%</span>
          </div>
          <div className="rp-progress-bar">
            <div
              className="rp-progress-fill"
              style={{ width: `${getProgressPercentage(candidate?.status)}%` }}
            />
          </div>
          <div className="rp-progress-stages">
            <span className={candidate?.status === 'new' ? 'active' : ''}>Applied</span>
            <span className={['screening', 'phone_screen'].includes(candidate?.status) ? 'active' : ''}>Review</span>
            <span className={candidate?.status === 'interview' ? 'active' : ''}>Interview</span>
            <span className={candidate?.status === 'assessment' ? 'active' : ''}>Assessment</span>
            <span className={['offer', 'hired'].includes(candidate?.status) ? 'active' : ''}>Decision</span>
          </div>
        </section>

        {/* Navigation Tabs */}
        <nav className="rp-tabs">
          <button
            className={`rp-tab ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview
          </button>
          <button
            className={`rp-tab ${activeTab === 'timeline' ? 'active' : ''}`}
            onClick={() => setActiveTab('timeline')}
          >
            Timeline
          </button>
          <button
            className={`rp-tab ${activeTab === 'interviews' ? 'active' : ''}`}
            onClick={() => setActiveTab('interviews')}
          >
            Interviews
          </button>
          <button
            className={`rp-tab ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('profile')}
          >
            My Profile
          </button>
        </nav>

        {/* Tab Content */}
        <div className="rp-content">
          {activeTab === 'overview' && (
            <div className="rp-overview">
              {/* Position Card */}
              <div className="rp-card rp-position-card">
                <h3>Applied Position</h3>
                <div className="rp-position-info">
                  <div className="rp-position-title">{candidate?.target_role || 'General Application'}</div>
                  <div className="rp-position-meta">
                    <span>Applied: {candidate?.applied_at ? new Date(candidate.applied_at).toLocaleDateString() : 'N/A'}</span>
                  </div>
                </div>
              </div>

              {/* Quick Stats */}
              <div className="rp-stats-grid">
                <div className="rp-stat-card">
                  <div className="rp-stat-icon">📅</div>
                  <div className="rp-stat-value">{candidate?.interviews?.length || 0}</div>
                  <div className="rp-stat-label">Interviews</div>
                </div>
                <div className="rp-stat-card">
                  <div className="rp-stat-icon">💬</div>
                  <div className="rp-stat-value">{candidate?.activities?.length || 0}</div>
                  <div className="rp-stat-label">Updates</div>
                </div>
                <div className="rp-stat-card">
                  <div className="rp-stat-icon">📄</div>
                  <div className="rp-stat-value">{candidate?.documents?.length || 0}</div>
                  <div className="rp-stat-label">Documents</div>
                </div>
              </div>

              {/* Next Steps */}
              <div className="rp-card rp-next-steps">
                <h3>Next Steps</h3>
                <div className="rp-steps-list">
                  {candidate?.next_steps?.length > 0 ? (
                    candidate.next_steps.map((step, idx) => (
                      <div key={idx} className="rp-step-item">
                        <div className="rp-step-number">{idx + 1}</div>
                        <div className="rp-step-content">
                          <div className="rp-step-title">{step.title}</div>
                          <div className="rp-step-desc">{step.description}</div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rp-no-data">
                      <span className="rp-no-data-icon">✨</span>
                      <p>No pending action items. We'll be in touch soon!</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'timeline' && (
            <div className="rp-timeline">
              <h3>Application Timeline</h3>
              <div className="rp-timeline-list">
                {candidate?.activities?.length > 0 ? (
                  candidate.activities.map((activity, idx) => (
                    <div key={idx} className="rp-timeline-item">
                      <div className="rp-timeline-dot"></div>
                      <div className="rp-timeline-content">
                        <div className="rp-timeline-title">{activity.description}</div>
                        <div className="rp-timeline-date">
                          {new Date(activity.timestamp).toLocaleDateString()} at {new Date(activity.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rp-no-data">
                    <span className="rp-no-data-icon">📜</span>
                    <p>Your application timeline will appear here.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'interviews' && (
            <div className="rp-interviews">
              <h3>Scheduled Interviews</h3>
              {candidate?.interviews?.length > 0 ? (
                <div className="rp-interviews-list">
                  {candidate.interviews.map((interview, idx) => (
                    <div key={idx} className="rp-card rp-interview-card">
                      <div className="rp-interview-header">
                        <span className="rp-interview-type">{interview.type || 'Interview'}</span>
                        <span className={`rp-interview-status ${interview.status}`}>{interview.status}</span>
                      </div>
                      <div className="rp-interview-datetime">
                        <span className="rp-interview-icon">📅</span>
                        <span>{new Date(interview.scheduled_at).toLocaleDateString()}</span>
                        <span className="rp-interview-icon">🕐</span>
                        <span>{new Date(interview.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                      {interview.meeting_url && (
                        <a
                          href={interview.meeting_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="rp-btn rp-btn-primary"
                        >
                          Join Meeting
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rp-no-data">
                  <span className="rp-no-data-icon">📅</span>
                  <p>No interviews scheduled yet.</p>
                  <p className="rp-no-data-hint">We'll notify you when an interview is scheduled.</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'profile' && (
            <div className="rp-profile">
              <h3>Your Profile</h3>
              <div className="rp-card rp-profile-card">
                <div className="rp-profile-header">
                  <div className="rp-avatar">
                    {candidate?.headshot_url ? (
                      <img src={candidate.headshot_url} alt={candidate.name} />
                    ) : (
                      <span className="rp-avatar-initials">
                        {candidate?.first_name?.[0]}{candidate?.last_name?.[0]}
                      </span>
                    )}
                  </div>
                  <div className="rp-profile-name">
                    <h4>{candidate?.name}</h4>
                    <p>{candidate?.email}</p>
                  </div>
                </div>

                <div className="rp-profile-section">
                  <h5>Contact Information</h5>
                  <div className="rp-profile-row">
                    <span className="rp-profile-label">Email</span>
                    <span className="rp-profile-value">{candidate?.email}</span>
                  </div>
                  <div className="rp-profile-row">
                    <span className="rp-profile-label">Phone</span>
                    <span className="rp-profile-value">{candidate?.phone || 'Not provided'}</span>
                  </div>
                </div>

                {candidate?.production && (
                  <div className="rp-profile-section">
                    <h5>Professional Background</h5>
                    <div className="rp-profile-row">
                      <span className="rp-profile-label">Current Company</span>
                      <span className="rp-profile-value">{candidate.production.current_company || 'Not provided'}</span>
                    </div>
                    <div className="rp-profile-row">
                      <span className="rp-profile-label">Current Title</span>
                      <span className="rp-profile-value">{candidate.production.current_title || 'Not provided'}</span>
                    </div>
                    {candidate.production.nmls_id && (
                      <div className="rp-profile-row">
                        <span className="rp-profile-label">NMLS ID</span>
                        <span className="rp-profile-value">{candidate.production.nmls_id}</span>
                      </div>
                    )}
                    {candidate.production.annual_volume && (
                      <div className="rp-profile-row">
                        <span className="rp-profile-label">Annual Volume</span>
                        <span className="rp-profile-value">${(candidate.production.annual_volume / 1000000).toFixed(1)}M</span>
                      </div>
                    )}
                  </div>
                )}

                {(candidate?.social_media?.linkedin || candidate?.social_media?.facebook) && (
                  <div className="rp-profile-section">
                    <h5>Social Profiles</h5>
                    <div className="rp-social-links">
                      {candidate.social_media.linkedin && (
                        <a href={candidate.social_media.linkedin} target="_blank" rel="noopener noreferrer" className="rp-social-link linkedin">
                          LinkedIn
                        </a>
                      )}
                      {candidate.social_media.facebook && (
                        <a href={candidate.social_media.facebook} target="_blank" rel="noopener noreferrer" className="rp-social-link facebook">
                          Facebook
                        </a>
                      )}
                      {candidate.social_media.instagram && (
                        <a href={candidate.social_media.instagram} target="_blank" rel="noopener noreferrer" className="rp-social-link instagram">
                          Instagram
                        </a>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="rp-footer">
        <p>Need help? Contact our recruiting team</p>
        <p className="rp-footer-brand">Powered by Perennia AI</p>
      </footer>
    </div>
  );
};

export default RecruitPortal;
