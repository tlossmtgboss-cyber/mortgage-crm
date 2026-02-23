import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../utils/toast';
import { API_BASE_URL } from '../services/api';
import './WorkflowRoleAssignment.css';

/**
 * WorkflowRoleAssignment Component
 *
 * Allows users to assign team members to workflow roles for a specific loan or lead.
 * Each role (Loan Officer, Processor, Underwriter, etc.) can have a user assigned
 * who will receive tasks related to that role.
 */
function WorkflowRoleAssignment({
  loanId = null,
  leadId = null,
  onUpdate = null,
  compact = false,
  showTitle = true
}) {
  const [roles, setRoles] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [teamMembers, setTeamMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({});

  const getAuthHeaders = useCallback(() => ({
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
    'Content-Type': 'application/json',
  }), []);

  // Load available roles
  const loadRoles = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/roles`, {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        setRoles(data.roles || []);
      } else {
        console.error('Failed to load roles');
      }
    } catch (error) {
      console.error('Error loading roles:', error);
    }
  }, [getAuthHeaders]);

  // Load current assignments for the entity
  const loadAssignments = useCallback(async () => {
    if (!loanId && !leadId) return;

    try {
      const entityType = loanId ? 'loans' : 'leads';
      const entityId = loanId || leadId;

      const response = await fetch(`${API_BASE_URL}/api/v1/${entityType}/${entityId}/roles`, {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        setAssignments(data.assignments || []);
      } else {
        // No assignments yet - that's fine
        setAssignments([]);
      }
    } catch (error) {
      console.error('Error loading assignments:', error);
      setAssignments([]);
    }
  }, [loanId, leadId, getAuthHeaders]);

  // Load team members
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
      await Promise.all([loadRoles(), loadAssignments(), loadTeamMembers()]);
      setLoading(false);
    };
    loadData();
  }, [loadRoles, loadAssignments, loadTeamMembers]);

  // Get assigned user for a role
  const getAssignedUser = (roleId) => {
    const assignment = assignments.find(a => a.role_id === roleId);
    return assignment ? assignment.user_id : null;
  };

  // Get assigned user name for a role
  const getAssignedUserName = (roleId) => {
    const assignment = assignments.find(a => a.role_id === roleId);
    return assignment ? assignment.user_name : null;
  };

  // Handle role assignment change
  const handleAssignmentChange = async (roleId, userId) => {
    if (!loanId && !leadId) return;

    const entityType = loanId ? 'loans' : 'leads';
    const entityId = loanId || leadId;

    setSaving(prev => ({ ...prev, [roleId]: true }));

    try {
      if (userId) {
        // Assign user to role
        const response = await fetch(`${API_BASE_URL}/api/v1/${entityType}/${entityId}/roles/${roleId}/assign`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ user_id: parseInt(userId) }),
        });

        if (response.ok) {
          const data = await response.json();
          toast.success(data.message || 'Role assigned successfully');

          // Update local state
          setAssignments(prev => {
            const existing = prev.find(a => a.role_id === roleId);
            const selectedUser = teamMembers.find(m => m.id === parseInt(userId));
            const newAssignment = {
              role_id: roleId,
              user_id: parseInt(userId),
              user_name: selectedUser?.name || `${selectedUser?.first_name || ''} ${selectedUser?.last_name || ''}`.trim()
            };

            if (existing) {
              return prev.map(a => a.role_id === roleId ? newAssignment : a);
            }
            return [...prev, newAssignment];
          });
        } else {
          const error = await response.json();
          toast.error(error.detail || 'Failed to assign role');
        }
      } else {
        // Remove assignment
        const response = await fetch(`${API_BASE_URL}/api/v1/${entityType}/${entityId}/roles/${roleId}`, {
          method: 'DELETE',
          headers: getAuthHeaders(),
        });

        if (response.ok) {
          toast.success('Role assignment removed');
          setAssignments(prev => prev.filter(a => a.role_id !== roleId));
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

  if (!loanId && !leadId) {
    return (
      <div className={`workflow-role-assignment ${compact ? 'compact' : ''}`}>
        <div className="role-assignment-empty">
          Select a loan or lead to manage role assignments
        </div>
      </div>
    );
  }

  // Filter to show only workflow-relevant roles
  const workflowRoles = roles.filter(role =>
    ['Loan Officer', 'Production Assistant 1', 'Production Assistant 2',
     'Processor', 'Underwriter', 'Closer', 'Funder', 'Post-Closer',
     'Concierge', 'Team Lead', 'Branch Manager'].includes(role.name)
  );

  // If no specific workflow roles found, show all roles
  const displayRoles = workflowRoles.length > 0 ? workflowRoles : roles;

  return (
    <div className={`workflow-role-assignment ${compact ? 'compact' : ''}`}>
      {showTitle && (
        <div className="role-assignment-header">
          <h4>
            <span className="header-icon">👥</span>
            Workflow Team Assignments
          </h4>
          <p className="header-subtitle">
            Assign team members to handle tasks for each role
          </p>
        </div>
      )}

      <div className="role-assignment-grid">
        {displayRoles.map(role => (
          <div
            key={role.id}
            className={`role-assignment-card ${getAssignedUser(role.id) ? 'assigned' : 'unassigned'}`}
          >
            <div className="role-header">
              <span className="role-icon">{getRoleIcon(role.name)}</span>
              <div className="role-info">
                <span className="role-name">{role.name}</span>
                {!compact && (
                  <span className="role-description">{getRoleDescription(role.name)}</span>
                )}
              </div>
            </div>

            <div className="role-assignment-control">
              <select
                className="role-user-select"
                value={getAssignedUser(role.id) || ''}
                onChange={(e) => handleAssignmentChange(role.id, e.target.value)}
                disabled={saving[role.id]}
              >
                <option value="">-- Not Assigned --</option>
                {teamMembers.map(member => (
                  <option key={member.id} value={member.id}>
                    {member.name || `${member.first_name || ''} ${member.last_name || ''}`.trim()}
                  </option>
                ))}
              </select>

              {saving[role.id] && (
                <div className="saving-indicator">
                  <div className="saving-spinner"></div>
                </div>
              )}

              {getAssignedUser(role.id) && !saving[role.id] && (
                <span className="assigned-badge">
                  ✓ Assigned
                </span>
              )}
            </div>

            {getAssignedUser(role.id) && !compact && (
              <div className="assigned-user-preview">
                <span className="preview-label">Currently:</span>
                <span className="preview-name">{getAssignedUserName(role.id)}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {displayRoles.length === 0 && (
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
