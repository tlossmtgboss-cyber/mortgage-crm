import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './Users.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const DEFAULT_ROLES = [
  { id: 1, name: 'Loan Officer', taskCount: 1 },
  { id: 2, name: 'Application Analysis', taskCount: 1 },
  { id: 3, name: 'Production Assistant 1', taskCount: 1 },
  { id: 4, name: 'Production Assistant 2', taskCount: 1 },
  { id: 5, name: 'Processing Assistant', taskCount: 1 },
  { id: 6, name: 'Concierge', taskCount: 1 },
  { id: 7, name: 'Executive Assistant', taskCount: 1 },
  { id: 8, name: 'Loan Processor', taskCount: 1 },
  { id: 9, name: 'Underwriter', taskCount: 1 },
  { id: 10, name: 'Closer', taskCount: 1 },
  { id: 11, name: 'Funder', taskCount: 1 },
  { id: 12, name: 'Servicing', taskCount: 1 }
];

function Users() {
  const [teamMembers, setTeamMembers] = useState([]);
  const [availableRoles, setAvailableRoles] = useState(DEFAULT_ROLES);
  const [loading, setLoading] = useState(true);
  const [showAddMemberModal, setShowAddMemberModal] = useState(false);
  const [showAddRoleModal, setShowAddRoleModal] = useState(false);
  const [editingMember, setEditingMember] = useState(null);

  useEffect(() => {
    loadTeamMembers();
    loadRoles();
  }, []);

  const loadTeamMembers = () => {
    try {
      // Load team members from localStorage (saved during onboarding)
      const storedMembers = localStorage.getItem('teamMembers');
      if (storedMembers) {
        const members = JSON.parse(storedMembers);

        // Filter out dummy/mock data
        const realMembers = members.filter(member => {
          const isDummy =
            member.email === 'demo@example.com' ||
            member.email === 'N/A' ||
            !member.email ||
            member.firstName === 'Demo' ||
            (member.email && member.email.includes('example.com'));
          return !isDummy;
        });

        // Save cleaned data back
        if (realMembers.length !== members.length) {
          localStorage.setItem('teamMembers', JSON.stringify(realMembers));
        }

        setTeamMembers(realMembers);
      } else {
        // Initialize with empty array
        setTeamMembers([]);
      }
    } catch (error) {
      console.error('Failed to load team members:', error);
      setTeamMembers([]);
    } finally {
      setLoading(false);
    }
  };

  const loadRoles = () => {
    try {
      const storedRoles = localStorage.getItem('availableRoles');
      if (storedRoles) {
        setAvailableRoles(JSON.parse(storedRoles));
      } else {
        // Save default roles to localStorage
        localStorage.setItem('availableRoles', JSON.stringify(DEFAULT_ROLES));
      }
    } catch (error) {
      console.error('Failed to load roles:', error);
      setAvailableRoles(DEFAULT_ROLES);
    }
  };

  const saveTeamMembers = (members) => {
    localStorage.setItem('teamMembers', JSON.stringify(members));
    setTeamMembers(members);
  };

  const saveRoles = (roles) => {
    localStorage.setItem('availableRoles', JSON.stringify(roles));
    setAvailableRoles(roles);
  };

  const handleAddMember = (memberData) => {
    const newMember = {
      id: Date.now(),
      ...memberData,
      createdAt: new Date().toISOString()
    };
    const updatedMembers = [...teamMembers, newMember];
    saveTeamMembers(updatedMembers);
    setShowAddMemberModal(false);
  };

  const handleUpdateMember = (memberId, updates) => {
    const updatedMembers = teamMembers.map(member =>
      member.id === memberId ? { ...member, ...updates } : member
    );
    saveTeamMembers(updatedMembers);
    setEditingMember(null);
  };

  const handleDeleteMember = (memberId) => {
    if (!window.confirm('Are you sure you want to remove this team member?')) return;
    const updatedMembers = teamMembers.filter(member => member.id !== memberId);
    saveTeamMembers(updatedMembers);
  };

  const handleAddRole = (roleName) => {
    const newRole = {
      id: Date.now(),
      name: roleName,
      taskCount: 0
    };
    const updatedRoles = [...availableRoles, newRole];
    saveRoles(updatedRoles);
    setShowAddRoleModal(false);
  };

  const handleDeleteRole = (roleId) => {
    if (!window.confirm('Are you sure you want to delete this role?')) return;
    const updatedRoles = availableRoles.filter(role => role.id !== roleId);
    saveRoles(updatedRoles);
  };

  const handleClearAllMembers = () => {
    if (!window.confirm('Are you sure you want to remove all team members? This cannot be undone.')) return;
    saveTeamMembers([]);
  };

  if (loading) {
    return <div className="users-page"><div className="loading">Loading team members...</div></div>;
  }

  return (
    <div className="users-page">
      <div className="page-header">
        <div>
          <h1>Team Members</h1>
          <p>Manage your team members and their role assignments</p>
        </div>
      </div>

      {/* Available Roles Section */}
      <div className="roles-section">
        <div className="section-header">
          <h2>Available Roles</h2>
          <button className="btn-add-role" onClick={() => setShowAddRoleModal(true)}>
            + Add Role
          </button>
        </div>
        <div className="roles-grid">
          {availableRoles.map(role => (
            <div key={role.id} className="role-card">
              <div className="role-header">
                <h3>{role.name}</h3>
                <button
                  className="btn-delete-role"
                  onClick={() => handleDeleteRole(role.id)}
                  title="Delete role"
                >
                  ×
                </button>
              </div>
              <p className="role-tasks">{role.taskCount} tasks</p>
              <p className="role-description">
                {role.name === 'Loan Officer' && 'Assist customers in selecting and applying for a mortgage loan and initial document...'}
                {role.name === 'Loan Processor' && 'Verify information on mortgage applications and ensure all necessary documents are...'}
                {role.name === 'Underwriter' && 'Assess risk of loan applications and decide on approval or denial.'}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Team Members Section */}
      <div className="team-members-section">
        <div className="section-header">
          <h2>Team Members ({teamMembers.length})</h2>
          <div className="header-actions">
            <button className="btn-add-member" onClick={() => setShowAddMemberModal(true)}>
              + Add Team Member
            </button>
            {teamMembers.length > 0 && (
              <button className="btn-clear-all" onClick={handleClearAllMembers}>
                Clear All
              </button>
            )}
          </div>
        </div>

        <div className="members-grid">
          {teamMembers.map(member => (
            <div key={member.id} className="member-card">
              <div className="member-avatar">
                {(member.firstName?.[0] || '') + (member.lastName?.[0] || '')}
              </div>
              <div className="member-info">
                <h3>{member.firstName} {member.lastName}</h3>
                <p className="member-email">{member.email}</p>
                {member.role && (
                  <span className="role-badge-small">
                    Role: {member.role}
                  </span>
                )}
              </div>
              <div className="member-actions">
                <button
                  className="btn-view-profile"
                  onClick={() => setEditingMember(member)}
                >
                  View Profile →
                </button>
              </div>
            </div>
          ))}
        </div>

        {teamMembers.length === 0 && (
          <div className="empty-state">
            <p>No team members found. Add your first team member to get started.</p>
          </div>
        )}
      </div>

      {/* Add Role Modal */}
      {showAddRoleModal && (
        <AddRoleModal
          onClose={() => setShowAddRoleModal(false)}
          onAdd={handleAddRole}
        />
      )}

      {/* Add Member Modal */}
      {showAddMemberModal && (
        <AddMemberModal
          onClose={() => setShowAddMemberModal(false)}
          onAdd={handleAddMember}
          availableRoles={availableRoles}
        />
      )}

      {/* Edit Member Modal */}
      {editingMember && (
        <EditMemberModal
          member={editingMember}
          onClose={() => setEditingMember(null)}
          onUpdate={handleUpdateMember}
          onDelete={handleDeleteMember}
          availableRoles={availableRoles}
        />
      )}
    </div>
  );
}

// Add Role Modal Component
function AddRoleModal({ onClose, onAdd }) {
  const [roleName, setRoleName] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (roleName.trim()) {
      onAdd(roleName.trim());
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content small-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Add New Role</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Role Name *</label>
            <input
              type="text"
              value={roleName}
              onChange={(e) => setRoleName(e.target.value)}
              placeholder="e.g., Junior Loan Officer"
              required
              autoFocus
            />
          </div>
          <div className="form-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Add Role</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Add Member Modal Component
function AddMemberModal({ onClose, onAdd, availableRoles }) {
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    role: ''
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onAdd(formData);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>Add Team Member</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label>First Name *</label>
              <input
                type="text"
                value={formData.firstName}
                onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Last Name *</label>
              <input
                type="text"
                value={formData.lastName}
                onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
                required
              />
            </div>
          </div>
          <div className="form-group">
            <label>Email *</label>
            <input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
            />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Role</label>
            <select
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
            >
              <option value="">Select Role</option>
              {availableRoles.map(role => (
                <option key={role.id} value={role.name}>{role.name}</option>
              ))}
            </select>
          </div>
          <div className="form-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Add Member</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Edit Member Modal Component
function EditMemberModal({ member, onClose, onUpdate, onDelete, availableRoles }) {
  const [formData, setFormData] = useState({
    firstName: member.firstName || '',
    lastName: member.lastName || '',
    email: member.email || '',
    phone: member.phone || '',
    role: member.role || ''
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onUpdate(member.id, formData);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>Edit Team Member</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label>First Name *</label>
              <input
                type="text"
                value={formData.firstName}
                onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Last Name *</label>
              <input
                type="text"
                value={formData.lastName}
                onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
                required
              />
            </div>
          </div>
          <div className="form-group">
            <label>Email *</label>
            <input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
            />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Role</label>
            <select
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
            >
              <option value="">Select Role</option>
              {availableRoles.map(role => (
                <option key={role.id} value={role.name}>{role.name}</option>
              ))}
            </select>
          </div>
          <div className="form-actions">
            <button
              type="button"
              className="btn-delete"
              onClick={() => {
                onDelete(member.id);
                onClose();
              }}
            >
              Delete Member
            </button>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button type="button" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn-primary">Save Changes</button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Users;
