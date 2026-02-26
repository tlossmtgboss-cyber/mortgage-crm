import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../utils/toast';
import { API_BASE_URL } from '../services/api';
import './WorkflowRoleAssignment.css';

/**
 * WorkflowRoleAssignment Component
 *
 * Organization-wide workflow team assignments. These roles apply to ALL loans
 * and leads in the organization — not per-file. Changes here update the entire
 * workflow routing for the org.
 */
function WorkflowRoleAssignment({
  onUpdate = null,
  compact = false,
  showTitle = true
}) {
  const [roleAssignments, setRoleAssignments] = useState([]);
  const [teamMembers, setTeamMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({});

  const getAuthHeaders = useCallback(() => ({
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
    'Content-Type': 'application/json',
  }), []);

  // Load org-wide role assignments (roles + current assignments in one call)
  const loadRoleAssignments = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles`, {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        setRoleAssignments(data.assignments || []);
      } else {
        console.error('Failed to load role assignments');
      }
    } catch (error) {
      console.error('Error loading role assignments:', error);
    }
  }, [getAuthHeaders]);

  // Load team members for dropdown options
  const loadTeamMembers = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/team/members`, {
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
      await Promise.all([loadRoleAssignments(), loadTeamMembers()]);
      setLoading(false);
    };
    loadData();
  }, [loadRoleAssignments, loadTeamMembers]);

  // Get assigned user for a role
  const getAssignedUser = (roleId) => {
    const assignment = roleAssignments.find(a => a.role_id === roleId);
    return assignment ? assignment.user_id : null;
  };

  // Get assigned user name for a role
  const getAssignedUserName = (roleId) => {
    const assignment = roleAssignments.find(a => a.role_id === roleId);
    return assignment ? assignment.user_name : null;
  };

  // Handle role assignment change (org-wide)
  const handleAssignmentChange = async (roleId, userId) => {
    setSaving(prev => ({ ...prev, [roleId]: true }));

    try {
      if (userId) {
        // Assign user to role org-wide
        const response = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${roleId}`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ user_id: parseInt(userId) }),
        });

        if (response.ok) {
          const data = await response.json();
          toast.success(data.message || 'Role assigned successfully');

          // Update local state
          const selectedUser = teamMembers.find(m => m.id === parseInt(userId));
          const userName = selectedUser?.name || `${selectedUser?.first_name || ''} ${selectedUser?.last_name || ''}`.trim();
          setRoleAssignments(prev =>
            prev.map(a => a.role_id === roleId
              ? { ...a, user_id: parseInt(userId), user_name: userName }
              : a
            )
          );
        } else {
          const error = await response.json();
          toast.error(error.detail || 'Failed to assign role');
        }
      } else {
        // Remove assignment
        const response = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${roleId}`, {
          method: 'DELETE',
          headers: getAuthHeaders(),
        });

        if (response.ok) {
          toast.success('Role assignment removed');
          setRoleAssignments(prev =>
            prev.map(a => a.role_id === roleId
              ? { ...a, user_id: null, user_name: '' }
              : a
            )
          );
        } else {
          const error = await response.json();
          toast.error(error.detail || 'Failed to remove assignment');
        }
      }

      if (onUpdate) {
        onUpdate();
      }
    } catch (error) {
      console.error('Error updating assignment:', error);
      toast.error('Failed to update assignment');
    } finally {
      setSaving(prev => ({ ...prev, [roleId]: false }));
    }
  };

  // Get role icon based on name
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

  // Get role description
  const getRoleDescription = (roleName) => {
    const descriptions = {
      'Loan Officer': 'Primary contact for the borrower',
      'Production Assistant 1': 'Handles initial paperwork and document collection',
      'Production Assistant 2': 'Assists with processing and follow-ups',
      'Processor': 'Prepares loan file for underwriting',
      'Underwriter': 'Reviews and approves the loan',
      'Closer': 'Prepares closing documents',
      'Funder': 'Handles funding and disbursement',
      'Post-Closer': 'Manages post-closing tasks',
      'Concierge': 'Client experience and coordination',
      'Team Lead': 'Oversees team operations',
      'Branch Manager': 'Branch-level oversight',
    };
    return descriptions[roleName] || 'Team member assigned to this role';
  };

  if (loading) {
    return (
      <div className={`workflow-role-assignment ${compact ? 'compact' : ''}`}>
        <div className="role-assignment-loading">
          <div className="loading-spinner"></div>
          <span>Loading role assignments...</span>
        </div>
      </div>
    );
  }

  // Filter to show only workflow-relevant roles
  const workflowRoleNames = [
    'Loan Officer', 'Production Assistant 1', 'Production Assistant 2',
    'Processor', 'Underwriter', 'Closer', 'Funder', 'Post-Closer',
    'Concierge', 'Team Lead', 'Branch Manager'
  ];
  const displayRoles = roleAssignments.filter(a => workflowRoleNames.includes(a.role_name));
  const finalRoles = displayRoles.length > 0 ? displayRoles : roleAssignments;

  return (
    <div className={`workflow-role-assignment ${compact ? 'compact' : ''}`}>
      {showTitle && (
        <div className="role-assignment-header">
          <h4>
            <span className="header-icon">👥</span>
            Workflow Team Assignments
          </h4>
          <p className="header-subtitle">
            Organization-wide team assignments — applies to all loans and leads
          </p>
        </div>
      )}

      <div className="role-assignment-grid">
        {finalRoles.map(role => (
          <div
            key={role.role_id}
            className={`role-assignment-card ${getAssignedUser(role.role_id) ? 'assigned' : 'unassigned'}`}
          >
            <div className="role-header">
              <span className="role-icon">{getRoleIcon(role.role_name)}</span>
              <div className="role-info">
                <span className="role-name">{role.role_name}</span>
                {!compact && (
                  <span className="role-description">{getRoleDescription(role.role_name)}</span>
                )}
              </div>
            </div>

            <div className="role-assignment-control">
              <select
                className="role-user-select"
                value={getAssignedUser(role.role_id) || ''}
                onChange={(e) => handleAssignmentChange(role.role_id, e.target.value)}
                disabled={saving[role.role_id]}
              >
                <option value="">-- Not Assigned --</option>
                {teamMembers.map(member => (
                  <option key={member.id} value={member.id}>
                    {member.name || `${member.first_name || ''} ${member.last_name || ''}`.trim()}
                  </option>
                ))}
              </select>

              {saving[role.role_id] && (
                <div className="saving-indicator">
                  <div className="saving-spinner"></div>
                </div>
              )}

              {getAssignedUser(role.role_id) && !saving[role.role_id] && (
                <span className="assigned-badge">
                  ✓ Assigned
                </span>
              )}
            </div>

            {getAssignedUser(role.role_id) && !compact && (
              <div className="assigned-user-preview">
                <span className="preview-label">Currently:</span>
                <span className="preview-name">{getAssignedUserName(role.role_id)}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {finalRoles.length === 0 && (
        <div className="role-assignment-empty">
          <span className="empty-icon">📋</span>
          <p>No workflow roles configured.</p>
          <p className="empty-hint">Configure roles in Settings to enable team assignments.</p>
        </div>
      )}
    </div>
  );
}

export default WorkflowRoleAssignment;
