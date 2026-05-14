import React from 'react';

export const HelpdeskModal = ({ helpdeskModal, formData, onClose, onSubmit }) => {
  if (!helpdeskModal) return null;

  return (
    <div className="connection-modal-overlay" onClick={onClose}>
      <div className="connection-modal helpdesk-modal" onClick={(e) => e.stopPropagation()}>
        <button className="btn-close-modal" onClick={onClose}>×</button>

        <div className="modal-header">
          <span className="modal-icon">🎫</span>
          <h3>Submit Support Ticket</h3>
          <p className="modal-description">Feature Not Yet Available</p>
        </div>

        <div className="modal-body">
          <div className="helpdesk-notice">
            <div className="notice-icon">ℹ️</div>
            <div className="notice-content">
              <h4>{helpdeskModal.feature}</h4>
              <p>{helpdeskModal.message}</p>
            </div>
          </div>

          <form className="helpdesk-form" onSubmit={onSubmit}>
            <div className="form-field">
              <label>Your Name</label>
              <input type="text" className="input-field" placeholder="Full name" required
                defaultValue={`${formData.members[0]?.firstName || ''} ${formData.members[0]?.lastName || ''}`.trim()} />
            </div>
            <div className="form-field">
              <label>Email Address</label>
              <input type="email" className="input-field" placeholder="your@email.com" required
                defaultValue={formData.members[0]?.email || ''} />
            </div>
            <div className="form-field">
              <label>Phone Number (Optional)</label>
              <input type="tel" className="input-field" placeholder="(555) 123-4567"
                defaultValue={formData.members[0]?.phone || ''} />
            </div>
            <div className="form-field">
              <label>Issue Type</label>
              <select className="input-field" required>
                <option value="setup">Setup Assistance</option>
                <option value="bug">Report a Bug</option>
                <option value="feature">Feature Request</option>
                <option value="integration">Integration Help</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="form-field">
              <label>Additional Details</label>
              <textarea className="textarea-field" placeholder="Please describe what you need help with..." rows="4"
                defaultValue={`I need help setting up: ${helpdeskModal.feature}`}></textarea>
            </div>
            <div className="helpdesk-actions">
              <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn-submit-ticket">Submit Ticket</button>
            </div>
          </form>

          <div className="support-info">
            <p className="support-note">📧 You can also email us at <strong>support@perenniaai.com</strong></p>
            <p className="support-note">⏱️ Average response time: <strong>2-4 hours</strong></p>
          </div>
        </div>
      </div>
    </div>
  );
};

