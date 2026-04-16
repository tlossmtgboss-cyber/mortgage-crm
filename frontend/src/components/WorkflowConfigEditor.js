import React, { useState, useEffect, useCallback } from 'react';
import './WorkflowConfigEditor.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Communication method columns - default for most workflows (uses "Realtor")
const DEFAULT_COMMUNICATION_METHODS = [
  { key: 'phone', label: 'Phone', color: '#3b82f6' },
  { key: 'text', label: 'Text', color: '#10b981' },
  { key: 'email', label: 'Email', color: '#f59e0b' },
  { key: 'referral_partner', label: 'Realtor', color: '#ec4899' }
];

// Theme Day workflow uses "Stakeholder" instead of "Realtor"
const THEME_DAY_COMMUNICATION_METHODS = [
  { key: 'phone', label: 'Phone', color: '#3b82f6' },
  { key: 'text', label: 'Text', color: '#10b981' },
  { key: 'email', label: 'Email', color: '#f59e0b' },
  { key: 'referral_partner', label: 'Stakeholder', color: '#ec4899' }
];

// Lead Purchase workflow has AM/PM phone and text columns
const LEAD_PURCHASE_COMMUNICATION_METHODS = [
  { key: 'phone_am', label: 'AM Phone', color: '#3b82f6' },
  { key: 'phone_pm', label: 'PM Phone', color: '#2563eb' },
  { key: 'text_am', label: 'AM Text', color: '#10b981' },
  { key: 'text_pm', label: 'PM Text', color: '#059669' },
  { key: 'email', label: 'Email', color: '#f59e0b' }
];

// Get communication methods based on workflow key
const getCommunicationMethods = (workflowKey) => {
  if (workflowKey === 'lead_purchase') {
    return LEAD_PURCHASE_COMMUNICATION_METHODS;
  }
  if (workflowKey === 'theme_day') {
    return THEME_DAY_COMMUNICATION_METHODS;
  }
  return DEFAULT_COMMUNICATION_METHODS;
};

// Legacy field mapping for backwards compatibility
const LEGACY_RESPONSIBILITY_FIELDS = {
  lo: 'lo_responsible',
  jr_lo: 'jr_lo_responsible',
  production_asst: 'production_asst_responsible',
  concierge: 'concierge_responsible',
  ai: 'ai_responsible'
};

// Legacy role mapping for backwards compatibility
const LEGACY_ROLE_MAP = {
  lo: 'loan_officer',
  jr_lo: 'junior_loan_officer',
  production_asst: 'production_assistant',
  concierge: 'concierge'
};

// Fallback roles if dynamic fetch fails
const DEFAULT_RESPONSIBILITY_ROLES = [
  { id: null, key: 'lo', label: 'LO', fullName: 'Loan Officer', roleValue: 'loan_officer', canDelete: false, isLegacy: true },
  { id: null, key: 'jr_lo', label: 'Jr. LO', fullName: 'Junior Loan Officer', roleValue: 'junior_loan_officer', canDelete: true, isLegacy: true },
  { id: null, key: 'production_asst', label: 'Production Asst.', fullName: 'Production Assistant', roleValue: 'production_assistant', canDelete: true, isLegacy: true },
  { id: null, key: 'concierge', label: 'Concierge', fullName: 'Concierge', roleValue: 'concierge', canDelete: true, isLegacy: true },
  { id: null, key: 'ai', label: 'AI', fullName: 'AI Automation', roleValue: 'ai', canDelete: false, isLegacy: true }
];

