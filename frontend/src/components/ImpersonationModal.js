import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { impersonationAPI } from '../services/api';
import { useImpersonation } from '../contexts/ImpersonationContext';
import './ImpersonationModal.css';

function ImpersonationModal({ employee, onClose }) {
  const navigate = useNavigate();
  const { startImpersonation } = useImpersonation();
  const [mode, setMode] = useState('read_only');
  const [reason, setReason] = useState('');
  const [duration, setDuration] = useState(60);
  const [notifyEmployee, setNotifyEmployee] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleStart = async () => {
    if (!reason) {
      setError('Please select a reason');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await impersonationAPI.start({
        user_id: employee.id,
        mode,
        reason,
        duration_minutes: duration,
        notify_employee: notifyEmployee
      });

      // Store impersonation data in context
      startImpersonation(response);

      // Close modal
      onClose();

      // Redirect to dashboard
      navigate('/dashboard');
    } catch (err) {
      console.error('Failed to start impersonation:', err);
      setError(err.response?.data?.detail || 'Failed to start impersonation session');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="impersonation-modal-overlay" onClick={onClose}>
      <div className="impersonation-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Impersonate Employee</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          <div className="employee-info">
            <div className="employee-avatar">
              {employee?.photo_url ? (
                <img src={employee.photo_url} alt={employee?.full_name || 'Employee'} />
              ) : (
                <span className="initials">
                  {employee?.first_name?.[0]}{employee?.last_name?.[0]}
                </span>
              )}
            </div>
            <div className="employee-details">
              <h3>{employee.first_name} {employee.last_name}</h3>
              <p className="role">{employee.role}</p>
            </div>
          </div>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <div className="form-section">
            <label>Access Mode</label>
            <div className="radio-group">
              <label className="radio-option">
                <input
                  type="radio"
                  value="read_only"
                  checked={mode === 'read_only'}
                  onChange={(e) => setMode(e.target.value)}
                />
                <div className="radio-content">
                  <strong>Read-Only</strong>
                  <span>View data only, no modifications allowed</span>
                </div>
              </label>
              <label className="radio-option">
                <input
                  type="radio"
                  value="full_access"
                  checked={mode === 'full_access'}
                  onChange={(e) => setMode(e.target.value)}
                />
                <div className="radio-content">
                  <strong>Full Access</strong>
                  <span>Can view and modify data as this employee</span>
                </div>
              </label>
            </div>
          </div>

          <div className="form-section">
            <label htmlFor="reason">Reason</label>
            <select
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="form-select"
            >
              <option value="">Select a reason...</option>
              <option value="Training">Training</option>
              <option value="Troubleshooting">Troubleshooting</option>
              <option value="Performance Review">Performance Review</option>
              <option value="QA">Quality Assurance</option>
              <option value="Other">Other</option>
            </select>
          </div>

          <div className="form-section">
            <label htmlFor="duration">Session Duration</label>
            <select
              id="duration"
              value={duration}
              onChange={(e) => setDuration(parseInt(e.target.value))}
              className="form-select"
            >
              <option value={30}>30 minutes</option>
              <option value={60}>1 hour</option>
              <option value={120}>2 hours</option>
              <option value={240}>4 hours</option>
            </select>
          </div>

          <div className="form-section">
            <label className="checkbox-option">
              <input
                type="checkbox"
                checked={notifyEmployee}
                onChange={(e) => setNotifyEmployee(e.target.checked)}
              />
              <span>Notify employee about this impersonation session</span>
            </label>
          </div>

          <div className="warning-box">
            <strong>Important:</strong> All actions taken during this session will be logged and auditable.
            You will see the CRM exactly as this employee would see it, with their permissions and data access.
          </div>
        </div>

        <div className="modal-footer">
          <button
            className="btn-cancel"
            onClick={onClose}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            className="btn-start"
            onClick={handleStart}
            disabled={loading || !reason}
          >
            {loading ? 'Starting...' : 'Start Impersonation'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ImpersonationModal;