export const ConnectionModal = ({ connectionModal, onClose, onAuthComplete }) => {
  if (!connectionModal) return null;

  const permissionsByCategory = {
    Email: ['Read emails and attachments', 'Send emails on your behalf', 'Access contact information'],
    Calendar: ['View and create calendar events', 'Send meeting invitations', 'Access availability information'],
    Phone: ['Make and receive calls', 'Send and receive SMS messages', 'Access call history and recordings'],
    Documents: ['Upload and download documents', 'Create and modify files', 'Share documents with clients'],
    LOS: ['Read loan application data', 'Update loan statuses', 'Sync borrower information'],
    CRM: ['Read and write contact data', 'Create and update leads', 'Sync pipeline information'],
    Credit: ['Pull credit reports', 'View credit scores', 'Access credit history'],
    Communication: ['Send messages to channels', 'Create notifications', 'Access team information'],
    Accounting: ['Read transaction data', 'Create invoices', 'Sync financial records']
  };

  const permissions = permissionsByCategory[connectionModal.category] || [];

  return (
    <div className="connection-modal-overlay" onClick={onClose}>
      <div className="connection-modal" onClick={(e) => e.stopPropagation()}>
        <button className="btn-close-modal" onClick={onClose}>×</button>

        <div className="modal-header">
          <span className="modal-icon">{connectionModal.icon}</span>
          <h3>Connect to {connectionModal.name}</h3>
          <p className="modal-description">{connectionModal.description}</p>
        </div>

        <div className="modal-body">
          <div className="auth-form">
            <div className="auth-provider-logo">
              <span className="provider-logo-icon">{connectionModal.icon}</span>
              <h4>{connectionModal.name}</h4>
            </div>

            <p className="auth-instruction">
              Sign in to your {connectionModal.name} account to authorize access
            </p>

            <form className="oauth-form" onSubmit={(e) => { e.preventDefault(); onAuthComplete(); }}>
              <div className="form-field">
                <label>Email or Username</label>
                <input type="text" className="input-field" placeholder={`Your ${connectionModal.name} email`} autoFocus />
              </div>
              <div className="form-field">
                <label>Password</label>
                <input type="password" className="input-field" placeholder="Password" />
              </div>
              <button type="submit" className="btn-authorize">Authorize Connection</button>
            </form>

            <div className="auth-footer">
              <p className="security-note">
                🔒 Your credentials are encrypted and securely stored. We only access data necessary for the integration.
              </p>
              <div className="permissions-info">
                <p className="permissions-title">This integration will be able to:</p>
                <ul className="permissions-list">
                  {permissions.map((perm, idx) => (
                    <li key={idx}>{perm}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const TaskEditModal = ({
  taskEditModal, formData, teamMembers,
  onClose, onSave, onUpdateField
}) => {
  if (!taskEditModal) return null;

  return (
    <div className="connection-modal-overlay" onClick={onClose}>
      <div className="connection-modal task-edit-modal" onClick={(e) => e.stopPropagation()}>
        <button className="btn-close-modal" onClick={onClose}>×</button>

        <div className="modal-header">
          <span className="modal-icon">📋</span>
          <h3>Edit Task</h3>
          <p className="modal-description">Update task details and assignment</p>
        </div>

        <div className="modal-body">
          <div className="form-field">
            <label>Task Name</label>
            <input type="text" className="input-field"
              value={taskEditModal.task_name || ''}
              onChange={(e) => onUpdateField('task_name', e.target.value)} />
          </div>
          <div className="form-field">
            <label>Description</label>
            <textarea className="textarea-field" rows="3"
              value={taskEditModal.task_description || ''}
              onChange={(e) => onUpdateField('task_description', e.target.value)} />
          </div>
          <div className="form-field">
            <label>Assigned Role</label>
            <select className="input-field"
              value={taskEditModal.tempRoleId || ''}
              onChange={(e) => onUpdateField('tempRoleId', e.target.value)}>
              <option value="">Select Role</option>
              {formData.extractedRoles?.map(role => (
                <option key={role.id} value={role.id}>{role.role_title}</option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label>Assigned User (Optional)</label>
            <select className="input-field"
              value={taskEditModal.tempUserId || ''}
              onChange={(e) => onUpdateField('tempUserId', e.target.value ? parseInt(e.target.value) : null)}>
              <option value="">Select User</option>
              {teamMembers.map((member) => (
                <option key={member.id} value={member.id}>{member.full_name || member.email}</option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label>SLA</label>
              <input type="number" className="input-field"
                value={taskEditModal.sla || ''}
                onChange={(e) => onUpdateField('sla', parseInt(e.target.value) || 0)} min="1" />
            </div>
            <div className="form-field">
              <label>SLA Unit</label>
              <select className="input-field"
                value={taskEditModal.sla_unit || 'hours'}
                onChange={(e) => onUpdateField('sla_unit', e.target.value)}>
                <option value="hours">Hours</option>
                <option value="days">Days</option>
              </select>
            </div>
          </div>
          <div className="form-field">
            <label className="checkbox-label">
              <input type="checkbox"
                checked={taskEditModal.ai_automatable || false}
                onChange={(e) => onUpdateField('ai_automatable', e.target.checked)} />
              <span>AI Automatable</span>
            </label>
          </div>
          <div className="modal-actions">
            <button className="btn-cancel" onClick={onClose}>Cancel</button>
            <button className="btn-save" onClick={onSave}>Save Changes</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export const RoleAddModal = ({ roleAddModal, newRoleForm, setNewRoleForm, onClose, onSave }) => {
  if (!roleAddModal) return null;

  return (
    <div className="connection-modal-overlay" onClick={onClose}>
      <div className="connection-modal role-add-modal" onClick={(e) => e.stopPropagation()}>
        <button className="btn-close-modal" onClick={onClose}>×</button>

        <div className="modal-header">
          <span className="modal-icon">👥</span>
          <h3>Add New Role</h3>
          <p className="modal-description">Create a custom role for your team</p>
        </div>

        <div className="modal-body">
          <div className="form-field">
            <label>Role Title *</label>
            <input type="text" className="input-field" placeholder="e.g., Senior Loan Officer"
              value={newRoleForm.role_title}
              onChange={(e) => setNewRoleForm({ ...newRoleForm, role_title: e.target.value })} />
          </div>
          <div className="form-field">
            <label>Role Name (Internal) *</label>
            <input type="text" className="input-field" placeholder="e.g., senior_loan_officer"
              value={newRoleForm.role_name}
              onChange={(e) => setNewRoleForm({ ...newRoleForm, role_name: e.target.value })} />
          </div>
          <div className="form-field">
            <label>Responsibilities</label>
            <textarea className="textarea-field" rows="3" placeholder="Describe what this role is responsible for..."
              value={newRoleForm.responsibilities}
              onChange={(e) => setNewRoleForm({ ...newRoleForm, responsibilities: e.target.value })} />
          </div>
          <div className="modal-actions">
            <button className="btn-cancel" onClick={onClose}>Cancel</button>
            <button className="btn-save" onClick={onSave}>Add Role</button>
          </div>
        </div>
      </div>
    </div>
  );
};
