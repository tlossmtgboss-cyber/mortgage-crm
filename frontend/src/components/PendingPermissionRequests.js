import React, { useState, useEffect } from 'react';
import { permissionsApi } from '../services/api';
import './PendingPermissionRequests.css';

const PendingPermissionRequests = () => {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState(null);
  const [showApproveModal, setShowApproveModal] = useState(null);
  const [showDenyModal, setShowDenyModal] = useState(null);
  const [approveNotes, setApproveNotes] = useState('');
  const [denyReason, setDenyReason] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    loadRequests();
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadRequests, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadRequests = async () => {
    try {
      setError(null);
      const response = await permissionsApi.getMyPermissionRequests('pending');
      setRequests(response.data.requests || []);
    } catch (err) {
      console.error('Error loading permission requests:', err);
      setError('Failed to load requests');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (requestId) => {
    try {
      setProcessingId(requestId);
      setError(null);

      await permissionsApi.approvePermissionRequest(requestId, approveNotes);

      // Remove from list and reset
      setRequests(requests.filter(r => r.id !== requestId));
      setShowApproveModal(null);
      setApproveNotes('');
    } catch (err) {
      console.error('Error approving request:', err);
      setError(err.response?.data?.detail || 'Failed to approve request');
    } finally {
      setProcessingId(null);
    }
  };

  const handleDeny = async (requestId) => {
    if (!denyReason.trim()) {
      setError('Please provide a reason for denying this request');
      return;
    }

    try {
      setProcessingId(requestId);
      setError(null);

      await permissionsApi.denyPermissionRequest(requestId, denyReason);

      // Remove from list and reset
      setRequests(requests.filter(r => r.id !== requestId));
      setShowDenyModal(null);
      setDenyReason('');
    } catch (err) {
      console.error('Error denying request:', err);
      setError(err.response?.data?.detail || 'Failed to deny request');
    } finally {
      setProcessingId(null);
    }
  };

  const getUrgencyClass = (urgency) => {
    const map = {
      'low': 'urgency-low',
      'medium': 'urgency-medium',
      'high': 'urgency-high'
    };
    return map[urgency] || 'urgency-medium';
  };

  if (loading) {
    return (
      <div className="pending-permissions-widget">
        <div className="widget-header">
          <h3>Pending Permission Requests</h3>
        </div>
        <div className="widget-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="pending-permissions-widget">
      <div className="widget-header">
        <h3>Pending Permission Requests</h3>
        {requests.length > 0 && (
          <span className="request-count">{requests.length}</span>
        )}
      </div>

      {error && (
        <div className="widget-error">
          {error}
          <button onClick={() => setError(null)} className="dismiss-btn">&times;</button>
        </div>
      )}

      {requests.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">✓</div>
          <p>No pending permission requests</p>
          <small>All caught up!</small>
        </div>
      ) : (
        <div className="requests-list">
          {requests.map(request => (
            <div key={request.id} className="request-card">
              <div className="request-header">
                <div className="employee-info">
                  <strong>{request.employee_name || request.employee_email}</strong>
                  <span className="request-date">
                    {new Date(request.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div className="badges">
                  <span className={`urgency-badge ${getUrgencyClass(request.urgency)}`}>
                    {request.urgency}
                  </span>
                  {request.is_temporary && (
                    <span className="temp-badge">
                      Temp ({request.duration_days}d)
                    </span>
                  )}
                </div>
              </div>

              <div className="permission-requested">
                <div className="permission-name">{request.permission_key}</div>
              </div>

              <div className="justification">
                <strong>Justification:</strong>
                <p>{request.justification}</p>
              </div>

              <div className="request-actions">
                <button
                  onClick={() => setShowDenyModal(request.id)}
                  className="btn-deny"
                  disabled={processingId === request.id}
                >
                  Deny
                </button>
                <button
                  onClick={() => setShowApproveModal(request.id)}
                  className="btn-approve"
                  disabled={processingId === request.id}
                >
                  {processingId === request.id ? 'Processing...' : 'Approve'}
                </button>
              </div>

              {/* Inline Approve Modal */}
              {showApproveModal === request.id && (
                <div className="inline-modal">
                  <div className="inline-modal-content">
                    <h4>Approve Permission Request</h4>
                    <p>Approving will immediately grant <strong>{request.permission_key}</strong> to {request.employee_name}.</p>
                    <div className="form-group">
                      <label>Notes (optional)</label>
                      <textarea
                        value={approveNotes}
                        onChange={(e) => setApproveNotes(e.target.value)}
                        placeholder="Add any notes about this approval..."
                        rows={2}
                      />
                    </div>
                    <div className="inline-modal-actions">
                      <button onClick={() => {
                        setShowApproveModal(null);
                        setApproveNotes('');
                      }} className="btn-cancel">
                        Cancel
                      </button>
                      <button onClick={() => handleApprove(request.id)} className="btn-confirm-approve">
                        Confirm Approval
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Inline Deny Modal */}
              {showDenyModal === request.id && (
                <div className="inline-modal">
                  <div className="inline-modal-content">
                    <h4>Deny Permission Request</h4>
                    <p>Please provide a reason for denying this request.</p>
                    <div className="form-group">
                      <label>Reason *</label>
                      <textarea
                        value={denyReason}
                        onChange={(e) => setDenyReason(e.target.value)}
                        placeholder="Explain why this request is being denied..."
                        rows={3}
                        required
                      />
                    </div>
                    <div className="inline-modal-actions">
                      <button onClick={() => {
                        setShowDenyModal(null);
                        setDenyReason('');
                      }} className="btn-cancel">
                        Cancel
                      </button>
                      <button onClick={() => handleDeny(request.id)} className="btn-confirm-deny">
                        Confirm Denial
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default PendingPermissionRequests;
