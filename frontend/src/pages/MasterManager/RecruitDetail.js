import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getCandidateFullProfile,
  updateCandidateStatus,
  updateCandidateSocialMedia,
  updateCandidateProduction,
  addCandidateNote
} from '../../services/masterManagerApi';
import './MasterManager.css';

const CANDIDATE_STATUSES = [
  { value: 'new', label: 'New', color: '#3b82f6' },
  { value: 'screening', label: 'Screening', color: '#8b5cf6' },
  { value: 'phone_screen', label: 'Phone Screen', color: '#a855f7' },
  { value: 'interview', label: 'Interview', color: '#f59e0b' },
  { value: 'assessment', label: 'Assessment', color: '#eab308' },
  { value: 'offer', label: 'Offer', color: '#22c55e' },
  { value: 'hired', label: 'Hired', color: '#10b981' },
  { value: 'rejected', label: 'Rejected', color: '#ef4444' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#6b7280' }
];

const RecruitDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [candidate, setCandidate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [showEditSocial, setShowEditSocial] = useState(false);
  const [showEditProduction, setShowEditProduction] = useState(false);
  const [newNote, setNewNote] = useState('');

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
      const data = await getCandidateFullProfile(id);
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
  }, [id]);

  useEffect(() => {
    loadCandidate();
  }, [loadCandidate]);

  const handleStatusChange = async (newStatus) => {
    try {
      await updateCandidateStatus(id, newStatus);
      setCandidate({ ...candidate, status: newStatus });
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSaveSocial = async () => {
    try {
      await updateCandidateSocialMedia(id, socialForm);
      await loadCandidate();
      setShowEditSocial(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSaveProduction = async () => {
    try {
      await updateCandidateProduction(id, productionForm);
      await loadCandidate();
      setShowEditProduction(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) return;
    try {
      await addCandidateNote(id, { content: newNote, note_type: 'general' });
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

  return (
    <div className="mm-container">
      {/* Header */}
      <div className="mm-header">
        <div className="mm-header-left">
          <button className="mm-btn mm-btn-secondary" onClick={() => navigate(-1)}>
            &larr; Back
          </button>
          <div style={{ marginLeft: '20px' }}>
            <h1>{candidate.name}</h1>
            <p>{candidate.target_role || 'Candidate'} {candidate.production?.current_company ? `at ${candidate.production.current_company}` : ''}</p>
          </div>
        </div>
        <div className="mm-header-actions">
          <select
            value={candidate.status}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="mm-select"
            style={{ backgroundColor: getStatusColor(candidate.status), color: 'white', fontWeight: 'bold' }}
          >
            {CANDIDATE_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Profile Header Card */}
      <div className="mm-card" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '30px', alignItems: 'flex-start' }}>
          {/* Avatar */}
          <div
            className="mm-user-avatar"
            style={{
              width: '120px',
              height: '120px',
              fontSize: '48px',
              backgroundColor: getStatusColor(candidate.status),
              backgroundImage: candidate.profile?.headshot_url ? `url(${candidate.profile.headshot_url})` : 'none',
              backgroundSize: 'cover',
              backgroundPosition: 'center'
            }}
          >
            {!candidate.profile?.headshot_url && candidate.first_name?.charAt(0)}
          </div>

          {/* Basic Info */}
          <div style={{ flex: 1 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
              <div>
                <label className="mm-stat-label">Email</label>
                <p style={{ margin: 0 }}>{candidate.email || '-'}</p>
              </div>
              <div>
                <label className="mm-stat-label">Phone</label>
                <p style={{ margin: 0 }}>{candidate.phone || '-'}</p>
              </div>
              <div>
                <label className="mm-stat-label">Source</label>
                <p style={{ margin: 0 }}>
                  {candidate.source === 'retr' ? (
                    <span className="mm-badge mm-badge-info">RETR</span>
                  ) : (
                    candidate.source || 'Direct'
                  )}
                </p>
              </div>
              <div>
                <label className="mm-stat-label">NMLS ID</label>
                <p style={{ margin: 0 }}>{candidate.production?.nmls_id || '-'}</p>
              </div>
              <div>
                <label className="mm-stat-label">Experience</label>
                <p style={{ margin: 0 }}>{candidate.experience?.years_total || 0} years</p>
              </div>
              <div>
                <label className="mm-stat-label">Applied</label>
                <p style={{ margin: 0 }}>{candidate.applied_at ? new Date(candidate.applied_at).toLocaleDateString() : '-'}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="mm-tabs" style={{ marginBottom: '20px' }}>
        <button
          className={`mm-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`mm-tab ${activeTab === 'production' ? 'active' : ''}`}
          onClick={() => setActiveTab('production')}
        >
          Production
        </button>
        <button
          className={`mm-tab ${activeTab === 'social' ? 'active' : ''}`}
          onClick={() => setActiveTab('social')}
        >
          Social Media
        </button>
        <button
          className={`mm-tab ${activeTab === 'interviews' ? 'active' : ''}`}
          onClick={() => setActiveTab('interviews')}
        >
          Interviews
        </button>
        <button
          className={`mm-tab ${activeTab === 'notes' ? 'active' : ''}`}
          onClick={() => setActiveTab('notes')}
        >
          Notes & Activity
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="mm-overview-grid">
          {/* Production Summary Card */}
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value" style={{ color: '#22c55e' }}>
              {formatCurrency(candidate.production?.annual_volume)}
            </div>
            <div className="mm-stat-label">Annual Volume</div>
          </div>
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value">{candidate.production?.annual_units || 0}</div>
            <div className="mm-stat-label">Annual Units</div>
          </div>
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value">{candidate.experience?.years_mortgage || 0}</div>
            <div className="mm-stat-label">Mortgage Experience (yrs)</div>
          </div>
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value">{(candidate.production?.license_states || []).length}</div>
            <div className="mm-stat-label">Licensed States</div>
          </div>

          {/* Bio Section */}
          {candidate.profile?.bio && (
            <div className="mm-card" style={{ gridColumn: 'span 4' }}>
              <h3 style={{ marginTop: 0 }}>About</h3>
              <p>{candidate.profile.bio}</p>
            </div>
          )}

          {/* Scores */}
          {(candidate.scores?.overall || candidate.scores?.vetting) && (
            <div className="mm-card" style={{ gridColumn: 'span 2' }}>
              <h3 style={{ marginTop: 0 }}>Assessment Scores</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '15px' }}>
                <div>
                  <label className="mm-stat-label">Overall</label>
                  <div className="mm-stat-value" style={{ fontSize: '24px' }}>
                    {candidate.scores?.overall?.toFixed(1) || '-'}
                  </div>
                </div>
                <div>
                  <label className="mm-stat-label">Culture Fit</label>
                  <div className="mm-stat-value" style={{ fontSize: '24px' }}>
                    {candidate.scores?.culture_fit?.toFixed(1) || '-'}
                  </div>
                </div>
                <div>
                  <label className="mm-stat-label">Technical</label>
                  <div className="mm-stat-value" style={{ fontSize: '24px' }}>
                    {candidate.scores?.technical?.toFixed(1) || '-'}
                  </div>
                </div>
                <div>
                  <label className="mm-stat-label">Behavioral</label>
                  <div className="mm-stat-value" style={{ fontSize: '24px' }}>
                    {candidate.scores?.behavioral?.toFixed(1) || '-'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Licensed States */}
          {candidate.production?.license_states?.length > 0 && (
            <div className="mm-card" style={{ gridColumn: 'span 2' }}>
              <h3 style={{ marginTop: 0 }}>Licensed States</h3>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {candidate.production.license_states.map((state, idx) => (
                  <span key={idx} className="mm-badge mm-badge-info">{state}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Production Tab */}
      {activeTab === 'production' && (
        <div className="mm-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2>Production Data (RETR)</h2>
            <button className="mm-btn mm-btn-secondary" onClick={() => setShowEditProduction(true)}>
              Edit Production
            </button>
          </div>

          <div className="mm-overview-grid">
            <div className="mm-card mm-stat-card">
              <div className="mm-stat-value" style={{ color: '#22c55e' }}>
                {formatCurrency(candidate.production?.annual_volume)}
              </div>
              <div className="mm-stat-label">Annual Volume</div>
            </div>
            <div className="mm-card mm-stat-card">
              <div className="mm-stat-value">{candidate.production?.annual_units || 0}</div>
              <div className="mm-stat-label">Annual Units</div>
            </div>
            <div className="mm-card mm-stat-card">
              <div className="mm-stat-value">
                {formatCurrency(candidate.production?.avg_loan_size)}
              </div>
              <div className="mm-stat-label">Average Loan Size</div>
            </div>
            <div className="mm-card mm-stat-card">
              <div className="mm-stat-value">{candidate.production?.nmls_id || '-'}</div>
              <div className="mm-stat-label">NMLS ID</div>
            </div>
          </div>

          <div className="mm-card" style={{ marginTop: '20px' }}>
            <h3 style={{ marginTop: 0 }}>Current Position</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px' }}>
              <div>
                <label className="mm-stat-label">Company</label>
                <p style={{ margin: 0, fontSize: '18px' }}>{candidate.production?.current_company || '-'}</p>
              </div>
              <div>
                <label className="mm-stat-label">Title</label>
                <p style={{ margin: 0, fontSize: '18px' }}>{candidate.production?.current_title || '-'}</p>
              </div>
            </div>
          </div>

          {candidate.production?.production_history?.length > 0 && (
            <div className="mm-card" style={{ marginTop: '20px' }}>
              <h3 style={{ marginTop: 0 }}>Production History</h3>
              <div className="mm-table-container">
                <table className="mm-table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Volume</th>
                      <th>Units</th>
                      <th>Company</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidate.production.production_history.map((row, idx) => (
                      <tr key={idx}>
                        <td>{row.year}</td>
                        <td>{formatCurrency(row.volume)}</td>
                        <td>{row.units}</td>
                        <td>{row.company || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Social Media Tab */}
      {activeTab === 'social' && (
        <div className="mm-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2>Social Media Profiles</h2>
            <button className="mm-btn mm-btn-secondary" onClick={() => setShowEditSocial(true)}>
              Edit Social Media
            </button>
          </div>

          <div className="mm-overview-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            {/* LinkedIn */}
            <div className="mm-card" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '48px', marginBottom: '10px' }}>in</div>
              <h4 style={{ margin: '0 0 10px 0' }}>LinkedIn</h4>
              {candidate.social_media?.linkedin ? (
                <a
                  href={candidate.social_media.linkedin}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mm-btn mm-btn-primary mm-btn-small"
                >
                  View Profile
                </a>
              ) : (
                <span className="mm-stat-label">Not connected</span>
              )}
            </div>

            {/* Facebook */}
            <div className="mm-card" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '48px', marginBottom: '10px', color: '#1877f2' }}>f</div>
              <h4 style={{ margin: '0 0 10px 0' }}>Facebook</h4>
              {candidate.social_media?.facebook ? (
                <a
                  href={candidate.social_media.facebook}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mm-btn mm-btn-primary mm-btn-small"
                >
                  View Profile
                </a>
              ) : (
                <span className="mm-stat-label">Not connected</span>
              )}
            </div>

            {/* Instagram */}
            <div className="mm-card" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '48px', marginBottom: '10px', color: '#e4405f' }}>ig</div>
              <h4 style={{ margin: '0 0 10px 0' }}>Instagram</h4>
              {candidate.social_media?.instagram ? (
                <a
                  href={candidate.social_media.instagram}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mm-btn mm-btn-primary mm-btn-small"
                >
                  View Profile
                </a>
              ) : (
                <span className="mm-stat-label">Not connected</span>
              )}
            </div>

            {/* Twitter */}
            <div className="mm-card" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '48px', marginBottom: '10px', color: '#1da1f2' }}>X</div>
              <h4 style={{ margin: '0 0 10px 0' }}>Twitter/X</h4>
              {candidate.social_media?.twitter ? (
                <a
                  href={candidate.social_media.twitter}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mm-btn mm-btn-primary mm-btn-small"
                >
                  View Profile
                </a>
              ) : (
                <span className="mm-stat-label">Not connected</span>
              )}
            </div>
          </div>

          {/* Recent Posts */}
          {candidate.social_media?.recent_posts?.length > 0 && (
            <div className="mm-card" style={{ marginTop: '20px' }}>
              <h3 style={{ marginTop: 0 }}>Recent Posts</h3>
              <div className="mm-social-posts">
                {candidate.social_media.recent_posts.map((post, idx) => (
                  <div key={idx} className="mm-social-post" style={{
                    padding: '15px',
                    borderBottom: '1px solid var(--border-color)',
                    marginBottom: '10px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                      <span className="mm-badge">{post.platform}</span>
                      <span className="mm-stat-label">{new Date(post.posted_at).toLocaleDateString()}</span>
                    </div>
                    <p style={{ margin: 0 }}>{post.content}</p>
                    {post.engagement && (
                      <div style={{ marginTop: '10px', display: 'flex', gap: '15px' }}>
                        <span>Likes: {post.engagement.likes || 0}</span>
                        <span>Comments: {post.engagement.comments || 0}</span>
                        <span>Shares: {post.engagement.shares || 0}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {candidate.social_media?.last_synced && (
            <p className="mm-stat-label" style={{ marginTop: '10px' }}>
              Last synced: {new Date(candidate.social_media.last_synced).toLocaleString()}
            </p>
          )}
        </div>
      )}

      {/* Interviews Tab */}
      {activeTab === 'interviews' && (
        <div className="mm-section">
          <h2>Interview History</h2>
          {candidate.interviews?.length === 0 ? (
            <div className="mm-card">
              <p style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
                No interviews scheduled yet
              </p>
            </div>
          ) : (
            <div className="mm-table-container">
              <table className="mm-table">
                <thead>
                  <tr>
                    <th>Round</th>
                    <th>Type</th>
                    <th>Date</th>
                    <th>Status</th>
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {candidate.interviews?.map((interview) => (
                    <tr key={interview.id}>
                      <td>Round {interview.round}</td>
                      <td>{interview.type}</td>
                      <td>{interview.scheduled_at ? new Date(interview.scheduled_at).toLocaleString() : '-'}</td>
                      <td>
                        <span className={`mm-status-badge mm-status-${interview.status}`}>
                          {interview.status}
                        </span>
                      </td>
                      <td>{interview.score?.toFixed(1) || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Notes & Activity Tab */}
      {activeTab === 'notes' && (
        <div className="mm-section">
          <h2>Notes & Activity</h2>

          {/* Add Note */}
          <div className="mm-card" style={{ marginBottom: '20px' }}>
            <h4 style={{ marginTop: 0 }}>Add Note</h4>
            <textarea
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              placeholder="Add a note about this candidate..."
              className="mm-textarea"
              rows="3"
            />
            <button
              className="mm-btn mm-btn-primary"
              onClick={handleAddNote}
              style={{ marginTop: '10px' }}
              disabled={!newNote.trim()}
            >
              Add Note
            </button>
          </div>

          {/* Notes List */}
          {candidate.notes?.length > 0 && (
            <div className="mm-card" style={{ marginBottom: '20px' }}>
              <h4 style={{ marginTop: 0 }}>Notes</h4>
              {candidate.notes.map((note) => (
                <div key={note.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border-color)' }}>
                  <p style={{ margin: 0 }}>{note.content}</p>
                  <span className="mm-stat-label">
                    {note.created_at ? new Date(note.created_at).toLocaleString() : ''}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Activity Timeline */}
          <div className="mm-card">
            <h4 style={{ marginTop: 0 }}>Activity Timeline</h4>
            {candidate.activities?.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)' }}>No activity yet</p>
            ) : (
              <div className="mm-timeline">
                {candidate.activities?.map((activity) => (
                  <div key={activity.id} className="mm-timeline-item" style={{
                    padding: '10px 0 10px 20px',
                    borderLeft: '2px solid var(--primary-color)',
                    marginBottom: '10px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span className="mm-badge">{activity.type}</span>
                      <span className="mm-stat-label">
                        {activity.timestamp ? new Date(activity.timestamp).toLocaleString() : ''}
                      </span>
                    </div>
                    <p style={{ margin: '5px 0 0 0' }}>{activity.description}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
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
    </div>
  );
};

export default RecruitDetail;
