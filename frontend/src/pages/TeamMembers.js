import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI, API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './Settings.css';
import './Leads.css';

function TeamMembers() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission } = usePermissions();

  // Permission check - require team management access
  const canViewTeam = hasAnyPermission(['team.view_all', 'team.view_team', 'team.manage_permissions']) || userRole === 'management' || userRole === 'admin';
  const canEditTeam = hasAnyPermission(['team.manage', 'team.manage_permissions']) || userRole === 'management' || userRole === 'admin';

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
    title: ''
  });
  const [saveStatus, setSaveStatus] = useState('');
  const autoSaveTimerRef = useRef(null);
  const initialFormDataRef = useRef(null);

  // Workflow roles state
  const [workflowRoles, setWorkflowRoles] = useState([]);
  const [roleAssignments, setRoleAssignments] = useState({}); // { memberId: roleId }
  const [savingWorkflowRole, setSavingWorkflowRole] = useState({}); // { memberId: true/false }

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
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles`, {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        setWorkflowRoles(data.assignments || []);

        // Build reverse mapping: userId -> roleId
        const assignments = {};
        (data.assignments || []).forEach(role => {
          if (role.user_id) {
            assignments[role.user_id] = role.role_id;
          }
        });
        setRoleAssignments(assignments);
      }
    } catch (error) {
      console.error('Error loading workflow roles:', error);
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

    if (!formData.first_name || !formData.last_name || !formData.role) {
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

  // Handle workflow role assignment change
  const handleWorkflowRoleChange = async (memberId, roleId) => {
    setSavingWorkflowRole(prev => ({ ...prev, [memberId]: true }));

    try {
      // First, remove any existing assignment for this user (if they had a different role)
      const previousRoleId = roleAssignments[memberId];

      if (roleId) {
        // Assign new role
        const response = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${roleId}`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ user_id: memberId }),
        });

        if (response.ok) {
          toast.success('Workflow role assigned');

          // Update local state
          setRoleAssignments(prev => {
            const newAssignments = { ...prev };
            // Remove old assignment if user was assigned to a different role
            Object.keys(newAssignments).forEach(uid => {
              if (parseInt(uid) === memberId) {
                delete newAssignments[uid];
              }
            });
            newAssignments[memberId] = parseInt(roleId);
            return newAssignments;
          });

          // Reload to get fresh data
          loadWorkflowRoles();
        } else {
          const error = await response.json();
          toast.error(error.detail || 'Failed to assign role');
        }
      } else {
        // Remove assignment - need to clear the role that this user was assigned to
        if (previousRoleId) {
          const response = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${previousRoleId}`, {
            method: 'DELETE',
            headers: getAuthHeaders(),
          });

          if (response.ok) {
            toast.success('Workflow role removed');
            setRoleAssignments(prev => {
              const newAssignments = { ...prev };
              delete newAssignments[memberId];
              return newAssignments;
            });
          } else {
            const error = await response.json();
            toast.error(error.detail || 'Failed to remove role');
          }
        }
      }
    } catch (error) {
      console.error('Error updating workflow role:', error);
      toast.error('Failed to update workflow role');
    } finally {
      setSavingWorkflowRole(prev => ({ ...prev, [memberId]: false }));
    }
  };

  const handleAddMember = () => {
    setFormData({
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      role: '',
      title: ''
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
        await teamAPI.createMember(formData);
        setShowAddModal(false);
        loadMembers();
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

  // Get the workflow role name for a member
  const getMemberWorkflowRole = (memberId) => {
    const roleId = roleAssignments[memberId];
    if (!roleId) return null;
    const role = workflowRoles.find(r => r.role_id === roleId);
    return role ? role.role_name : null;
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

  const assignedCount = Object.keys(roleAssignments).length;

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
                <th>ROLE</th>
                <th>TITLE</th>
                <th style={{ minWidth: '180px' }}>WORKFLOW ROLE</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {filteredMembers.map((member) => {
                if (!member || !member.id) return null;
                const isSelected = selectedMembers.includes(member.id);
                const assignedRoleId = roleAssignments[member.id];
                const isSavingRole = savingWorkflowRole[member.id];

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
                    <td>
                      <span className="status-badge status-prospect">{String(member.role || 'Team Member')}</span>
                    </td>
                    <td>{String(member.title || 'N/A')}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <select
                          value={assignedRoleId || ''}
                          onChange={(e) => handleWorkflowRoleChange(member.id, e.target.value)}
                          disabled={isSavingRole}
                          style={{
                            padding: '6px 28px 6px 10px',
                            borderRadius: '6px',
                            border: assignedRoleId ? '2px solid #218D8D' : '1px solid #d1d5db',
                            background: assignedRoleId ? '#f0fdf4' : 'white',
                            fontSize: '13px',
                            cursor: isSavingRole ? 'wait' : 'pointer',
                            minWidth: '150px',
                            appearance: 'none',
                            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%236b7280' d='M6 8L1 3h10z'/%3E%3C/svg%3E")`,
                            backgroundRepeat: 'no-repeat',
                            backgroundPosition: 'right 8px center',
                            opacity: isSavingRole ? 0.7 : 1
                          }}
                        >
                          <option value="">-- None --</option>
                          {workflowRoles.map(role => (
                            <option
                              key={role.role_id}
                              value={role.role_id}
                              disabled={role.user_id && role.user_id !== member.id}
                            >
                              {role.role_name}
                              {role.user_id && role.user_id !== member.id ? ' (assigned)' : ''}
                            </option>
                          ))}
                        </select>
                        {isSavingRole && (
                          <span style={{
                            width: '16px',
                            height: '16px',
                            border: '2px solid #e5e7eb',
                            borderTopColor: '#218D8D',
                            borderRadius: '50%',
                            animation: 'spin 0.8s linear infinite'
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
        background: '#f0f9ff',
        borderRadius: '8px',
        border: '1px solid #bae6fd',
        display: 'flex',
        alignItems: 'center',
        gap: '8px'
      }}>
        <span style={{ fontSize: '16px' }}>ℹ️</span>
        <span style={{ color: '#0369a1', fontSize: '14px' }}>
          {assignedCount} of {workflowRoles.length} workflow roles assigned.
          Workflow roles determine default team member assignments for new loans and leads.
        </span>
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
                    <label>Role *</label>
                    <select
                      value={formData.role}
                      onChange={(e) => handleChange('role', e.target.value)}
                      required
                    >
                      <option value="">Select Role...</option>
                      <option value="Application Analysis">Application Analysis</option>
                      <option value="Concierge">Concierge</option>
                      <option value="Jr. Loan Officer">Jr. Loan Officer</option>
                      <option value="Jr. Processor">Jr. Processor</option>
                      <option value="Loan Officer">Loan Officer</option>
                      <option value="Loan Officer Assistant">Loan Officer Assistant</option>
                      <option value="Processing Assistant">Processing Assistant</option>
                      <option value="Processor">Processor</option>
                      <option value="Production Assistant 1">Production Assistant 1</option>
                      <option value="Production Assistant 2">Production Assistant 2</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Title</label>
                    <input
                      type="text"
                      value={formData.title}
                      onChange={(e) => handleChange('title', e.target.value)}
                      placeholder="e.g., Senior Loan Officer"
                    />
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
