import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI, API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './Settings.css';
import './Leads.css';

// Debug: Log API_BASE_URL on module load
console.log('[DEBUG] TeamMembers API_BASE_URL:', API_BASE_URL);

function TeamMembers() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - require team management access
  // Use isAdmin from context which has robust admin detection (checks permission_role, is_admin flag, legacy role)
  const canViewTeam = isAdmin || hasAnyPermission(['team.view_all', 'team.view_team', 'team.manage_permissions']) || userRole === 'management' || userRole === 'admin';
  const canEditTeam = isAdmin || hasAnyPermission(['team.manage', 'team.manage_permissions']) || userRole === 'management' || userRole === 'admin';

  // Team Members state
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingMember, setEditingMember] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMembers, setSelectedMembers] = useState([]);
  const [deletingMembers, setDeletingMembers] = useState(false);
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    role: '',
    title: '',
    workflow_role_id: ''
  });
  const [saveStatus, setSaveStatus] = useState('');
  const autoSaveTimerRef = useRef(null);
  const initialFormDataRef = useRef(null);

  // Workflow roles state
  const [workflowRoles, setWorkflowRoles] = useState([]);
  const [roleAssignments, setRoleAssignments] = useState({}); // { memberId: [roleId1, roleId2, ...] }
  const [savingWorkflowRole, setSavingWorkflowRole] = useState({}); // { memberId: true/false }
  const [seedingRoles, setSeedingRoles] = useState(false);
  const [addingRoleForMember, setAddingRoleForMember] = useState(null); // memberId currently showing add-role dropdown

  const getAuthHeaders = useCallback(() => ({
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
    'Content-Type': 'application/json',
  }), []);

  // Load team members
  const loadMembers = async () => {
    try {
      setLoading(true);
      setSelectedMembers([]);
      const data = await teamAPI.getMembers();

      let membersList = [];
      if (Array.isArray(data)) {
        membersList = data;
      } else if (data && typeof data === 'object') {
        if (Array.isArray(data.team_members)) {
          membersList = data.team_members;
        } else if (data.team_members && typeof data.team_members === 'string') {
          try {
            const parsed = JSON.parse(data.team_members);
            membersList = Array.isArray(parsed) ? parsed : [];
          } catch (e) {
            console.error('Failed to parse team_members string:', e);
            membersList = [];
          }
        }
      }

      setMembers(membersList);
    } catch (error) {
      console.error('Failed to load team members:', error);
      setMembers([]);
    } finally {
      setLoading(false);
    }
  };

  // Load workflow roles
  const loadWorkflowRoles = useCallback(async () => {
    const url = `${API_BASE_URL}/api/v1/settings/team-roles`;
    console.log('[DEBUG] Loading workflow roles from:', url);

    try {
      const response = await fetch(url, {
        headers: getAuthHeaders(),
      });

      console.log('[DEBUG] Workflow roles response status:', response.status);

      if (response.ok) {
        const data = await response.json();
        console.log('[DEBUG] Workflow roles data:', data);
        setWorkflowRoles(data.assignments || []);

        // Build reverse mapping: userId -> [roleId1, roleId2, ...]
        const assignments = {};
        (data.assignments || []).forEach(role => {
          if (role.user_id) {
            if (!assignments[role.user_id]) assignments[role.user_id] = [];
            assignments[role.user_id].push(role.role_id);
          }
        });
        setRoleAssignments(assignments);
      } else {
        const errorText = await response.text();
        console.error('[DEBUG] Workflow roles error response:', errorText);
      }
    } catch (error) {
      console.error('[DEBUG] Error loading workflow roles:', error);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    loadMembers();
    loadWorkflowRoles();
  }, [loadWorkflowRoles]);

  // Auto-save effect for team member editing
  useEffect(() => {
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }

    if (!editingMember) return;

    if (initialFormDataRef.current && JSON.stringify(formData) === JSON.stringify(initialFormDataRef.current)) {
      return;
    }

    if (!formData.first_name || !formData.last_name) {
      return;
    }

    autoSaveTimerRef.current = setTimeout(() => {
      autoSave();
    }, 2000);

    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
      }
    };
  }, [formData, editingMember]);

  const autoSave = async () => {
    if (!editingMember) return;

    try {
      setSaveStatus('saving');
      await teamAPI.updateMember(editingMember.id, formData);
      setSaveStatus('saved');
      initialFormDataRef.current = { ...formData };

      setMembers(prevMembers => prevMembers.map(m =>
        m.id === editingMember.id ? { ...m, ...formData } : m
      ));

      setTimeout(() => setSaveStatus(''), 2000);
    } catch (error) {
      console.error('Auto-save failed:', error);
      setSaveStatus('error');
      setTimeout(() => setSaveStatus(''), 3000);
    }
  };

  // Add a role to a member (multi-role: doesn't remove existing roles)
  const handleAddRole = async (memberId, roleId) => {
    if (!roleId) return;
    roleId = parseInt(roleId);

    // Check if this role is already assigned to someone else
    const existingRole = workflowRoles.find(r => r.role_id === roleId);
    if (existingRole && existingRole.user_id && existingRole.user_id !== memberId) {
      const confirmMessage = `"${existingRole.role_name}" is currently assigned to ${existingRole.user_name}.\n\nDo you want to reassign this role?`;
      if (!window.confirm(confirmMessage)) {
        return;
      }
    }

    setSavingWorkflowRole(prev => ({ ...prev, [memberId]: true }));

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${roleId}`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ user_id: memberId }),
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message || 'Role assigned');
        loadWorkflowRoles();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to assign role');
      }
    } catch (error) {
      console.error('Error adding role:', error);
      toast.error('Failed to assign role');
    } finally {
      setSavingWorkflowRole(prev => ({ ...prev, [memberId]: false }));
      setAddingRoleForMember(null);
    }
  };

  // Remove a single role from a member
  const handleRemoveRole = async (memberId, roleId) => {
    setSavingWorkflowRole(prev => ({ ...prev, [memberId]: true }));

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${roleId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        toast.success('Role removed');
        loadWorkflowRoles();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to remove role');
      }
    } catch (error) {
      console.error('Error removing role:', error);
      toast.error('Failed to remove role');
    } finally {
      setSavingWorkflowRole(prev => ({ ...prev, [memberId]: false }));
    }
  };

  // Seed workflow roles if none exist
  const seedWorkflowRoles = async () => {
    setSeedingRoles(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/settings/seed-workflow-roles`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message || 'Workflow roles seeded successfully');
        // Reload the workflow roles
        await loadWorkflowRoles();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to seed workflow roles');
      }
    } catch (error) {
      console.error('Error seeding workflow roles:', error);
      toast.error('Failed to seed workflow roles');
    } finally {
      setSeedingRoles(false);
    }
  };

  const handleAddMember = () => {
    setFormData({
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      role: '',
      title: '',
      workflow_role_id: ''
    });
    setEditingMember(null);
    setSaveStatus('');
    initialFormDataRef.current = null;
    setShowAddModal(true);
  };

  const handleEditMember = (member) => {
    const initialData = {
      first_name: member.first_name || '',
      last_name: member.last_name || '',
      email: member.email || '',
      phone: member.phone || '',
      role: member.role || '',
      title: member.title || ''
    };
    setFormData(initialData);
    initialFormDataRef.current = { ...initialData };
    setEditingMember(member);
    setSaveStatus('');
    setShowAddModal(true);
  };

  const handleSaveMember = async (e) => {
    e.preventDefault();

    if (!editingMember) {
      try {
        // Create the member first
        const newMember = await teamAPI.createMember(formData);

        // If a workflow role was selected, assign it to the new member
        if (formData.workflow_role_id && newMember && newMember.id) {
          try {
            await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${formData.workflow_role_id}`, {
              method: 'POST',
              headers: getAuthHeaders(),
              body: JSON.stringify({ user_id: newMember.id }),
            });
          } catch (roleError) {
            console.error('Failed to assign workflow role:', roleError);
            // Don't fail the whole operation, just log it
          }
        }

        setShowAddModal(false);
        loadMembers();
        loadWorkflowRoles();
        toast.success('Team member added!');
      } catch (error) {
        console.error('Failed to save team member:', error);
        toast.error('Failed to save team member');
      }
    }
  };

  const handleCloseModal = () => {
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }
    setShowAddModal(false);
    setSaveStatus('');
  };

  const handleDeleteMember = async (memberId) => {
    if (!window.confirm('Are you sure you want to delete this team member?')) return;

    try {
      await teamAPI.deleteMember(memberId);
      loadMembers();
      toast.success('Team member removed');
    } catch (error) {
      console.error('Failed to delete team member:', error);
      toast.error('Failed to remove team member');
    }
  };

  const handleSelectMember = (memberId, e) => {
    e.stopPropagation();
    setSelectedMembers(prev => {
      if (prev.includes(memberId)) {
        return prev.filter(id => id !== memberId);
      } else {
        return [...prev, memberId];
      }
    });
  };

  const handleSelectAll = (e) => {
    e.stopPropagation();
    const safeMembers = Array.isArray(members) ? members : [];
    if (selectedMembers.length === safeMembers.length) {
      setSelectedMembers([]);
    } else {
      setSelectedMembers(safeMembers.map(m => m.id));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedMembers.length === 0) return;

    const confirmMessage = `Are you sure you want to delete ${selectedMembers.length} team member${selectedMembers.length > 1 ? 's' : ''}? This action cannot be undone.`;
    if (!window.confirm(confirmMessage)) return;

    setDeletingMembers(true);
    let successCount = 0;
    let failCount = 0;

    for (const memberId of selectedMembers) {
      try {
        await teamAPI.deleteMember(memberId);
        successCount++;
      } catch (error) {
        console.error(`Failed to delete member ${memberId}:`, error);
        failCount++;
      }
    }

    setDeletingMembers(false);
    setSelectedMembers([]);
    loadMembers();

    if (failCount === 0) {
      toast.success(`Successfully deleted ${successCount} team member${successCount > 1 ? 's' : ''}`);
    } else {
      toast.warning(`Deleted ${successCount} member${successCount !== 1 ? 's' : ''}, failed to delete ${failCount}`);
    }
  };

  const handleChange = (field, value) => {
    setFormData({ ...formData, [field]: value });
  };

  // Get workflow role names for a member (returns array)
  const getMemberWorkflowRoles = (memberId) => {
    const roleIds = roleAssignments[memberId] || [];
    return roleIds.map(rid => {
      const role = workflowRoles.find(r => r.role_id === rid);
      return role ? { role_id: rid, role_name: role.role_name } : null;
    }).filter(Boolean);
  };

  // Get roles NOT yet assigned to this member (for "Add Role" dropdown)
  const getAvailableRolesForMember = (memberId) => {
    const assignedIds = roleAssignments[memberId] || [];
    return workflowRoles.filter(r => !assignedIds.includes(r.role_id));
  };

  if (loading) {
    return <div className="loading">Loading team...</div>;
  }

  const safeMembers = Array.isArray(members) ? members : [];
  let filteredMembers = safeMembers;

  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    filteredMembers = safeMembers.filter(member =>
      member &&
      (
        `${member.first_name || ''} ${member.last_name || ''}`.toLowerCase().includes(query) ||
        member.full_name?.toLowerCase().includes(query) ||
        member.email?.toLowerCase().includes(query) ||
        member.phone?.toLowerCase().includes(query) ||
        member.role?.toLowerCase().includes(query) ||
        member.title?.toLowerCase().includes(query)
      )
    );
  }

  if (!canViewTeam) {
    return (
      <div className="leads-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to view team members.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Count how many team members have at least one workflow role assigned
  const membersWithRoles = safeMembers.filter(member => (roleAssignments[member.id] || []).length > 0).length;

  return (
    <div className="leads-page">
      <div className="page-header">
        <div>
          <h1>Team Management</h1>
          <p>Manage your team members and workflow role assignments</p>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {selectedMembers.length > 0 && (
            <button
              className="btn-danger"
              onClick={handleBulkDelete}
              disabled={deletingMembers}
              style={{
                padding: '10px 20px',
                background: '#dc2626',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: deletingMembers ? 'not-allowed' : 'pointer',
                fontWeight: '500',
                opacity: deletingMembers ? 0.7 : 1
              }}
            >
              {deletingMembers ? 'Deleting...' : `Delete Selected (${selectedMembers.length})`}
            </button>
          )}
          <button className="btn-primary" onClick={handleAddMember}>
            + Add Team Member
          </button>
        </div>
      </div>

      <div className="search-bar-container">
        <input
          type="text"
          className="search-bar"
          placeholder="Search team members by name, email, phone, or role..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button className="clear-search" onClick={() => setSearchQuery('')}>
            ×
          </button>
        )}
      </div>

      <div className="table-container">
        {filteredMembers.length === 0 ? (
          <div className="empty-state">
            <h3>No Team Members Found</h3>
            <p>{searchQuery ? 'Try adjusting your search' : 'Add your first team member to get started'}</p>
            {!searchQuery && (
              <button className="btn-primary" onClick={handleAddMember}>
                + Add Team Member
              </button>
            )}
          </div>
        ) : (
          <table className="leads-table">
            <thead>
              <tr>
                <th style={{ width: '40px', textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    onChange={handleSelectAll}
                    checked={safeMembers.length > 0 && selectedMembers.length === safeMembers.length}
                    style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                    title="Select all"
                  />
                </th>
                <th>NAME</th>
                <th>EMAIL</th>
                <th>PHONE</th>
                <th>TITLE</th>
                <th style={{ minWidth: '220px' }}>WORKFLOW ROLES</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {filteredMembers.map((member) => {
                if (!member || !member.id) return null;
                const isSelected = selectedMembers.includes(member.id);
                const memberRoles = getMemberWorkflowRoles(member.id);
                const availableRoles = getAvailableRolesForMember(member.id);
                const isSavingRole = savingWorkflowRole[member.id];
                const isAddingRole = addingRoleForMember === member.id;

                return (
                  <tr
                    key={member.id}
                    style={{
                      backgroundColor: isSelected ? '#e0f2fe' : undefined
                    }}
                  >
                    <td style={{ textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => handleSelectMember(member.id, e)}
                        style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                      />
                    </td>
                    <td
                      className="lead-name"
                      style={{ cursor: 'pointer' }}
                      onClick={() => navigate(`/team-members/${member.id}`)}
                    >
                      <strong>
                        {member.full_name || `${member.first_name || ''} ${member.last_name || ''}`.trim() || 'No Name'}
                      </strong>
                    </td>
                    <td>{String(member.email || 'N/A')}</td>
                    <td>{String(member.phone || 'N/A')}</td>
                    <td>{String(member.title || 'N/A')}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center' }}>
                        {/* Role chips */}
                        {memberRoles.map(r => (
                          <span
                            key={r.role_id}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              padding: '3px 8px',
                              borderRadius: '12px',
                              background: '#e0f2f1',
                              border: '1px solid #218D8D',
                              fontSize: '12px',
                              color: '#0d5c5c',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {r.role_name}
                            <button
                              onClick={() => handleRemoveRole(member.id, r.role_id)}
                              disabled={isSavingRole}
                              title={`Remove ${r.role_name}`}
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: isSavingRole ? 'wait' : 'pointer',
                                padding: '0 2px',
                                fontSize: '14px',
                                lineHeight: 1,
                                color: '#991b1b',
                                fontWeight: 'bold',
                              }}
                            >
                              x
                            </button>
                          </span>
                        ))}
                        {/* Add Role button / dropdown */}
                        {isAddingRole ? (
                          <select
                            autoFocus
                            value=""
                            onChange={(e) => {
                              if (e.target.value) handleAddRole(member.id, e.target.value);
                            }}
                            onBlur={() => setAddingRoleForMember(null)}
                            disabled={isSavingRole}
                            style={{
                              padding: '3px 6px',
                              borderRadius: '6px',
                              border: '1px solid #d1d5db',
                              fontSize: '12px',
                              cursor: isSavingRole ? 'wait' : 'pointer',
                              minWidth: '130px',
                            }}
                          >
                            <option value="">Select role...</option>
                            {availableRoles.map(role => {
                              const isAssignedToOther = role.user_id && role.user_id !== member.id;
                              const assignedToName = isAssignedToOther ? role.user_name : null;
                              return (
                                <option key={role.role_id} value={role.role_id}>
                                  {role.role_name}
                                  {assignedToName ? ` (${assignedToName})` : ''}
                                </option>
                              );
                            })}
                          </select>
                        ) : (
                          availableRoles.length > 0 && (
                            <button
                              onClick={() => setAddingRoleForMember(member.id)}
                              disabled={isSavingRole}
                              style={{
                                background: 'none',
                                border: '1px dashed #9ca3af',
                                borderRadius: '12px',
                                padding: '3px 8px',
                                fontSize: '12px',
                                color: '#6b7280',
                                cursor: isSavingRole ? 'wait' : 'pointer',
                                whiteSpace: 'nowrap',
                              }}
                              title="Add another role"
                            >
                              + Add Role
                            </button>
                          )
                        )}
                        {isSavingRole && (
                          <span style={{
                            width: '16px',
                            height: '16px',
                            border: '2px solid #e5e7eb',
                            borderTopColor: '#218D8D',
                            borderRadius: '50%',
                            animation: 'spin 0.8s linear infinite',
                            flexShrink: 0,
                          }} />
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="btn-icon"
                          onClick={(e) => { e.stopPropagation(); handleEditMember(member); }}
                          title="Edit"
                        >
                          ✏️
                        </button>
                        <button
                          className="btn-icon"
                          onClick={(e) => { e.stopPropagation(); handleDeleteMember(member.id); }}
                          title="Delete"
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Summary footer */}
      <div style={{
        marginTop: '16px',
        padding: '12px 16px',
        background: workflowRoles.length === 0 ? '#fef3c7' : '#f0f9ff',
        borderRadius: '8px',
        border: `1px solid ${workflowRoles.length === 0 ? '#f59e0b' : '#bae6fd'}`,
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        flexWrap: 'wrap'
      }}>
        <span style={{ fontSize: '16px' }}>{workflowRoles.length === 0 ? '⚠️' : 'ℹ️'}</span>
        <span style={{ color: workflowRoles.length === 0 ? '#92400e' : '#0369a1', fontSize: '14px', flex: 1 }}>
          {workflowRoles.length === 0 ? (
            'No workflow roles configured. Click the button to set up workflow roles for your team.'
          ) : (
            `${membersWithRoles} of ${safeMembers.length} team members have workflow roles assigned. Users can hold multiple roles.`
          )}
        </span>
        {workflowRoles.length === 0 && canEditTeam && (
          <button
            onClick={seedWorkflowRoles}
            disabled={seedingRoles}
            style={{
              padding: '8px 16px',
              background: '#0066cc',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: seedingRoles ? 'wait' : 'pointer',
              fontSize: '14px',
              fontWeight: '500',
              opacity: seedingRoles ? 0.7 : 1
            }}
          >
            {seedingRoles ? 'Setting up roles...' : 'Set Up Workflow Roles'}
          </button>
        )}
      </div>

      {/* Add/Edit Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={handleCloseModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2>{editingMember ? 'Edit Team Member' : 'Add Team Member'}</h2>
                {editingMember && (
                  <div style={{ fontSize: '12px', marginTop: '4px', color: '#666' }}>
                    {saveStatus === 'saving' && (
                      <span style={{ color: '#0066cc' }}>● Saving changes...</span>
                    )}
                    {saveStatus === 'saved' && (
                      <span style={{ color: '#28a745' }}>✓ All changes saved</span>
                    )}
                    {saveStatus === 'error' && (
                      <span style={{ color: '#dc3545' }}>✗ Failed to save</span>
                    )}
                    {!saveStatus && (
                      <span style={{ color: '#999' }}>Auto-saves 2 seconds after changes</span>
                    )}
                  </div>
                )}
              </div>
              <button className="modal-close" onClick={handleCloseModal}>
                ×
              </button>
            </div>

            <form onSubmit={handleSaveMember}>
              <div className="form-section">
                <div className="form-row">
                  <div className="form-group">
                    <label>First Name *</label>
                    <input
                      type="text"
                      value={formData.first_name}
                      onChange={(e) => handleChange('first_name', e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Last Name *</label>
                    <input
                      type="text"
                      value={formData.last_name}
                      onChange={(e) => handleChange('last_name', e.target.value)}
                      required
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Email</label>
                    <input
                      type="email"
                      value={formData.email}
                      onChange={(e) => handleChange('email', e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label>Phone</label>
                    <input
                      type="tel"
                      value={formData.phone}
                      onChange={(e) => handleChange('phone', e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Title</label>
                    <input
                      type="text"
                      value={formData.title}
                      onChange={(e) => handleChange('title', e.target.value)}
                      placeholder="e.g., Senior Loan Officer"
                    />
                  </div>
                  <div className="form-group">
                    <label>Workflow Role{editingMember ? 's' : ''}</label>
                    {editingMember ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center', minHeight: '36px' }}>
                        {getMemberWorkflowRoles(editingMember.id).map(r => (
                          <span
                            key={r.role_id}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              padding: '4px 10px',
                              borderRadius: '14px',
                              background: '#e0f2f1',
                              border: '1px solid #218D8D',
                              fontSize: '13px',
                              color: '#0d5c5c',
                            }}
                          >
                            {r.role_name}
                            <button
                              type="button"
                              onClick={() => handleRemoveRole(editingMember.id, r.role_id)}
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                padding: '0 2px',
                                fontSize: '14px',
                                lineHeight: 1,
                                color: '#991b1b',
                                fontWeight: 'bold',
                              }}
                            >
                              x
                            </button>
                          </span>
                        ))}
                        <select
                          value=""
                          onChange={(e) => {
                            if (e.target.value) handleAddRole(editingMember.id, e.target.value);
                          }}
                          style={{
                            padding: '4px 8px',
                            borderRadius: '6px',
                            border: '1px dashed #9ca3af',
                            fontSize: '13px',
                            color: '#6b7280',
                            background: 'white',
                          }}
                        >
                          <option value="">+ Add Role</option>
                          {getAvailableRolesForMember(editingMember.id).map(role => (
                            <option key={role.role_id} value={role.role_id}>
                              {role.role_name}
                              {role.user_id && role.user_id !== editingMember.id ? ` (${role.user_name})` : ''}
                            </option>
                          ))}
                        </select>
                      </div>
                    ) : (
                      <select
                        value={formData.workflow_role_id || ''}
                        onChange={(e) => handleChange('workflow_role_id', e.target.value)}
                        style={{
                          padding: '8px 12px',
                          borderRadius: '6px',
                          border: '1px solid #d1d5db',
                          fontSize: '14px',
                          width: '100%'
                        }}
                      >
                        <option value="">-- Select Role --</option>
                        {workflowRoles.map(role => (
                          <option key={role.role_id} value={role.role_id}>
                            {role.role_name}
                            {role.user_id ? ` (${role.user_name})` : ''}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleCloseModal}
                >
                  {editingMember ? 'Close' : 'Cancel'}
                </button>
                {!editingMember && (
                  <button type="submit" className="btn-primary">
                    Add Member
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

export default TeamMembers;
