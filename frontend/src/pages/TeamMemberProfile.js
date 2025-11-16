import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teamAPI } from '../services/api';
import ImpersonationModal from '../components/ImpersonationModal';
import PermissionsTab from '../components/PermissionsTab';
import AccessAuditTab from '../components/AccessAuditTab';
import './TeamMemberProfile.css';

function TeamMemberProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [member, setMember] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [editing, setEditing] = useState(false);
  const [formData, setFormData] = useState({});
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [showImpersonationModal, setShowImpersonationModal] = useState(false);
  const [auditLog, setAuditLog] = useState([]);
  const [impersonationHistory, setImpersonationHistory] = useState([]);
  const [activeSessions, setActiveSessions] = useState([]);
  const [loadingAudit, setLoadingAudit] = useState(false);

  useEffect(() => {
    loadMemberData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadMemberData = async () => {
    try {
      setLoading(true);
      const data = await teamAPI.getMemberDetail(id);
      setMember(data);
      setFormData(data);
    } catch (error) {
      console.error('Failed to load team member:', error);
      alert('Failed to load team member details');
    } finally {
      setLoading(false);
    }
  };

  const loadAuditData = async () => {
    try {
      setLoadingAudit(true);

      // Load audit log
      const auditResponse = await fetch(`/api/v1/users/${id}/audit-log?limit=50`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const auditData = await auditResponse.json();
      setAuditLog(auditData.changes || []);

      // Load impersonation history
      const impersonationResponse = await fetch(`/api/v1/users/${id}/impersonation-history`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const impersonationData = await impersonationResponse.json();
      setImpersonationHistory(impersonationData.sessions || []);

      // Load active sessions
      const sessionsResponse = await fetch(`/api/v1/users/${id}/active-sessions`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const sessionsData = await sessionsResponse.json();
      setActiveSessions(sessionsData.sessions || []);
    } catch (error) {
      console.error('Failed to load audit data:', error);
    } finally {
      setLoadingAudit(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'access-audit' && member) {
      loadAuditData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, member]);

  const handleSave = async () => {
    try {
      await teamAPI.updateMember(id, formData);
      setMember(formData);
      setEditing(false);
      alert('Team member updated successfully!');
    } catch (error) {
      console.error('Failed to update team member:', error);
      alert('Failed to update team member');
    }
  };

  const handleFieldChange = (field, value) => {
    setFormData({ ...formData, [field]: value });
  };

  const handlePhotoUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      alert('Please select an image file');
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      alert('File size must be less than 5MB');
      return;
    }

    try {
      setUploadingPhoto(true);
      const formData = new FormData();
      formData.append('photo', file);

      // TODO: Update this endpoint when backend support is added
      // await teamAPI.uploadPhoto(id, formData);

      // For now, create a local URL preview
      const photoUrl = URL.createObjectURL(file);
      setFormData(prev => ({ ...prev, photo_url: photoUrl }));
      setMember(prev => ({ ...prev, photo_url: photoUrl }));

      alert('Photo uploaded successfully! (Note: This is a preview. Backend integration pending)');
    } catch (error) {
      console.error('Failed to upload photo:', error);
      alert('Failed to upload photo');
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleImpersonate = () => {
    setShowImpersonationModal(true);
  };

  const handleRevokeSession = async (sessionId) => {
    if (!window.confirm('Are you sure you want to revoke this session? The user will be logged out immediately.')) {
      return;
    }

    try {
      const response = await fetch(`/api/v1/users/${id}/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          reason: 'Session revoked by administrator'
        })
      });

      if (!response.ok) {
        throw new Error('Failed to revoke session');
      }

      alert('Session revoked successfully');
      loadAuditData(); // Reload to refresh the session list
    } catch (error) {
      console.error('Failed to revoke session:', error);
      alert('Failed to revoke session');
    }
  };

  const handleRevokeAllSessions = async () => {
    if (!window.confirm('⚠️ WARNING: This will log out the user from ALL devices immediately. Are you sure?')) {
      return;
    }

    const reason = window.prompt('Please provide a reason for revoking all sessions:');
    if (!reason) {
      alert('Reason is required');
      return;
    }

    try {
      const response = await fetch(`/api/v1/users/${id}/sessions`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ reason })
      });

      if (!response.ok) {
        throw new Error('Failed to revoke sessions');
      }

      const data = await response.json();
      alert(`Success: ${data.message}`);
      loadAuditData(); // Reload to refresh the session list
    } catch (error) {
      console.error('Failed to revoke all sessions:', error);
      alert('Failed to revoke all sessions');
    }
  };

  if (loading) {
    return (
      <div className="team-member-profile-page">
        <div className="loading">Loading team member...</div>
      </div>
    );
  }

  if (!member) {
    return (
      <div className="team-member-profile-page">
        <div className="error">Team member not found</div>
      </div>
    );
  }

  return (
    <div className="team-member-profile-page">
      {/* Back Button */}
      <div className="profile-header">
        <button className="btn-back" onClick={() => navigate('/team-members')}>
          ← Back to Team Members
        </button>
        <div className="header-actions">
          {editing ? (
            <>
              <button className="btn-save" onClick={handleSave}>Save</button>
              <button className="btn-cancel" onClick={() => { setEditing(false); setFormData(member); }}>Cancel</button>
            </>
          ) : (
            <button className="btn-edit-header" onClick={() => setEditing(true)}>
              ✏️ Edit
            </button>
          )}
        </div>
      </div>

      {/* Green Header Bar with Profile Picture, Name, Tabs, and Impersonate Button */}
      <div className="profile-green-bar">
        <div className="profile-left-section">
          {/* Profile Picture */}
          <div className="member-avatar-section">
            <input
              type="file"
              id="photo-upload"
              accept="image/*"
              onChange={handlePhotoUpload}
              style={{ display: 'none' }}
            />
            <label htmlFor="photo-upload" className="avatar-upload-label">
              <div className="avatar-circle-new">
                {formData.photo_url || member.photo_url ? (
                  <img src={formData.photo_url || member.photo_url} alt={`${member.first_name} ${member.last_name}`} />
                ) : (
                  <span className="avatar-initials">{member.first_name?.[0]}{member.last_name?.[0]}</span>
                )}
                <div className="avatar-upload-overlay">
                  {uploadingPhoto ? '⏳' : '📷'}
                </div>
              </div>
            </label>
          </div>

          {/* Member Name and Info */}
          <div className="member-name-section">
            <h1 className="member-name-header">{member.first_name} {member.last_name}</h1>
            <p className="member-role-header">{member.role}</p>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="profile-tabs-new">
          <button
            className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview
          </button>
          <button
            className={`tab-btn ${activeTab === 'kpis' ? 'active' : ''}`}
            onClick={() => setActiveTab('kpis')}
          >
            KPIs
          </button>
          <button
            className={`tab-btn ${activeTab === 'notes' ? 'active' : ''}`}
            onClick={() => setActiveTab('notes')}
          >
            Notes & Meetings
          </button>
          <button
            className={`tab-btn ${activeTab === 'personality' ? 'active' : ''}`}
            onClick={() => setActiveTab('personality')}
          >
            DISC Profile
          </button>
          <button
            className={`tab-btn ${activeTab === 'personal' ? 'active' : ''}`}
            onClick={() => setActiveTab('personal')}
          >
            Personal Info
          </button>
          <button
            className={`tab-btn ${activeTab === 'goals' ? 'active' : ''}`}
            onClick={() => setActiveTab('goals')}
          >
            Goals
          </button>
          <button
            className={`tab-btn ${activeTab === 'permissions' ? 'active' : ''}`}
            onClick={() => setActiveTab('permissions')}
          >
            Permissions
          </button>
          <button
            className={`tab-btn ${activeTab === 'access-audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('access-audit')}
          >
            Access & Audit
          </button>
        </div>

        {/* Impersonate Button */}
        <div className="profile-right-section">
          <button className="btn-impersonate" onClick={handleImpersonate} title="View CRM as this user">
            👤 Impersonate
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="tab-panel">
            <h2>Overview</h2>
            <div className="info-grid">
              <div className="info-field">
                <label>Employee ID</label>
                <input
                  type="text"
                  value={formData.employee_id || ''}
                  onChange={(e) => handleFieldChange('employee_id', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Start Date</label>
                <input
                  type="date"
                  value={formData.start_date || ''}
                  onChange={(e) => handleFieldChange('start_date', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Department</label>
                <input
                  type="text"
                  value={formData.department || ''}
                  onChange={(e) => handleFieldChange('department', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Manager</label>
                <input
                  type="text"
                  value={formData.manager || ''}
                  onChange={(e) => handleFieldChange('manager', e.target.value)}
                  disabled={!editing}
                />
              </div>
            </div>
          </div>
        )}

        {/* KPIs Tab */}
        {activeTab === 'kpis' && (
          <div className="tab-panel">
            <h2>Key Performance Indicators</h2>
            <div className="kpi-grid">
              <div className="kpi-card">
                <h3>Loans Processed</h3>
                <div className="kpi-value">{formData.loans_processed || 0}</div>
                <div className="kpi-period">This Month</div>
              </div>
              <div className="kpi-card">
                <h3>Average Close Time</h3>
                <div className="kpi-value">{formData.avg_close_time || 0} days</div>
                <div className="kpi-period">Last 30 Days</div>
              </div>
              <div className="kpi-card">
                <h3>Customer Satisfaction</h3>
                <div className="kpi-value">{formData.satisfaction_score || 0}%</div>
                <div className="kpi-period">Overall</div>
              </div>
              <div className="kpi-card">
                <h3>Volume</h3>
                <div className="kpi-value">${(formData.volume || 0).toLocaleString()}</div>
                <div className="kpi-period">This Quarter</div>
              </div>
            </div>

            <div className="kpi-details">
              <h3>Monthly Performance</h3>
              <div className="info-grid">
                <div className="info-field">
                  <label>Loans Processed</label>
                  <input
                    type="number"
                    value={formData.loans_processed || ''}
                    onChange={(e) => handleFieldChange('loans_processed', e.target.value)}
                    disabled={!editing}
                  />
                </div>
                <div className="info-field">
                  <label>Average Close Time (days)</label>
                  <input
                    type="number"
                    value={formData.avg_close_time || ''}
                    onChange={(e) => handleFieldChange('avg_close_time', e.target.value)}
                    disabled={!editing}
                  />
                </div>
                <div className="info-field">
                  <label>Satisfaction Score (%)</label>
                  <input
                    type="number"
                    value={formData.satisfaction_score || ''}
                    onChange={(e) => handleFieldChange('satisfaction_score', e.target.value)}
                    disabled={!editing}
                    min="0"
                    max="100"
                  />
                </div>
                <div className="info-field">
                  <label>Volume ($)</label>
                  <input
                    type="number"
                    value={formData.volume || ''}
                    onChange={(e) => handleFieldChange('volume', e.target.value)}
                    disabled={!editing}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Notes & Meetings Tab */}
        {activeTab === 'notes' && (
          <div className="tab-panel">
            <h2>Notes & Meetings</h2>
            <div className="notes-section">
              <div className="info-field">
                <label>Meeting Notes</label>
                <textarea
                  rows="8"
                  value={formData.meeting_notes || ''}
                  onChange={(e) => handleFieldChange('meeting_notes', e.target.value)}
                  disabled={!editing}
                  placeholder="Add notes from 1-on-1 meetings, performance reviews, etc."
                />
              </div>
              <div className="info-field">
                <label>General Notes</label>
                <textarea
                  rows="6"
                  value={formData.general_notes || ''}
                  onChange={(e) => handleFieldChange('general_notes', e.target.value)}
                  disabled={!editing}
                  placeholder="Any additional notes about this team member..."
                />
              </div>
            </div>
          </div>
        )}

        {/* DISC Profile Tab */}
        {activeTab === 'personality' && (
          <div className="tab-panel">
            <h2>DISC Personality Profile</h2>
            <div className="disc-grid">
              <div className="disc-card dominance">
                <h3>D - Dominance</h3>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={formData.disc_d || 50}
                  onChange={(e) => handleFieldChange('disc_d', e.target.value)}
                  disabled={!editing}
                />
                <div className="disc-value">{formData.disc_d || 50}%</div>
                <p>Direct, results-oriented, decisive</p>
              </div>
              <div className="disc-card influence">
                <h3>I - Influence</h3>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={formData.disc_i || 50}
                  onChange={(e) => handleFieldChange('disc_i', e.target.value)}
                  disabled={!editing}
                />
                <div className="disc-value">{formData.disc_i || 50}%</div>
                <p>Outgoing, enthusiastic, optimistic</p>
              </div>
              <div className="disc-card steadiness">
                <h3>S - Steadiness</h3>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={formData.disc_s || 50}
                  onChange={(e) => handleFieldChange('disc_s', e.target.value)}
                  disabled={!editing}
                />
                <div className="disc-value">{formData.disc_s || 50}%</div>
                <p>Even-tempered, accommodating, patient</p>
              </div>
              <div className="disc-card conscientiousness">
                <h3>C - Conscientiousness</h3>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={formData.disc_c || 50}
                  onChange={(e) => handleFieldChange('disc_c', e.target.value)}
                  disabled={!editing}
                />
                <div className="disc-value">{formData.disc_c || 50}%</div>
                <p>Analytical, reserved, precise</p>
              </div>
            </div>
            <div className="info-field">
              <label>DISC Summary</label>
              <textarea
                rows="4"
                value={formData.disc_summary || ''}
                onChange={(e) => handleFieldChange('disc_summary', e.target.value)}
                disabled={!editing}
                placeholder="Summary of DISC assessment results and communication preferences..."
              />
            </div>
          </div>
        )}

        {/* Personal Info Tab */}
        {activeTab === 'personal' && (
          <div className="tab-panel">
            <h2>Personal Information</h2>
            <div className="info-grid">
              <div className="info-field">
                <label>Birthday</label>
                <input
                  type="date"
                  value={formData.birthday || ''}
                  onChange={(e) => handleFieldChange('birthday', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Anniversary</label>
                <input
                  type="date"
                  value={formData.anniversary || ''}
                  onChange={(e) => handleFieldChange('anniversary', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Spouse/Partner Name</label>
                <input
                  type="text"
                  value={formData.spouse_name || ''}
                  onChange={(e) => handleFieldChange('spouse_name', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Children</label>
                <input
                  type="text"
                  value={formData.children || ''}
                  onChange={(e) => handleFieldChange('children', e.target.value)}
                  disabled={!editing}
                  placeholder="Names and ages"
                />
              </div>
              <div className="info-field">
                <label>Hobbies</label>
                <input
                  type="text"
                  value={formData.hobbies || ''}
                  onChange={(e) => handleFieldChange('hobbies', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Emergency Contact</label>
                <input
                  type="text"
                  value={formData.emergency_contact || ''}
                  onChange={(e) => handleFieldChange('emergency_contact', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Emergency Phone</label>
                <input
                  type="tel"
                  value={formData.emergency_phone || ''}
                  onChange={(e) => handleFieldChange('emergency_phone', e.target.value)}
                  disabled={!editing}
                />
              </div>
            </div>
          </div>
        )}

        {/* Goals Tab */}
        {activeTab === 'goals' && (
          <div className="tab-panel">
            <h2>Personal & Professional Goals</h2>
            <div className="goals-section">
              <div className="info-field">
                <label>Career Goals</label>
                <textarea
                  rows="4"
                  value={formData.career_goals || ''}
                  onChange={(e) => handleFieldChange('career_goals', e.target.value)}
                  disabled={!editing}
                  placeholder="Long-term career aspirations, desired positions, etc."
                />
              </div>
              <div className="info-field">
                <label>Q1 Goals</label>
                <textarea
                  rows="3"
                  value={formData.q1_goals || ''}
                  onChange={(e) => handleFieldChange('q1_goals', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Q2 Goals</label>
                <textarea
                  rows="3"
                  value={formData.q2_goals || ''}
                  onChange={(e) => handleFieldChange('q2_goals', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Q3 Goals</label>
                <textarea
                  rows="3"
                  value={formData.q3_goals || ''}
                  onChange={(e) => handleFieldChange('q3_goals', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Q4 Goals</label>
                <textarea
                  rows="3"
                  value={formData.q4_goals || ''}
                  onChange={(e) => handleFieldChange('q4_goals', e.target.value)}
                  disabled={!editing}
                />
              </div>
              <div className="info-field">
                <label>Development Areas</label>
                <textarea
                  rows="4"
                  value={formData.development_areas || ''}
                  onChange={(e) => handleFieldChange('development_areas', e.target.value)}
                  disabled={!editing}
                  placeholder="Skills to develop, training needs, etc."
                />
              </div>
            </div>
          </div>
        )}

        {/* Permissions Tab */}
        {activeTab === 'permissions' && (
          <div className="tab-panel">
            <PermissionsTab userId={member.id} />
          </div>
        )}

        {/* Access & Audit Tab */}
        {activeTab === 'access-audit' && (
          <div className="tab-panel">
            <h2>Access & Audit</h2>

            {loadingAudit ? (
              <div className="loading">Loading audit data...</div>
            ) : (
              <>
                {/* Section 1: Change History (Audit Log) */}
                <div className="audit-section">
                  <h3>📋 Change History</h3>
                  <p className="section-description">Complete log of all changes made to this employee's profile and permissions</p>

                  {auditLog.length === 0 ? (
                    <div className="empty-state">No changes recorded yet</div>
                  ) : (
                    <div className="audit-table-container">
                      <table className="audit-table">
                        <thead>
                          <tr>
                            <th>Date/Time</th>
                            <th>Changed By</th>
                            <th>Change Type</th>
                            <th>Entity</th>
                            <th>Before</th>
                            <th>After</th>
                            <th>Reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {auditLog.map((change) => (
                            <tr key={change.id}>
                              <td>{new Date(change.timestamp).toLocaleString()}</td>
                              <td>
                                {change.changed_by ? (
                                  <>
                                    <div>{change.changed_by.name}</div>
                                    <div className="text-muted">{change.changed_by.role}</div>
                                  </>
                                ) : 'System'}
                              </td>
                              <td>
                                <span className={`badge badge-${change.change_type}`}>
                                  {change.change_type}
                                </span>
                              </td>
                              <td>
                                <div>{change.entity_type}</div>
                                {change.entity_id && <div className="text-muted">ID: {change.entity_id}</div>}
                              </td>
                              <td className="code-cell">{JSON.stringify(change.before_state)}</td>
                              <td className="code-cell">{JSON.stringify(change.after_state)}</td>
                              <td>{change.reason || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Section 2: Impersonation History */}
                <div className="audit-section">
                  <h3>👤 Impersonation History</h3>
                  <p className="section-description">Record of all times this employee's account has been impersonated by managers</p>

                  {impersonationHistory.length === 0 ? (
                    <div className="empty-state">No impersonation sessions recorded</div>
                  ) : (
                    <div className="audit-table-container">
                      <table className="audit-table">
                        <thead>
                          <tr>
                            <th>Started</th>
                            <th>Ended</th>
                            <th>Duration</th>
                            <th>Manager</th>
                            <th>Reason</th>
                            <th>Mode</th>
                            <th>Employee Notified</th>
                          </tr>
                        </thead>
                        <tbody>
                          {impersonationHistory.map((session) => (
                            <tr key={session.id}>
                              <td>{new Date(session.started_at).toLocaleString()}</td>
                              <td>{session.ended_at ? new Date(session.ended_at).toLocaleString() : 'Active'}</td>
                              <td>{session.duration_minutes} min</td>
                              <td>
                                {session.manager ? session.manager.name : 'Unknown'}
                              </td>
                              <td>{session.reason || '-'}</td>
                              <td>
                                <span className={`badge badge-${session.mode}`}>
                                  {session.mode}
                                </span>
                              </td>
                              <td>
                                {session.employee_notified ? (
                                  <span className="badge badge-success">Yes</span>
                                ) : (
                                  <span className="badge badge-warning">No</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Section 3: Active Sessions */}
                <div className="audit-section">
                  <h3>🔓 Active Sessions</h3>
                  <p className="section-description">Currently active login sessions for this employee</p>

                  {activeSessions.length === 0 ? (
                    <div className="empty-state">No active sessions</div>
                  ) : (
                    <div className="audit-table-container">
                      <table className="audit-table">
                        <thead>
                          <tr>
                            <th>Logged In</th>
                            <th>IP Address</th>
                            <th>Location</th>
                            <th>Device</th>
                            <th>Last Activity</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {activeSessions.map((session) => (
                            <tr key={session.session_id}>
                              <td>{new Date(session.logged_in_at).toLocaleString()}</td>
                              <td>{session.ip_address}</td>
                              <td>{session.location || 'Unknown'}</td>
                              <td>{session.device || 'Unknown'}</td>
                              <td>{new Date(session.last_activity).toLocaleString()}</td>
                              <td>
                                <button
                                  className="btn-danger-small"
                                  onClick={() => handleRevokeSession(session.session_id)}
                                >
                                  Revoke
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Section 4: Emergency Actions */}
                <div className="audit-section emergency-section">
                  <h3>🚨 Emergency Actions</h3>
                  <p className="section-description">Critical security actions - use with caution</p>

                  <div className="emergency-actions">
                    <div className="emergency-action-card">
                      <h4>Revoke All Sessions</h4>
                      <p>Immediately log out this employee from all devices and locations. They will need to log in again.</p>
                      <button
                        className="btn-danger"
                        onClick={() => handleRevokeAllSessions()}
                      >
                        Revoke All Sessions
                      </button>
                    </div>

                    <div className="emergency-action-card">
                      <h4>Security Lockout</h4>
                      <p>Temporarily disable account access. Employee will not be able to log in until unlocked.</p>
                      <button
                        className="btn-danger"
                        onClick={() => alert('Account lockout feature coming soon')}
                      >
                        Lock Account
                      </button>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Impersonation Modal */}
      {showImpersonationModal && member && (
        <ImpersonationModal
          employee={member}
          onClose={() => setShowImpersonationModal(false)}
        />
      )}
    </div>
  );
}

export default TeamMemberProfile;
