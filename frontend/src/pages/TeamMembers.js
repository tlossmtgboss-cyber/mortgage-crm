import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import './Settings.css';
import './Leads.css';

function TeamMembers() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission } = usePermissions();

  // Permission check - require team management access
  const canViewTeam = hasAnyPermission(['team.view_all', 'team.view_team', 'team.manage_permissions']) || userRole === 'management' || userRole === 'admin';
  const canEditTeam = hasAnyPermission(['team.manage', 'team.manage_permissions']) || userRole === 'management' || userRole === 'admin';

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
  const [saveStatus, setSaveStatus] = useState(''); // 'saving', 'saved', or ''
  const autoSaveTimerRef = useRef(null);
  const initialFormDataRef = useRef(null);

  useEffect(() => {
    loadMembers();
  }, []);

  // Auto-save effect - triggers 2 seconds after form data changes
  useEffect(() => {
    // Clear existing timer
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }

    // Only auto-save if we're editing an existing member (not adding new)
    if (!editingMember) {
      return;
    }

    // Check if data has actually changed from initial values
    if (initialFormDataRef.current && JSON.stringify(formData) === JSON.stringify(initialFormDataRef.current)) {
      return;
    }

    // Don't auto-save if required fields are empty
    if (!formData.first_name || !formData.last_name || !formData.role) {
      return;
    }

    // Set up auto-save timer
    autoSaveTimerRef.current = setTimeout(() => {
      autoSave();
    }, 2000);

    // Cleanup function
    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
      }
    };
  }, [formData, editingMember]);

  const loadMembers = async () => {
    try {
      setLoading(true);
      setSelectedMembers([]); // Clear selection when reloading
      const data = await teamAPI.getMembers();

      console.log('Team API response:', data);
      console.log('Type of data:', typeof data);

      // Handle different response formats
      let membersList = [];

      if (Array.isArray(data)) {
        // Direct array response
        membersList = data;
      } else if (data && typeof data === 'object') {
        // Object with team_members property
        if (Array.isArray(data.team_members)) {
          membersList = data.team_members;
        } else if (data.team_members && typeof data.team_members === 'string') {
          // Handle case where backend returns stringified data
          try {
            const parsed = JSON.parse(data.team_members);
            membersList = Array.isArray(parsed) ? parsed : [];
          } catch (e) {
            console.error('Failed to parse team_members string:', e);
            membersList = [];
          }
        }
      }

      console.log('Processed members list:', membersList);
      setMembers(membersList);
    } catch (error) {
      console.error('Failed to load team members:', error);
      setMembers([]);
    } finally {
      setLoading(false);
    }
  };

  const autoSave = async () => {
    if (!editingMember) return;

    try {
      setSaveStatus('saving');
      await teamAPI.updateMember(editingMember.id, formData);
      setSaveStatus('saved');

      // Update the initial form data to reflect the saved state
      initialFormDataRef.current = { ...formData };

      // Update the member in the list using functional update to avoid stale closure
      setMembers(prevMembers => prevMembers.map(m =>
        m.id === editingMember.id
          ? { ...m, ...formData }
          : m
      ));

      // Clear 'saved' status after 2 seconds
      setTimeout(() => {
        setSaveStatus('');
      }, 2000);
    } catch (error) {
      console.error('Auto-save failed:', error);
      setSaveStatus('error');
      setTimeout(() => {
        setSaveStatus('');
      }, 3000);
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

    // Only handle new member creation (editing is auto-saved)
    if (!editingMember) {
      try {
        await teamAPI.createMember(formData);
        setShowAddModal(false);
        loadMembers();
        alert('Team member added!');
      } catch (error) {
        console.error('Failed to save team member:', error);
        alert('Failed to save team member');
      }
    }
  };

  const handleCloseModal = () => {
    // Clear any pending auto-save timers
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }
    setShowAddModal(false);
    setSaveStatus('');
  };

  const handleDeleteMember = async (memberId) => {
    try {
      await teamAPI.deleteMember(memberId);
      loadMembers();
      alert('Team member removed');
    } catch (error) {
      console.error('Failed to delete team member:', error);
      alert('Failed to remove team member');
    }
  };

  // Handle checkbox selection for a single member
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

  // Handle select all checkbox
  const handleSelectAll = (e) => {
    e.stopPropagation();
    const safeMembers = Array.isArray(members) ? members : [];
    if (selectedMembers.length === safeMembers.length) {
      // Deselect all
      setSelectedMembers([]);
    } else {
      // Select all
      setSelectedMembers(safeMembers.map(m => m.id));
    }
  };

  // Handle bulk delete
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
      alert(`Successfully deleted ${successCount} team member${successCount > 1 ? 's' : ''}`);
    } else {
      alert(`Deleted ${successCount} member${successCount !== 1 ? 's' : ''}, failed to delete ${failCount}`);
    }
  };

  const handleChange = (field, value) => {
    setFormData({ ...formData, [field]: value });
  };

  if (loading) {
    return <div className="loading">Loading team members...</div>;
  }

  // Filter by search query - ensure members is always an array
  const safeMembers = Array.isArray(members) ? members : [];
  let filteredMembers = safeMembers;

  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    filteredMembers = safeMembers.filter(member =>
      member &&
      (
        `${member.first_name || ''} ${member.last_name || ''}`.toLowerCase().includes(query) ||
        member.email?.toLowerCase().includes(query) ||
        member.phone?.toLowerCase().includes(query) ||
        member.role?.toLowerCase().includes(query) ||
        member.title?.toLowerCase().includes(query)
      )
    );
  }

  // Access denied if user doesn't have team permissions
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

  return (
    <div className="leads-page">
      <div className="page-header">
        <div>
          <h1>Team Members</h1>
          <p>{String(safeMembers.length)} total team members</p>
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
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {filteredMembers.map((member) => {
                if (!member || !member.id) return null;
                const isSelected = selectedMembers.includes(member.id);
                return (
                  <tr
                    key={member.id}
                    onClick={() => navigate(`/team-members/${member.id}`)}
                    style={{
                      cursor: 'pointer',
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
                    <td className="lead-name">
                      <strong>
                        {`${member.first_name || ''} ${member.last_name || ''}`.trim() || 'No Name'}
                      </strong>
                    </td>
                    <td>{String(member.email || 'N/A')}</td>
                    <td>{String(member.phone || 'N/A')}</td>
                    <td>
                      <span className="status-badge status-prospect">{String(member.role || 'Team Member')}</span>
                    </td>
                    <td>{String(member.title || 'N/A')}</td>
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
    </div>
  );
}

export default TeamMembers;
