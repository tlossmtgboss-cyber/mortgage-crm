import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teamAPI, API_BASE_URL } from '../services/api';
import ImpersonationModal from '../components/ImpersonationModal';
import PermissionsTab from '../components/PermissionsTab';
import AccessAuditTab from '../components/AccessAuditTab';
import RolesResponsibilitiesTab from '../components/RolesResponsibilitiesTab';
import WorkflowMilestonesTab from '../components/WorkflowMilestonesTab';
import { formatPhoneNumber } from '../utils/phoneUtils';
import './TeamMemberProfile.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

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
      toast.error('Failed to load team member details');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      await teamAPI.updateMember(id, formData);
      setMember(formData);
      setEditing(false);
      toast.success('Team member updated successfully!');
    } catch (error) {
      console.error('Failed to update team member:', error);
      toast.error('Failed to update team member');
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
      toast.error('Please select an image file');
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      toast.error('File size must be less than 5MB');
      return;
    }

    try {
      setUploadingPhoto(true);
      const photoFormData = new FormData();
      photoFormData.append('photo', file);

      // Upload to backend
      const response = await fetch(`${API_BASE_URL}/api/v1/users/${id}/photo`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`
        },
        body: photoFormData
      });

      if (!response.ok) {
        throw new Error('Upload failed');
      }

      const result = await response.json();
      const photoUrl = result.photo_url;

      setFormData(prev => ({ ...prev, photo_url: photoUrl }));
      setMember(prev => ({ ...prev, photo_url: photoUrl }));

      toast.success('Photo uploaded successfully!');
    } catch (error) {
      console.error('Failed to upload photo:', error);
      toast.error('Failed to upload photo. Please try again.');
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleImpersonate = () => {
    setShowImpersonationModal(true);
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
            className={`tab-btn ${activeTab === 'roles' ? 'active' : ''}`}
            onClick={() => setActiveTab('roles')}
          >
            Roles & Responsibilities
          </button>
          <button
            className={`tab-btn ${activeTab === 'workflow' ? 'active' : ''}`}
            onClick={() => setActiveTab('workflow')}
          >
            Workflow & Milestones
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

        {/* Roles & Responsibilities Tab */}
        {activeTab === 'roles' && (
          <div className="tab-panel">
            <RolesResponsibilitiesTab userId={member.id} isManager={true} />
          </div>
        )}

        {/* Workflow & Milestones Tab */}
        {activeTab === 'workflow' && (
          <div className="tab-panel">
            <WorkflowMilestonesTab userId={member.id} />
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
                  onChange={(e) => handleFieldChange('emergency_phone', formatPhoneNumber(e.target.value))}
                  disabled={!editing}
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
        {activeTab === 'access-audit' && member && (
          <div className="tab-panel">
            <AccessAuditTab userId={member.id} />
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
