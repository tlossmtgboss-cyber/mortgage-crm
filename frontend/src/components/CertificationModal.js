import React, { useState, useEffect } from 'react';
import './CertificationModal.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

const CertificationModal = ({ certificationId, onClose, onComplete }) => {
  const [cert, setCert] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState('');
  const [permissionsToRevoke, setPermissionsToRevoke] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadCertification();
  }, [certificationId]);

  const loadCertification = async () => {
    try {
      setLoading(true);
      const token = getToken();
      const response = await fetch(
        `https://api.perenniaai.com/api/v1/certifications/${certificationId}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setCert(data);
      } else {
        toast.error('Failed to load certification');
        onClose();
      }
    } catch (err) {
      console.error('Error loading certification:', err);
      toast.error('Failed to load certification');
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const togglePermissionRevoke = (permKey) => {
    setPermissionsToRevoke(prev =>
      prev.includes(permKey)
        ? prev.filter(p => p !== permKey)
        : [...prev, permKey]
    );
  };

  const handleCertify = async () => {
    setSubmitting(true);
    try {
      const token = getToken();
      const response = await fetch(
        `https://api.perenniaai.com/api/v1/certifications/${certificationId}/certify`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            notes,
            permissions_to_revoke: permissionsToRevoke
          })
        }
      );

      if (response.ok) {
        onComplete();
      } else {
        toast.error('Failed to certify access');
      }
    } catch (err) {
      toast.error('Failed to certify access');
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkip = async () => {
    const reason = prompt('Reason for skipping certification (required):');
    if (!reason) return;

    setSubmitting(true);
    try {
      const token = getToken();
      const response = await fetch(
        `https://api.perenniaai.com/api/v1/certifications/${certificationId}/skip`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ reason })
        }
      );

      if (response.ok) {
        onComplete();
      } else {
        toast.error('Failed to skip certification');
      }
    } catch (err) {
      toast.error('Failed to skip certification');
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="loading">Loading certification...</div>
        </div>
      </div>
    );
  }

  const changedPermissions = cert.permissions_changed_since_snapshot || {};
  const hasChanges = changedPermissions.added?.length > 0 || changedPermissions.removed?.length > 0;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content certification-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Access Certification</h3>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <div className="employee-info">
          <h4>{cert.employee.name}</h4>
          <p>Role: {cert.employee.role} | Period: {cert.certification_period}</p>
          <p className={cert.status === 'overdue' ? 'overdue-warning' : ''}>
            Due: {new Date(cert.due_date).toLocaleDateString()}
            {cert.status === 'overdue' && ' (OVERDUE)'}
          </p>
        </div>

        {hasChanges && (
          <div className="changes-alert">
            <strong>⚠️ Permissions have changed since last certification:</strong>
            {changedPermissions.added?.length > 0 && (
              <div className="added-perms">
                <strong>Added ({changedPermissions.added.length}):</strong>
                <ul>
                  {changedPermissions.added.map(p => <li key={p}>{p}</li>)}
                </ul>
              </div>
            )}
            {changedPermissions.removed?.length > 0 && (
              <div className="removed-perms">
                <strong>Removed ({changedPermissions.removed.length}):</strong>
                <ul>
                  {changedPermissions.removed.map(p => <li key={p}>{p}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="current-permissions">
          <h4>Current Permissions ({Object.keys(cert.current_permissions).length})</h4>
          <p className="instructions">
            Review all permissions. Check any you want to revoke during certification.
          </p>

          <div className="permissions-list">
            {Object.entries(cert.current_permissions).map(([key, perm]) => (
              <label key={key} className="permission-item">
                <input
                  type="checkbox"
                  checked={permissionsToRevoke.includes(key)}
                  onChange={() => togglePermissionRevoke(key)}
                />
                <div className="permission-info">
                  <strong>{key}</strong>
                  {perm.description && <p>{perm.description}</p>}
                  {perm.is_temporary && <span className="temp-badge">Temporary</span>}
                </div>
              </label>
            ))}
          </div>
        </div>

        <div className="certification-notes">
          <label>Certification Notes:</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            placeholder="Add any notes about this certification review..."
          />
        </div>

        {permissionsToRevoke.length > 0 && (
          <div className="revoke-warning">
            <strong>⚠️ You are about to revoke {permissionsToRevoke.length} permission(s):</strong>
            <ul>
              {permissionsToRevoke.map(p => <li key={p}>{p}</li>)}
            </ul>
            <p>The employee will be notified of revoked permissions.</p>
          </div>
        )}

        <div className="modal-actions">
          <button onClick={handleSkip} className="btn-skip" disabled={submitting}>
            Skip (Requires Escalation)
          </button>
          <button onClick={onClose} className="btn-secondary" disabled={submitting}>
            Cancel
          </button>
          <button onClick={handleCertify} className="btn-primary" disabled={submitting}>
            {submitting ? 'Certifying...' : 'Certify Access'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CertificationModal;
