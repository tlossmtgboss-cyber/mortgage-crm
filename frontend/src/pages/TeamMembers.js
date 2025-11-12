import React, { useState, useEffect } from 'react';
import { teamAPI } from '../services/api';
import './Settings.css';

function TeamMembers() {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingMember, setEditingMember] = useState(null);
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    role: '',
    title: ''
  });

  useEffect(() => {
    loadMembers();
  }, []);

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
    setShowAddModal(true);
  };

  const handleEditMember = (member) => {
    setFormData({
      first_name: member.first_name || '',
      last_name: member.last_name || '',
      email: member.email || '',
      phone: member.phone || '',
      role: member.role || '',
      title: member.title || ''
    });
    setEditingMember(member);
    setShowAddModal(true);
  };

  const handleSaveMember = async (e) => {
    e.preventDefault();

    try {
      if (editingMember) {
        await teamAPI.updateMember(editingMember.id, formData);
      } else {
        await teamAPI.createMember(formData);
      }

      setShowAddModal(false);
      loadMembers();
      alert(editingMember ? 'Team member updated!' : 'Team member added!');
    } catch (error) {
      console.error('Failed to save team member:', error);
      alert('Failed to save team member');
    }
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

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>Team Members</h1>
        <button className="btn-primary" onClick={handleAddMember}>
          + Add Team Member
        </button>
      </div>

      <div className="settings-content">
        <div className="team-members-grid">
          {members.length === 0 ? (
            <div className="empty-state">
              <h3>No Team Members Yet</h3>
              <p>Add your first team member to get started</p>
              <button className="btn-primary" onClick={handleAddMember}>
                + Add Team Member
              </button>
            </div>
          ) : (
            <table className="team-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Phone</th>
                  <th>Role</th>
                  <th>Title</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <strong>
                        {member.first_name} {member.last_name}
                      </strong>
                    </td>
                    <td>{member.email || '-'}</td>
                    <td>{member.phone || '-'}</td>
                    <td>
                      <span className="role-badge">{member.role || 'Team Member'}</span>
                    </td>
                    <td>{member.title || '-'}</td>
                    <td>
                      <button
                        className="btn-edit"
                        onClick={() => handleEditMember(member)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn-delete"
                        onClick={() => handleDeleteMember(member.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Add/Edit Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingMember ? 'Edit Team Member' : 'Add Team Member'}</h2>
              <button className="modal-close" onClick={() => setShowAddModal(false)}>
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
                      <option value="Loan Officer">Loan Officer</option>
                      <option value="Processor">Processor</option>
                      <option value="Underwriter">Underwriter</option>
                      <option value="Closer">Closer</option>
                      <option value="Manager">Manager</option>
                      <option value="Admin">Admin</option>
                      <option value="Other">Other</option>
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
                  onClick={() => setShowAddModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  {editingMember ? 'Update' : 'Add'} Member
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default TeamMembers;
