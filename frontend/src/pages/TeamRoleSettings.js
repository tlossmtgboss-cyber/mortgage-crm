import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../utils/toast';
import './TeamRoleSettings.css';

/**
 * TeamRoleSettings Page
 *
 * Allows administrators to set default team role assignments.
 * These assignments apply organization-wide - all loans/leads will
 * automatically use these default team members for each role.
 */
function TeamRoleSettings() {
  const [assignments, setAssignments] = useState([]);
  const [teamMembers, setTeamMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({});

  const getAuthHeaders = useCallback(() => ({
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
    'Content-Type': 'application/json',
  }), []);

  // Load default role assignments
  const loadAssignments = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/settings/team-roles', {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        setAssignments(data.assignments || []);
      } else {
        console.error('Failed to load assignments');
        toast.error('Failed to load team role settings');
      }
    } catch (error) {
      console.error('Error loading assignments:', error);
      toast.error('Error loading team role settings');
    }
  }, [getAuthHeaders]);

  // Load team members
  const loadTeamMembers = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/team/members', {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        setTeamMembers(data.team_members || data || []);
      }
    } catch (error) {
      console.error('Error loading team members:', error);
    }
  }, [getAuthHeaders]);

  // Load all data
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([loadAssignments(), loadTeamMembers()]);
      setLoading(false);
    };
    loadData();
  }, [loadAssignments, loadTeamMembers]);

  // Handle assignment change
  const handleAssignmentChange = async (roleId, userId) => {
    setSaving(prev => ({ ...prev, [roleId]: true }));

    try {
      if (userId) {
        // Set default assignment
        const response = await fetch(`/api/v1/settings/team-roles/${roleId}`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ user_id: parseInt(userId) }),
        });

        if (response.ok) {
          const data = await response.json();
          toast.success(data.message || 'Default role assignment saved');

          // Update local state
          setAssignments(prev => prev.map(a =>
            a.role_id === roleId
              ? {
                  ...a,
                  user_id: parseInt(userId),
                  user_name: teamMembers.find(m => m.id === parseInt(userId))?.name ||
                             `${teamMembers.find(m => m.id === parseInt(userId))?.first_name || ''} ${teamMembers.find(m => m.id === parseInt(userId))?.last_name || ''}`.trim()
                }
              : a
          ));
        } else {
          const error = await response.json();
          toast.error(error.detail || 'Failed to save assignment');
        }
      } else {
        // Remove assignment
        const response = await fetch(`/api/v1/settings/team-roles/${roleId}`, {
          method: 'DELETE',
          headers: getAuthHeaders(),
        });

        if (response.ok) {
          toast.success('Default assignment removed');
          setAssignments(prev => prev.map(a =>
            a.role_id === roleId
              ? { ...a, user_id: null, user_name: null, user_email: null }
              : a
          ));
        } else {
          const error = await response.json();
          toast.error(error.detail || 'Failed to remove assignment');
        }
      }
    } catch (error) {
      console.error('Error updating assignment:', error);
      toast.error('Failed to update assignment');
    } finally {
      setSaving(prev => ({ ...prev, [roleId]: false }));
    }
  };

  // Get role icon
  const getRoleIcon = (roleName) => {
    const icons = {
      'Loan Officer': '👔',
      'Production Assistant 1': '📋',
      'Production Assistant 2': '📝',
      'Processor': '⚙️',
      'Underwriter': '🔍',
      'Closer': '✅',
      'Funder': '💰',
      'Post-Closer': '📦',
      'Concierge': '🎯',
      'Team Lead': '👑',
      'Branch Manager': '🏢',
    };
    return icons[roleName] || '👤';
  };

  if (loading) {
    return (
      <div className="team-role-settings">
        <div className="settings-loading">
          <div className="loading-spinner"></div>
          <span>Loading team role settings...</span>
        </div>
      </div>
    );
  }

  const assignedCount = assignments.filter(a => a.user_id).length;

  return (
    <div className="team-role-settings">
      <div className="settings-header">
        <div className="header-content">
          <h1>Team Role Settings</h1>
          <p className="header-description">
            Assign default team members to each workflow role. These assignments will apply
            automatically to all loans and leads in your organization.
          </p>
        </div>
        <div className="header-stats">
          <div className="stat-box">
            <span className="stat-value">{assignedCount}</span>
            <span className="stat-label">Roles Assigned</span>
          </div>
          <div className="stat-box">
            <span className="stat-value">{assignments.length - assignedCount}</span>
            <span className="stat-label">Unassigned</span>
          </div>
        </div>
      </div>

      <div className="settings-content">
        <div className="role-assignments-grid">
          {assignments.map(assignment => (
            <div
              key={assignment.role_id}
              className={`role-card ${assignment.user_id ? 'assigned' : 'unassigned'}`}
            >
              <div className="role-card-header">
                <span className="role-icon">{getRoleIcon(assignment.role_name)}</span>
                <div className="role-info">
                  <h3 className="role-name">{assignment.role_name}</h3>
                  <p className="role-description">{assignment.role_description}</p>
                </div>
              </div>

              <div className="role-card-body">
                <label className="select-label">Assigned Team Member</label>
                <div className="select-wrapper">
                  <select
                    className="role-select"
                    value={assignment.user_id || ''}
                    onChange={(e) => handleAssignmentChange(assignment.role_id, e.target.value)}
                    disabled={saving[assignment.role_id]}
                  >
                    <option value="">-- Select Team Member --</option>
                    {teamMembers.map(member => (
                      <option key={member.id} value={member.id}>
                        {member.name || `${member.first_name || ''} ${member.last_name || ''}`.trim()}
                        {member.role ? ` (${member.role})` : ''}
                      </option>
                    ))}
                  </select>
                  {saving[assignment.role_id] && (
                    <div className="select-saving">
                      <div className="saving-spinner"></div>
                    </div>
                  )}
                </div>

                {assignment.user_id && (
                  <div className="current-assignment">
                    <span className="assignment-badge">
                      <span className="badge-icon">✓</span>
                      Currently: {assignment.user_name}
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {assignments.length === 0 && (
          <div className="no-roles-message">
            <span className="empty-icon">📋</span>
            <h3>No Workflow Roles Configured</h3>
            <p>Contact your administrator to set up workflow roles.</p>
          </div>
        )}
      </div>

      <div className="settings-footer">
        <div className="footer-info">
          <span className="info-icon">ℹ️</span>
          <p>
            Changes are saved automatically. Team members assigned here will be the default
            for all new loans and leads. You can still override assignments on individual
            loan/lead pages if needed.
          </p>
        </div>
      </div>
    </div>
  );
}

export default TeamRoleSettings;
