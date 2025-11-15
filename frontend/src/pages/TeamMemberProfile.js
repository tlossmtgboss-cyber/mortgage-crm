import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teamAPI } from '../services/api';
import './TeamMemberProfile.css';

function TeamMemberProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [member, setMember] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [editing, setEditing] = useState(false);
  const [formData, setFormData] = useState({});

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
      {/* Header */}
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

      {/* Member Info Card */}
      <div className="member-info-card">
        <div className="member-avatar">
          <div className="avatar-circle">
            {member.first_name?.[0]}{member.last_name?.[0]}
          </div>
        </div>
        <div className="member-details">
          <h1>{member.first_name} {member.last_name}</h1>
          <p className="member-role">{member.role}</p>
          {member.title && <p className="member-title">{member.title}</p>}
          <div className="member-contact">
            {member.email && <span>✉️ {member.email}</span>}
            {member.phone && <span>📞 {member.phone}</span>}
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="profile-tabs">
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
      </div>
    </div>
  );
}

export default TeamMemberProfile;
