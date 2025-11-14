import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI } from '../services/api';
import './Settings.css';
import './Leads.css';

function TeamMembers() {
  const navigate = useNavigate();
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingMember, setEditingMember] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
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
      const data = await teamAPI.getMembers();
      // API returns an array of team members directly
      setMembers(Array.isArray(data) ? data : []);
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
    if (!window.confirm('Are you sure you want to remove this team member?')) {
      return;
    }

    try {
      await teamAPI.deleteMember(memberId);
      loadMembers();
      alert('Team member removed');
    } catch (error) {
      console.error('Failed to delete team member:', error);
      alert('Failed to remove team member');
    }
  };

  const handleChange = (field, value) => {
    setFormData({ ...formData, [field]: value });
  };

  if (loading) {
    return <div className="loading">Loading team members...</div>;
  }

  // Filter by search query
  let filteredMembers = members;
  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    filteredMembers = members.filter(member =>
      `${member.first_name} ${member.last_name}`.toLowerCase().includes(query) ||
      member.email?.toLowerCase().includes(query) ||
      member.phone?.toLowerCase().includes(query) ||
      member.role?.toLowerCase().includes(query) ||
      member.title?.toLowerCase().includes(query)
    );
  }

  return (
    <div className="leads-page">
      <div className="page-header">
        <div>
          <h1>Team Members</h1>
          <p>{members.length} total team members</p>
        </div>
        <button className="btn-primary" onClick={handleAddMember}>
          + Add Team Member
        </button>
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
                <th>NAME</th>
                <th>EMAIL</th>
                <th>PHONE</th>
                <th>ROLE</th>
                <th>TITLE</th>
                <th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {filteredMembers.map((member) => (
                <tr
                  key={member.id}
                  onClick={() => navigate(`/team-members/${member.id}`)}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="lead-name">
                    <strong>
                      {member.first_name} {member.last_name}
                    </strong>
                  </td>
                  <td>{member.email || 'N/A'}</td>
                  <td>{member.phone || 'N/A'}</td>
                  <td>
                    <span className="status-badge status-prospect">{member.role || 'Team Member'}</span>
                  </td>
                  <td>{member.title || 'N/A'}</td>
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
              ))}
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
