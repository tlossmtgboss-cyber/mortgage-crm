import React, { useState } from 'react';
import { permissionsApi } from '../services/api';
import './PermissionRequestModal.css';

const PermissionRequestModal = ({
  availablePermissions,
  allPermissions,
  pendingRequests,
  onClose,
  onSubmit
}) => {
  const [selectedPermission, setSelectedPermission] = useState('');
  const [justification, setJustification] = useState('');
  const [urgency, setUrgency] = useState('medium');
  const [isTemporary, setIsTemporary] = useState(false);
  const [durationDays, setDurationDays] = useState(30);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const hasPendingRequest = (permKey) => {
    return pendingRequests.some(r => r.permission_key === permKey && r.status === 'pending');
  };

  const getPermissionsByCategory = () => {
    const categories = {};
    availablePermissions.forEach(([key, info]) => {
      const category = info.category || 'Other';
      if (!categories[category]) {
        categories[category] = [];
      }
      categories[category].push({ key, ...info });
    });
    return categories;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!selectedPermission) {
      setError('Please select a permission');
      return;
    }

    if (justification.length < 50) {
      setError('Justification must be at least 50 characters');
      return;
    }

    if (isTemporary && (!durationDays || durationDays < 1)) {
      setError('Please specify a valid duration for temporary access');
      return;
    }

    try {
      setSubmitting(true);

      await permissionsApi.createPermissionRequest({
        permission_key: selectedPermission,
        justification,
        urgency,
        is_temporary: isTemporary,
        duration_days: isTemporary ? durationDays : null
      });

      // Reset form and notify parent
      setSelectedPermission('');
      setJustification('');
      setUrgency('medium');
      setIsTemporary(false);
      setDurationDays(30);

      onSubmit();
    } catch (err) {
      console.error('Error submitting request:', err);
      setError(err.response?.data?.detail || 'Failed to submit request. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const permissionsByCategory = getPermissionsByCategory();
  const selectedPermInfo = selectedPermission ? allPermissions[selectedPermission] : null;

  const urgencyOptions = [
    { value: 'low', label: 'Low', description: 'Can wait a few days' },
    { value: 'medium', label: 'Medium', description: 'Needed this week' },
    { value: 'high', label: 'High', description: 'Needed ASAP' }
  ];

  return (
    <div className="permission-request-modal-overlay" onClick={onClose}>
      <div className="permission-request-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="permission-request-modal-header">
          <h2>Request Permission</h2>
          <button className="close-btn" onClick={onClose} aria-label="Close">&times;</button>
        </div>

        {error && (
          <div className="permission-request-error">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="permission-request-form">
          {/* Permission Selection */}
          <div className="form-group">
            <label htmlFor="permission-select">
              Permission <span className="required">*</span>
            </label>
            <select
              id="permission-select"
              value={selectedPermission}
              onChange={(e) => setSelectedPermission(e.target.value)}
              required
              className="permission-select"
            >
              <option value="">Select a permission...</option>
              {Object.entries(permissionsByCategory).map(([category, perms]) => (
                <optgroup key={category} label={category}>
                  {perms.map(perm => (
                    <option
                      key={perm.key}
                      value={perm.key}
                      disabled={hasPendingRequest(perm.key)}
                    >
                      {perm.name || perm.key} {hasPendingRequest(perm.key) ? '(Pending)' : ''}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          {/* Permission Description */}
          {selectedPermInfo && (
            <div className="permission-description-box">
              <div className="permission-description-header">
                <strong>{selectedPermInfo.name || selectedPermission}</strong>
              </div>
              <p>{selectedPermInfo.description || 'No description available'}</p>
            </div>
          )}

          {/* Business Justification */}
          <div className="form-group">
            <label htmlFor="justification">
              Business Justification <span className="required">*</span>
            </label>
            <textarea
              id="justification"
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              placeholder="Explain why you need this permission and how it will help you do your job more effectively..."
              rows={5}
              required
              minLength={50}
              className={justification.length > 0 && justification.length < 50 ? 'invalid' : ''}
            />
            <div className="char-counter">
              <span className={justification.length < 50 ? 'insufficient' : 'sufficient'}>
                {justification.length}/50 characters {justification.length < 50 && '(minimum)'}
              </span>
            </div>
          </div>

          {/* Urgency Level */}
          <div className="form-group">
            <label>Urgency Level <span className="required">*</span></label>
            <div className="urgency-options">
              {urgencyOptions.map(option => (
                <label key={option.value} className={`urgency-option ${urgency === option.value ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="urgency"
                    value={option.value}
                    checked={urgency === option.value}
                    onChange={(e) => setUrgency(e.target.value)}
                  />
                  <div className="urgency-option-content">
                    <div className="urgency-label">{option.label}</div>
                    <div className="urgency-description">{option.description}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Temporary Access */}
          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={isTemporary}
                onChange={(e) => setIsTemporary(e.target.checked)}
              />
              <span>This is temporary access</span>
            </label>
            <p className="help-text">Check this if you only need this permission for a limited time</p>
          </div>

          {/* Duration (shown only if temporary) */}
          {isTemporary && (
            <div className="form-group duration-group">
              <label htmlFor="duration">
                Duration (days) <span className="required">*</span>
              </label>
              <input
                id="duration"
                type="number"
                value={durationDays}
                onChange={(e) => setDurationDays(parseInt(e.target.value))}
                min={1}
                max={365}
                required
                className="duration-input"
              />
              <p className="help-text">
                Access will automatically expire after {durationDays} day{durationDays !== 1 ? 's' : ''}
              </p>
            </div>
          )}

          {/* Form Actions */}
          <div className="permission-request-modal-actions">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary"
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={submitting || justification.length < 50}
            >
              {submitting ? 'Submitting...' : 'Submit Request'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default PermissionRequestModal;
