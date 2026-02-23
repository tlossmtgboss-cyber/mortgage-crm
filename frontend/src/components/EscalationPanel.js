import React, { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../services/api';
import './EscalationPanel.css';

function EscalationPanel() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [teamMembers, setTeamMembers] = useState([]);
  const [selectedMember, setSelectedMember] = useState('');
  const [borrowerSearch, setBorrowerSearch] = useState('');
  const [borrowerSuggestions, setBorrowerSuggestions] = useState([]);
  const [selectedBorrower, setSelectedBorrower] = useState(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [message, setMessage] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const suggestionsRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    loadTeamMembers();
  }, []);

  useEffect(() => {
    // Handle click outside to close suggestions
    function handleClickOutside(event) {
      if (suggestionsRef.current && !suggestionsRef.current.contains(event.target)) {
        setShowSuggestions(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  useEffect(() => {
    // Search for borrowers when user types
    const searchBorrowers = async () => {
      if (borrowerSearch.trim().length < 2) {
        setBorrowerSuggestions([]);
        setShowSuggestions(false);
        return;
      }

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/leads/search?q=${encodeURIComponent(borrowerSearch)}&limit=10`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
          },
        });

        if (response.ok) {
          const data = await response.json();
          setBorrowerSuggestions(data.leads || data || []);
          setShowSuggestions(true);
        }
      } catch (error) {
        console.error('Error searching borrowers:', error);
      }
    };

    const debounceTimer = setTimeout(searchBorrowers, 300);
    return () => clearTimeout(debounceTimer);
  }, [borrowerSearch]);

  const loadTeamMembers = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/team/members`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
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

  const handleBorrowerSelect = (borrower) => {
    setSelectedBorrower(borrower);
    setBorrowerSearch(`${borrower.name} - Loan #${borrower.loan_number || borrower.id}`);
    setShowSuggestions(false);
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

    if (!selectedBorrower) {
      setErrorMessage('Please select a borrower');
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
      formData.append('lead_id', selectedBorrower.id);
      formData.append('loan_number', selectedBorrower.loan_number || '');
      formData.append('borrower_name', selectedBorrower.name);
      formData.append('message', message);
      formData.append('priority', 'high');

      // Add attachments
      attachments.forEach((file) => {
        formData.append('attachments', file);
      });

      const response = await fetch(`${API_BASE_URL}/api/v1/escalations`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to create escalation');
      }

      const data = await response.json();

      // Success - clear form
      setSuccessMessage('Escalation sent successfully!');
      setSelectedMember('');
      setSelectedBorrower(null);
      setBorrowerSearch('');
      setMessage('');
      setAttachments([]);

      setTimeout(() => {
        setSuccessMessage('');
        setIsExpanded(false);
      }, 2000);

    } catch (error) {
      console.error('Error creating escalation:', error);
      setErrorMessage('Failed to send escalation. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="escalation-panel">
      <div
        className="escalation-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="escalation-title">
          <span className="escalation-icon">🚨</span>
          <span>Escalate Issue</span>
        </div>
        <span className={`expand-arrow ${isExpanded ? 'expanded' : ''}`}>
          ▼
        </span>
      </div>

      {isExpanded && (
        <form onSubmit={handleSubmit} className="escalation-content">
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

          {/* Borrower Search */}
          <div className="form-group">
            <label className="form-label">Borrower / Loan *</label>
            <div className="autocomplete-container" ref={suggestionsRef}>
              <input
                type="text"
                className="form-input"
                placeholder="Start typing borrower name..."
                value={borrowerSearch}
                onChange={(e) => {
                  setBorrowerSearch(e.target.value);
                  if (!e.target.value.trim()) {
                    setSelectedBorrower(null);
                  }
                }}
                onFocus={() => borrowerSuggestions.length > 0 && setShowSuggestions(true)}
                required
              />

              {showSuggestions && borrowerSuggestions.length > 0 && (
                <div className="autocomplete-suggestions">
                  {borrowerSuggestions.map((borrower) => (
                    <div
                      key={borrower.id}
                      className="suggestion-item"
                      onClick={() => handleBorrowerSelect(borrower)}
                    >
                      <div className="suggestion-name">{borrower.name}</div>
                      <div className="suggestion-loan">
                        Loan #{borrower.loan_number || borrower.id}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
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
          <button
            type="submit"
            className="escalate-submit-button"
            disabled={isSubmitting || !selectedMember || !selectedBorrower || !message.trim()}
          >
            {isSubmitting ? 'Sending...' : '🚨 Send Escalation'}
          </button>
        </form>
      )}
    </div>
  );
}

export default EscalationPanel;