function WorkflowConfigEditor({ workflowKey, workflowName, workflowColor, onClose, embedded = false }) {
  // Get workflow-specific communication methods
  const COMMUNICATION_METHODS = getCommunicationMethods(workflowKey);

  const [workflowConfig, setWorkflowConfig] = useState(null);
  const [days, setDays] = useState([]);
  const [roleAssignments, setRoleAssignments] = useState([]);
  const [users, setUsers] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [showAddDay, setShowAddDay] = useState(false);
  const [newDay, setNewDay] = useState({ label: '', value: '' });
  const [showRoleDropdown, setShowRoleDropdown] = useState(null);
  const [editingRole, setEditingRole] = useState(null);
  const [responsibilityRoles, setResponsibilityRoles] = useState(DEFAULT_RESPONSIBILITY_ROLES);
  const [dynamicRoles, setDynamicRoles] = useState([]); // Roles from admin Role table
  const [showAddRole, setShowAddRole] = useState(false);
  const [newRole, setNewRole] = useState({ label: '', fullName: '' });
  const [deleteRoleModal, setDeleteRoleModal] = useState(null);
  const [reassignToRole, setReassignToRole] = useState('');
  const [lastSaved, setLastSaved] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [editingDay, setEditingDay] = useState(null);
  const [editDayForm, setEditDayForm] = useState({ label: '', value: '', repeat_weekly: false });

  const fetchWorkflowConfig = useCallback(async () => {
    try {
      setLoading(true);
      const token = getToken();
      const headers = { 'Authorization': `Bearer ${token}` };

      // Fetch roles AND assignments from shared team-roles API (single source of truth)
      try {
        const rolesResponse = await fetch(`${API_BASE}/api/v1/settings/team-roles`, { headers });
        if (rolesResponse.ok) {
          const rolesData = await rolesResponse.json();
          const fetchedAssignments = rolesData.assignments || [];
          setDynamicRoles(fetchedAssignments);

          // Convert to responsibility roles format
          const dynamicRoleEntries = fetchedAssignments.map(role => ({
            id: role.role_id,
            key: `dynamic_${role.role_id}`,
            label: getAbbreviation(role.role_name),
            fullName: role.role_name,
            roleValue: role.role_name.toLowerCase().replace(/\s+/g, '_'),
            canDelete: false,
            isLegacy: false,
            isDynamic: true
          }));

          // Keep AI role at the end
          const aiRole = DEFAULT_RESPONSIBILITY_ROLES.find(r => r.key === 'ai');
          setResponsibilityRoles([...dynamicRoleEntries, aiRole]);

          // Build role assignments from the shared data
          const sharedAssignments = fetchedAssignments
            .filter(a => a.user_id)
            .map(a => ({
              id: a.role_id,
              role_id: a.role_id,
              user_id: a.user_id,
              role: a.role_name.toLowerCase().replace(/\s+/g, '_'),
            }));
          setRoleAssignments(sharedAssignments);
        }
      } catch (roleErr) {
        console.warn('Could not fetch roles from team-roles API, using defaults:', roleErr);
      }

      // Fetch workflow configuration
      const response = await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}`, { headers });

      if (!response.ok) {
        // If workflow doesn't exist, try to seed defaults first
        if (response.status === 404) {
          await fetch(`${API_BASE}/api/v1/workflow-config/seed`, {
            method: 'POST',
            headers
          });
          // Try again
          const retryResponse = await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}`, { headers });
          if (retryResponse.ok) {
            const data = await retryResponse.json();
            setWorkflowConfig(data);
            setDays(data.days || []);
            setRoleAssignments(data.role_assignments || []);
          } else {
            throw new Error('Workflow not found');
          }
        } else {
          throw new Error('Failed to fetch workflow configuration');
        }
      } else {
        const data = await response.json();
        setWorkflowConfig(data);
        setDays(data.days || []);
        setRoleAssignments(data.role_assignments || []);
      }

      // Fetch users for role assignment
      const usersResponse = await fetch(`${API_BASE}/api/v1/users`, { headers });
      if (usersResponse.ok) {
        const usersData = await usersResponse.json();
        setUsers(usersData.users || usersData || []);
      }

      // Fetch alerts for this workflow
      const alertsResponse = await fetch(`${API_BASE}/api/v1/workflow-config/alerts?workflow_key=${workflowKey}&unresolved_only=true`, { headers });
      if (alertsResponse.ok) {
        const alertsData = await alertsResponse.json();
        setAlerts(alertsData || []);
      }

      setError(null);
    } catch (err) {
      console.error('Error fetching workflow config:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workflowKey]);

  // Helper function to generate abbreviation from role name
  const getAbbreviation = (name) => {
    if (!name) return '';
    const words = name.split(/\s+/);
    if (words.length === 1) {
      return name.substring(0, 3).toUpperCase();
    }
    // Take first letter of each word
    return words.map(w => w[0]).join('').toUpperCase();
  };

  useEffect(() => {
    fetchWorkflowConfig();
  }, [fetchWorkflowConfig]);

  // Toggle communication method for a day
  const toggleCommunication = async (dayId, method) => {
    const day = days.find(d => d.id === dayId);
    if (!day) return;

    const fieldMap = {
      phone: 'phone_enabled',
      phone_am: 'phone_am_enabled',
      phone_pm: 'phone_pm_enabled',
      text: 'text_enabled',
      text_am: 'text_am_enabled',
      text_pm: 'text_pm_enabled',
      email: 'email_enabled',
      referral_partner: 'referral_partner_enabled'
    };

    const field = fieldMap[method];
    const newValue = !day[field];

    try {
      setSaving(true);
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days/${dayId}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ [field]: newValue })
      });

      if (response.ok) {
        setDays(prev => prev.map(d =>
          d.id === dayId ? { ...d, [field]: newValue } : d
        ));
      }
    } catch (err) {
      console.error('Error updating communication method:', err);
    } finally {
      setSaving(false);
    }
  };

  // Toggle responsibility for a day - supports both legacy and dynamic roles
  const toggleResponsibility = async (dayId, roleKey, roleData = null) => {
    const day = days.find(d => d.id === dayId);
    if (!day) return;

    // Check if this is a dynamic role (from admin Role table)
    const isDynamic = roleData?.isDynamic || roleKey.startsWith('dynamic_');

    try {
      setSaving(true);
      const token = getToken();

      if (isDynamic && roleData?.id) {
        // For dynamic roles, use the role_responsibilities JSON field
        const roleResponsibilities = day.role_responsibilities || {};
        const roleIdStr = String(roleData.id);
        const newValue = !roleResponsibilities[roleIdStr];

        // Use the dedicated endpoint for role responsibilities
        const response = await fetch(
          `${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days/${dayId}/role-responsibility`,
          {
            method: 'PUT',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ role_id: roleData.id, responsible: newValue })
          }
        );

        if (response.ok) {
          const updatedRoleResp = { ...roleResponsibilities, [roleIdStr]: newValue };
          setDays(prev => prev.map(d =>
            d.id === dayId ? { ...d, role_responsibilities: updatedRoleResp } : d
          ));
        }
      } else {
        // Legacy roles use individual boolean columns
        const fieldMap = {
          lo: 'lo_responsible',
          jr_lo: 'jr_lo_responsible',
          production_asst: 'production_asst_responsible',
          concierge: 'concierge_responsible',
          ai: 'ai_responsible'
        };

        const field = fieldMap[roleKey];
        if (!field) {
          console.warn('Unknown legacy role:', roleKey);
          return;
        }
        const newValue = !day[field];

        const response = await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days/${dayId}`, {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ [field]: newValue })
        });

        if (response.ok) {
          setDays(prev => prev.map(d =>
            d.id === dayId ? { ...d, [field]: newValue } : d
          ));
        }
      }
    } catch (err) {
      console.error('Error updating responsibility:', err);
    } finally {
      setSaving(false);
    }
  };

  // Save all workflow changes (explicit save button)
  const handleSaveAll = async () => {
    try {
      setSaving(true);
      setSaveSuccess(false);
      const token = getToken();
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // Save each day's configuration
      const savePromises = days.map(day =>
        fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days/${day.id}`, {
          method: 'PUT',
          headers,
          body: JSON.stringify({
            phone_enabled: day.phone_enabled,
            text_enabled: day.text_enabled,
            email_enabled: day.email_enabled,
            referral_partner_enabled: day.referral_partner_enabled,
            lo_responsible: day.lo_responsible,
            jr_lo_responsible: day.jr_lo_responsible,
            production_asst_responsible: day.production_asst_responsible,
            concierge_responsible: day.concierge_responsible,
            ai_responsible: day.ai_responsible,
            role_responsibilities: day.role_responsibilities || {}
          })
        })
      );

      await Promise.all(savePromises);

      setLastSaved(new Date());
      setSaveSuccess(true);

      // Hide success message after 3 seconds
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      console.error('Error saving workflow:', err);
      toast.error('Failed to save workflow. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Add a new day
  const handleAddDay = async () => {
    if (!newDay.label || !newDay.value) return;

    try {
      setSaving(true);
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          day_label: newDay.label,
          day_value: parseInt(newDay.value),
          day_order: days.length + 1
        })
      });

      if (response.ok) {
        const result = await response.json();
        // Backend returns {success: true, day: {...}} - extract the day object
        const addedDay = result.day || result;
        setDays(prev => [...prev, addedDay].sort((a, b) => a.day_order - b.day_order));
        setNewDay({ label: '', value: '' });
        setShowAddDay(false);
      }
    } catch (err) {
      console.error('Error adding day:', err);
    } finally {
      setSaving(false);
    }
  };

  // Delete a day
  const handleDeleteDay = async (dayId) => {
    try {
      setSaving(true);
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days/${dayId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        setDays(prev => prev.filter(d => d.id !== dayId));
      }
    } catch (err) {
      console.error('Error deleting day:', err);
    } finally {
      setSaving(false);
    }
  };

  // Open edit modal for a day
  const handleEditDay = (day) => {
    setEditingDay(day);
    setEditDayForm({
      label: day.day_label,
      value: day.day_value?.toString() || '',
      repeat_weekly: day.repeat_weekly === true // Default to false (unchecked) if not set
    });
  };

  // Save edited day
  const handleSaveEditDay = async () => {
    if (!editingDay || !editDayForm.label) return;

    try {
      setSaving(true);
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days/${editingDay.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          day_label: editDayForm.label,
          day_value: editDayForm.value ? parseInt(editDayForm.value) : null,
          repeat_weekly: editDayForm.repeat_weekly
        })
      });

      if (response.ok) {
        setDays(prev => prev.map(d =>
          d.id === editingDay.id
            ? { ...d, day_label: editDayForm.label, day_value: editDayForm.value ? parseInt(editDayForm.value) : null, repeat_weekly: editDayForm.repeat_weekly }
            : d
        ));
        setEditingDay(null);
        setEditDayForm({ label: '', value: '', repeat_weekly: false });
      }
    } catch (err) {
      console.error('Error updating day:', err);
    } finally {
      setSaving(false);
    }
  };

  // Assign user to role via shared team-roles API
  const handleAssignUser = async (roleKey, userId, roleData = null) => {
    try {
      setSaving(true);
      const token = getToken();
      const authHeaders = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      const roleId = roleData?.id;
      if (!roleId) {
        console.warn('No role ID for assignment:', roleKey);
        return;
      }

      let response;
      if (userId) {
        // Assign: POST /api/v1/settings/team-roles/{roleId}
        response = await fetch(`${API_BASE}/api/v1/settings/team-roles/${roleId}`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ user_id: parseInt(userId) })
        });
      } else {
        // Unassign: DELETE /api/v1/settings/team-roles/{roleId}
        response = await fetch(`${API_BASE}/api/v1/settings/team-roles/${roleId}`, {
          method: 'DELETE',
          headers: authHeaders
        });
      }

      if (response.ok) {
        // Update local state
        setRoleAssignments(prev => {
          const filtered = prev.filter(ra => ra.role_id !== roleId);
          if (userId) {
            filtered.push({ id: roleId, role_id: roleId, user_id: parseInt(userId) });
          }
          return filtered;
        });
      }

      setEditingRole(null);
      setShowRoleDropdown(null);
    } catch (err) {
      console.error('Error assigning user:', err);
    } finally {
      setSaving(false);
    }
  };

  // Get user name by ID
  const getUserName = (userId) => {
    const user = users.find(u => u.id === userId);
    return user ? user.name || user.email : 'Unassigned';
  };

  // Get assigned user for a role by role_id
  const getAssignedUser = (roleKey, roleData = null) => {
    if (roleData?.id) {
      const assignment = roleAssignments.find(ra => ra.role_id === roleData.id);
      return assignment?.user_id;
    }
    return null;
  };

  // Check day health
  const runHealthCheck = async (dayId) => {
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days/${dayId}/check-health`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const result = await response.json();
        setDays(prev => prev.map(d =>
          d.id === dayId ? { ...d, health_status: result.health_status, health_message: result.health_message } : d
        ));

        // Refresh alerts
        fetchWorkflowConfig();
      }
    } catch (err) {
      console.error('Error running health check:', err);
    }
  };

  // Add a new role
  const handleAddRole = () => {
    if (!newRole.label || !newRole.fullName) return;

    const roleKey = newRole.fullName.toLowerCase().replace(/\s+/g, '_');
    const roleValue = roleKey;

    // Check if role already exists
    if (responsibilityRoles.some(r => r.key === roleKey)) {
      toast.error('A role with this name already exists');
      return;
    }

    const newRoleEntry = {
      key: roleKey,
      label: newRole.label,
      fullName: newRole.fullName,
      roleValue: roleValue,
      canDelete: true
    };

    setResponsibilityRoles(prev => [...prev.filter(r => r.key !== 'ai'), newRoleEntry, prev.find(r => r.key === 'ai')]);
    setNewRole({ label: '', fullName: '' });
    setShowAddRole(false);
  };

  // Check if role has tasks assigned
  const roleHasTasks = (roleKey) => {
    const fieldMap = {
      lo: 'lo_responsible',
      jr_lo: 'jr_lo_responsible',
      production_asst: 'production_asst_responsible',
      concierge: 'concierge_responsible',
      ai: 'ai_responsible'
    };
    const field = fieldMap[roleKey];
    if (!field) return false;
    return days.some(day => day[field]);
  };

  // Handle role deletion with reassignment
  const handleDeleteRole = (roleKey) => {
    const role = responsibilityRoles.find(r => r.key === roleKey);
    if (!role || !role.canDelete) return;

    if (roleHasTasks(roleKey)) {
      setDeleteRoleModal(role);
      setReassignToRole('');
    } else {
      // No tasks, can delete directly
      setResponsibilityRoles(prev => prev.filter(r => r.key !== roleKey));
    }
  };

  // Confirm role deletion with task reassignment
  const confirmDeleteRole = async () => {
    if (!deleteRoleModal || !reassignToRole) return;

    const fromRoleKey = deleteRoleModal.key;
    const toRoleKey = reassignToRole;

    // Reassign tasks from old role to new role
    const fromFieldMap = {
      lo: 'lo_responsible',
      jr_lo: 'jr_lo_responsible',
      production_asst: 'production_asst_responsible',
      concierge: 'concierge_responsible',
      ai: 'ai_responsible'
    };
    const toFieldMap = fromFieldMap;

    const fromField = fromFieldMap[fromRoleKey];
    const toField = toFieldMap[toRoleKey];

    if (!fromField || !toField) {
      toast.error('Invalid role selection');
      return;
    }

    try {
      setSaving(true);
      const token = getToken();

      // Update each day that has the deleted role's tasks
      for (const day of days) {
        if (day[fromField]) {
          await fetch(`${API_BASE}/api/v1/workflow-config/workflows/${workflowKey}/days/${day.id}`, {
            method: 'PUT',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              [fromField]: false,
              [toField]: true
            })
          });
        }
      }

      // Update local state
      setDays(prev => prev.map(day => {
        if (day[fromField]) {
          return { ...day, [fromField]: false, [toField]: true };
        }
        return day;
      }));

      // Remove role from list
      setResponsibilityRoles(prev => prev.filter(r => r.key !== fromRoleKey));
      setDeleteRoleModal(null);
      setReassignToRole('');
    } catch (err) {
      console.error('Error reassigning tasks:', err);
      toast.error('Failed to reassign tasks. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="workflow-config-editor">
        <div className="editor-loading">Loading workflow configuration...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="workflow-config-editor">
        <div className="editor-error">
          <p>Error: {error}</p>
          <button onClick={fetchWorkflowConfig} className="btn-retry">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className={`workflow-config-editor ${embedded ? 'embedded' : ''}`}>
      {/* Header */}
      <div className="editor-header" style={{ borderColor: workflowColor }}>
        <div className="editor-title">
          <h2 style={{ color: workflowColor }}>{workflowName} Workflow Configuration</h2>
          {workflowConfig && (
            <p className="editor-objective">
              <strong>Objective:</strong> {workflowConfig.objective}
            </p>
          )}
        </div>
        <div className="editor-actions">
          {saving && <span className="saving-indicator">Saving...</span>}
          {saveSuccess && <span className="save-success">Saved successfully!</span>}
          {lastSaved && !saving && !saveSuccess && (
            <span className="last-saved">Last saved: {lastSaved.toLocaleTimeString()}</span>
          )}
          <button
            onClick={handleSaveAll}
            className="btn-save"
            disabled={saving || days.length === 0}
          >
            {saving ? 'Saving...' : 'Save Workflow'}
          </button>
          {!embedded && onClose && (
            <button onClick={onClose} className="btn-close">Close</button>
          )}
        </div>
      </div>

      {/* Alerts Banner */}
      {alerts.length > 0 && (
        <div className="alerts-banner">
          <div className="alert-icon">!</div>
          <div className="alert-content">
            <strong>{alerts.length} Broken Task{alerts.length > 1 ? 's' : ''}</strong>
            <span>Some tasks need admin attention</span>
          </div>
        </div>
      )}

      {/* Workflow Stats - shows actual task count */}
      {embedded && (
        <div className="workflow-stats-inline">
          <div className="stat-box">
            <div className="stat-value" style={{ color: workflowColor }}>{days.length}</div>
            <div className="stat-label">Total Tasks</div>
          </div>
        </div>
      )}

      {/* Role Assignments Section */}
      <div className="role-assignments-section">
        <div className="role-section-header">
          <div>
            <h3>Role Assignments</h3>
            <p className="section-description">Click on a role to assign a specific user to handle those tasks</p>
          </div>
          {/* Hide Add Role button since roles are now managed from Admin */}
        </div>
        <div className="role-assignments-grid">
          {responsibilityRoles.filter(r => r.key !== 'ai').map(role => {
            const assignedUserId = getAssignedUser(role.key, role);

            return (
              <div key={role.key} className="role-assignment-card">
                <div className="role-header">
                  <span className="role-name">{role.fullName}</span>
                  <span className="role-abbr">({role.label})</span>
                </div>
                <div className="role-user" onClick={() => setEditingRole(role.key)}>
                  {editingRole === role.key ? (
                    <select
                      autoFocus
                      value={assignedUserId || ''}
                      onChange={(e) => handleAssignUser(role.key, e.target.value ? parseInt(e.target.value) : null, role)}
                      onBlur={() => setEditingRole(null)}
                    >
                      <option value="">-- Unassigned --</option>
                      {users.map(user => (
                        <option key={user.id} value={user.id}>
                          {user.name || user.email}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className={assignedUserId ? 'assigned' : 'unassigned'}>
                      {assignedUserId ? getUserName(assignedUserId) : 'Click to assign'}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Add Role Modal */}
        {showAddRole && (
          <div className="modal-overlay">
            <div className="modal-content">
              <h4>Add New Role</h4>
              <div className="form-group">
                <label>Abbreviation (e.g., "LC")</label>
                <input
                  type="text"
                  value={newRole.label}
                  onChange={(e) => setNewRole(prev => ({ ...prev, label: e.target.value }))}
                  placeholder="Short label"
                  maxLength={10}
                />
              </div>
              <div className="form-group">
                <label>Full Name (e.g., "Loan Coordinator")</label>
                <input
                  type="text"
                  value={newRole.fullName}
                  onChange={(e) => setNewRole(prev => ({ ...prev, fullName: e.target.value }))}
                  placeholder="Full role name"
                />
              </div>
              <div className="modal-actions">
                <button className="btn-cancel" onClick={() => { setShowAddRole(false); setNewRole({ label: '', fullName: '' }); }}>
                  Cancel
                </button>
                <button
                  className="btn-save"
                  onClick={handleAddRole}
                  disabled={!newRole.label || !newRole.fullName}
                >
                  Add Role
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Delete Role Modal with Reassignment */}
        {deleteRoleModal && (
          <div className="modal-overlay">
            <div className="modal-content">
              <h4>Delete Role: {deleteRoleModal.fullName}</h4>
              <p className="warning-text">
                This role has tasks assigned to it. Please select a role to reassign these tasks to:
              </p>
              <div className="form-group">
                <label>Reassign tasks to:</label>
                <select
                  value={reassignToRole}
                  onChange={(e) => setReassignToRole(e.target.value)}
                >
                  <option value="">-- Select a role --</option>
                  {responsibilityRoles
                    .filter(r => r.key !== deleteRoleModal.key && r.key !== 'ai')
                    .map(r => (
                      <option key={r.key} value={r.key}>{r.fullName}</option>
                    ))
                  }
                </select>
              </div>
              <div className="modal-actions">
                <button className="btn-cancel" onClick={() => { setDeleteRoleModal(null); setReassignToRole(''); }}>
                  Cancel
                </button>
                <button
                  className="btn-delete"
                  onClick={confirmDeleteRole}
                  disabled={!reassignToRole || saving}
                >
                  {saving ? 'Reassigning...' : 'Delete & Reassign'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Edit Day Modal */}
        {editingDay && (
          <div className="modal-overlay">
            <div className="modal-content">
              <h4>Edit Task</h4>
              <div className="form-group">
                <label>Task Label</label>
                <input
                  type="text"
                  value={editDayForm.label}
                  onChange={(e) => setEditDayForm(prev => ({ ...prev, label: e.target.value }))}
                  placeholder="e.g., 7 Day Call - Thank You"
                />
              </div>
              <div className="form-group">
                <label>Day Value (number of days from closing)</label>
                <input
                  type="number"
                  value={editDayForm.value}
                  onChange={(e) => setEditDayForm(prev => ({ ...prev, value: e.target.value }))}
                  placeholder="e.g., 7"
                />
              </div>
              <div className="form-group checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={editDayForm.repeat_weekly}
                    onChange={(e) => setEditDayForm(prev => ({ ...prev, repeat_weekly: e.target.checked }))}
                  />
                  <span className="checkbox-text">Repeat weekly until closed</span>
                </label>
                <p className="field-hint">
                  Task repeats weekly until loan is closed, canceled, withdrawn, or denied.
                  <br />
                  <em>Monday updates: First update goes out on the Monday following Disclosed date entry (not same day if added on Monday).</em>
                </p>
              </div>
              <div className="modal-actions">
                <button className="btn-cancel" onClick={() => { setEditingDay(null); setEditDayForm({ label: '', value: '', repeat_weekly: false }); }}>
                  Cancel
                </button>
                <button
                  className="btn-save"
                  onClick={handleSaveEditDay}
                  disabled={!editDayForm.label || saving}
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Workflow Grid */}
      <div className="workflow-grid-container">
        <table className="workflow-config-grid">
          <thead>
            <tr>
              <th className="health-col">Status</th>
              <th className="day-col">Day</th>
              <th colSpan={COMMUNICATION_METHODS.length} className="comm-header">
                Communication Method
              </th>
              <th colSpan={responsibilityRoles.length} className="resp-header">
                Task Responsibility
              </th>
              <th className="actions-col">Actions</th>
            </tr>
            <tr className="sub-header">
              <th></th>
              <th></th>
              {COMMUNICATION_METHODS.map(method => (
                <th key={method.key} style={{ color: method.color }}>
                  {method.label}
                </th>
              ))}
              {responsibilityRoles.map(role => (
                <th key={role.key}>{role.label}</th>
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {days.map(day => (
              <tr key={day.id} className={day.health_status === 'broken' ? 'row-broken' : ''}>
                {/* Health Status Dot */}
                <td className="health-cell">
                  <span
                    className={`health-dot ${day.health_status || 'healthy'}`}
                    title={day.health_message || (day.health_status === 'healthy' ? 'Task is functioning' : day.health_status === 'broken' ? 'Task has issues' : 'Task is disabled')}
                    onClick={() => runHealthCheck(day.id)}
                  ></span>
                </td>

                {/* Day Label */}
                <td className="day-cell">
                  <span className="day-label">{day.day_label}</span>
                  {day.day_value && (
                    <span className="day-value">({day.day_value} days)</span>
                  )}
                </td>

                {/* Communication Method Checkboxes */}
                {COMMUNICATION_METHODS.map(method => {
                  const fieldMap = {
                    phone: 'phone_enabled',
                    phone_am: 'phone_am_enabled',
                    phone_pm: 'phone_pm_enabled',
                    text: 'text_enabled',
                    text_am: 'text_am_enabled',
                    text_pm: 'text_pm_enabled',
                    email: 'email_enabled',
                    referral_partner: 'referral_partner_enabled'
                  };
                  const isEnabled = day[fieldMap[method.key]];

                  return (
                    <td key={method.key} className="checkbox-cell">
                      <label className="checkbox-wrapper">
                        <input
                          type="checkbox"
                          checked={isEnabled || false}
                          onChange={() => toggleCommunication(day.id, method.key)}
                          disabled={saving}
                        />
                        <span
                          className="custom-checkbox"
                          style={{ borderColor: isEnabled ? method.color : '#ccc', backgroundColor: isEnabled ? method.color : 'transparent' }}
                        ></span>
                      </label>
                    </td>
                  );
                })}

                {/* Responsibility Checkboxes - supports both legacy and dynamic roles */}
                {responsibilityRoles.map(role => {
                  let isResponsible;

                  if (role.isDynamic && role.id) {
                    // Dynamic roles use role_responsibilities JSON
                    const roleResp = day.role_responsibilities || {};
                    isResponsible = roleResp[String(role.id)] === true;
                  } else {
                    // Legacy roles use individual boolean columns
                    const fieldMap = {
                      lo: 'lo_responsible',
                      jr_lo: 'jr_lo_responsible',
                      production_asst: 'production_asst_responsible',
                      concierge: 'concierge_responsible',
                      ai: 'ai_responsible'
                    };
                    isResponsible = day[fieldMap[role.key]];
                  }

                  return (
                    <td key={role.key} className="checkbox-cell">
                      <label className="checkbox-wrapper">
                        <input
                          type="checkbox"
                          checked={isResponsible || false}
                          onChange={() => toggleResponsibility(day.id, role.key, role)}
                          disabled={saving}
                        />
                        <span className={`custom-checkbox ${isResponsible ? 'checked' : ''}`}></span>
                      </label>
                    </td>
                  );
                })}

                {/* Actions */}
                <td className="actions-cell">
                  <button
                    className="btn-edit-day"
                    onClick={() => handleEditDay(day)}
                    title="Edit this task"
                    disabled={saving}
                  >
                    ✎
                  </button>
                  <button
                    className="btn-delete-day"
                    onClick={() => handleDeleteDay(day.id)}
                    title="Delete this task"
                    disabled={saving}
                  >
                    &times;
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Add Day Section */}
      <div className="add-day-section">
        {showAddDay ? (
          <div className="add-day-form">
            <input
              type="text"
              placeholder="Day Label (e.g., Day 15)"
              value={newDay.label}
              onChange={(e) => setNewDay(prev => ({ ...prev, label: e.target.value }))}
              className="input-day-label"
            />
            <input
              type="number"
              placeholder="Day Value"
              value={newDay.value}
              onChange={(e) => setNewDay(prev => ({ ...prev, value: e.target.value }))}
              className="input-day-value"
            />
            <button onClick={handleAddDay} disabled={saving || !newDay.label || !newDay.value} className="btn-save-day">
              Add Day
            </button>
            <button onClick={() => { setShowAddDay(false); setNewDay({ label: '', value: '' }); }} className="btn-cancel">
              Cancel
            </button>
          </div>
        ) : (
          <button onClick={() => setShowAddDay(true)} className="btn-add-day">
            + Add Day
          </button>
        )}
      </div>

      {/* Task Description Legend */}
      <div className="legend-section">
        <h4>Legend</h4>
        <div className="legend-items">
          <div className="legend-item">
            <span className="health-dot healthy"></span>
            <span>Task is active and functioning</span>
          </div>
          <div className="legend-item">
            <span className="health-dot broken"></span>
            <span>Task has issues - admin task created</span>
          </div>
          <div className="legend-item">
            <span className="health-dot disabled"></span>
            <span>Task is disabled</span>
          </div>
        </div>
        <div className="legend-items">
          {COMMUNICATION_METHODS.map(method => (
            <div key={method.key} className="legend-item">
              <span className="method-dot" style={{ backgroundColor: method.color }}></span>
              <span>{method.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default WorkflowConfigEditor;
