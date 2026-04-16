import React, { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../services/api';
import './EscalationModal.css';
import { getToken } from '../utils/tokenStore';

function EscalationModal({ isOpen, onClose, lead }) {
  const [teamMembers, setTeamMembers] = useState([]);
  const [selectedMember, setSelectedMember] = useState('');
  const [message, setMessage] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const fileInputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      loadTeamMembers();
    }
  }, [isOpen]);

  const loadTeamMembers = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/team/members`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setTeamMembers(data.team_members || data || []);
      }
    } catch (error) {
      console.error('Error loading team members:', error);
    }
  };

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    setAttachments(prev => [...prev, ...files]);
  };

  const removeAttachment = (index) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!selectedMember) {
      setErrorMessage('Please select a team member to escalate to');
      return;
    }

    if (!lead) {
      setErrorMessage('Lead information is missing');
      return;
    }

    if (!message.trim()) {
      setErrorMessage('Please enter a message');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage('');

    try {
      const formData = new FormData();
      formData.append('assigned_to_id', selectedMember);
      formData.append('lead_id', lead.id);
      formData.append('loan_number', lead.loan_number || '');
      formData.append('borrower_name', lead.name || lead.first_name || 'Unknown');
      formData.append('message', message);
      formData.append('priority', 'high');

      // Add attachments
      attachments.forEach((file) => {
        formData.append('attachments', file);
      });

      const response = await fetch(`${API_BASE_URL}/api/v1/escalations`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to create escalation');
      }

      // Success - clear form
      setSuccessMessage('Escalation sent successfully!');
      setSelectedMember('');
      setMessage('');
      setAttachments([]);

      setTimeout(() => {
        setSuccessMessage('');
        onClose();
      }, 2000);

    } catch (error) {
      console.error('Error creating escalation:', error);
      setErrorMessage('Failed to send escalation. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content escalation-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>🚨 Escalate Issue</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="escalation-modal-form">
          {/* Borrower Info */}
          <div className="borrower-info">
            <strong>Borrower:</strong> {lead?.name || lead?.first_name || 'Unknown'}
            {lead?.loan_number && <span> | Loan #{lead.loan_number}</span>}
          </div>

          {/* Escalate To */}
          <div className="form-group">
            <label className="form-label">Escalate To *</label>
            <select
              className="form-select"
              value={selectedMember}
              onChange={(e) => setSelectedMember(e.target.value)}
              required
            >
              <option value="">Select team member...</option>
              {teamMembers.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name || member.email} - {member.role || 'Team Member'}
                </option>
              ))}
            </select>
          </div>

          {/* Message */}
          <div className="form-group">
            <label className="form-label">Message *</label>
            <textarea
              className="form-textarea"
              placeholder="Describe the issue that needs to be escalated..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows="4"
              required
            />
          </div>

          {/* File Attachments */}
          <div className="form-group">
            <label className="form-label">Attachments</label>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              multiple
              style={{ display: 'none' }}
            />
            <button
              type="button"
              className="attach-button"
              onClick={() => fileInputRef.current?.click()}
            >
              📎 Add Documents
            </button>

            {attachments.length > 0 && (
              <div className="attachments-list">
                {attachments.map((file, index) => (
                  <div key={index} className="attachment-item">
                    <span className="attachment-name">📄 {file.name}</span>
                    <button
                      type="button"
                      className="remove-attachment"
                      onClick={() => removeAttachment(index)}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Messages */}
          {successMessage && (
            <div className="success-message">
              ✓ {successMessage}
            </div>
          )}

          {errorMessage && (
            <div className="error-message">
              ✕ {errorMessage}
            </div>
          )}

          {/* Submit Button */}
          <div className="modal-actions">
            <button
              type="button"
              className="cancel-button"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="escalate-submit-button"
              disabled={isSubmitting || !selectedMember || !message.trim()}
            >
              {isSubmitting ? 'Sending...' : '🚨 Send Escalation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default EscalationModal;
