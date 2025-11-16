import React, { useState, useEffect } from 'react';
import { getAuth } from '../utils/auth';
import { permissionsApi } from '../services/api';
import PermissionRequestModal from '../components/PermissionRequestModal';
import './MyPermissions.css';

const MyPermissions = () => {
  const { user } = getAuth();
  const [myPermissions, setMyPermissions] = useState({});
  const [allPermissions, setAllPermissions] = useState({});
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load current permissions, all available permissions, and my requests
      const [permsRes, allPermsRes, requestsRes] = await Promise.all([
        permissionsApi.getUserPermissions(user.id),
        permissionsApi.getAvailablePermissions(),
        permissionsApi.getMyPermissionRequests()
      ]);

      setMyPermissions(permsRes.data.permissions || {});
      setAllPermissions(allPermsRes.data.permissions || {});
      setRequests(requestsRes.data.requests || []);
    } catch (err) {
      console.error('Error loading permissions:', err);
      setError('Failed to load permissions. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleRequestSubmitted = () => {
    setShowRequestModal(false);
    loadData(); // Refresh to show new request
  };

  const getPermissionsByCategory = () => {
    const categories = {};
    Object.entries(allPermissions).forEach(([key, info]) => {
      const category = info.category || 'Other';
      if (!categories[category]) {
        categories[category] = [];
      }
      categories[category].push({ key, ...info });
    });
    return categories;
  };

  const hasPermission = (permKey) => {
    return myPermissions[permKey]?.granted === true;
  };

  const hasPendingRequest = (permKey) => {
    return requests.some(r => r.permission_key === permKey && r.status === 'pending');
  };

  const getStatusBadgeClass = (status) => {
    const statusMap = {
      'pending': 'status-pending',
      'approved': 'status-approved',
      'denied': 'status-denied',
      'more_info_needed': 'status-info'
    };
    return statusMap[status] || 'status-pending';
  };

  if (loading) {
    return (
      <div className="my-permissions-page">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading permissions...</p>
        </div>
      </div>
    );
  }

  const permissionsByCategory = getPermissionsByCategory();
  const grantedPermissions = Object.entries(myPermissions).filter(([_, p]) => p.granted);
  const unavailablePermissions = Object.entries(allPermissions).filter(
    ([key]) => !hasPermission(key)
  );

  return (
    <div className="my-permissions-page">
      <div className="page-header">
        <div>
          <h1>My Permissions</h1>
          <p>View what you can do in the system and request additional access</p>
        </div>
        <button
          onClick={() => setShowRequestModal(true)}
          className="btn-primary"
          disabled={unavailablePermissions.length === 0}
        >
          Request Permission
        </button>
      </div>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)} className="close-btn">&times;</button>
        </div>
      )}

      {/* Current Permissions */}
      <section className="permissions-section current-permissions">
        <h2>What I Can Do ({grantedPermissions.length})</h2>
        {grantedPermissions.length === 0 ? (
          <p className="empty-message">No permissions granted yet</p>
        ) : (
          <div className="permissions-grid">
            {Object.entries(permissionsByCategory).map(([category, perms]) => {
              const grantedInCategory = perms.filter(p => hasPermission(p.key));
              if (grantedInCategory.length === 0) return null;

              return (
                <div key={category} className="permission-category">
                  <h3>{category}</h3>
                  <ul>
                    {grantedInCategory.map(perm => (
                      <li key={perm.key} className="permission-item granted">
                        <span className="permission-icon">✓</span>
                        <div className="permission-info">
                          <strong>{perm.name || perm.key}</strong>
                          <p>{perm.description || 'No description available'}</p>
                          {myPermissions[perm.key]?.expires_at && (
                            <span className="expires-badge">
                              Expires: {new Date(myPermissions[perm.key].expires_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Unavailable Permissions */}
      <section className="permissions-section unavailable-permissions">
        <h2>Permissions I Don't Have ({unavailablePermissions.length})</h2>

        {unavailablePermissions.length === 0 ? (
          <p className="empty-message">You have all available permissions!</p>
        ) : (
          <div className="permissions-grid">
            {Object.entries(permissionsByCategory).map(([category, perms]) => {
              const unavailableInCategory = perms.filter(p => !hasPermission(p.key));
              if (unavailableInCategory.length === 0) return null;

              return (
                <div key={category} className="permission-category">
                  <h3>{category}</h3>
                  <ul>
                    {unavailableInCategory.map(perm => (
                      <li key={perm.key} className="permission-item unavailable">
                        <span className="permission-icon">○</span>
                        <div className="permission-info">
                          <strong>{perm.name || perm.key}</strong>
                          <p>{perm.description || 'No description available'}</p>
                          {hasPendingRequest(perm.key) && (
                            <span className="pending-badge">Request Pending</span>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* My Requests */}
      <section className="permissions-section my-requests">
        <h2>My Permission Requests ({requests.length})</h2>
        {requests.length === 0 ? (
          <p className="empty-message">No requests submitted yet</p>
        ) : (
          <div className="requests-table-container">
            <table className="requests-table">
              <thead>
                <tr>
                  <th>Permission</th>
                  <th>Justification</th>
                  <th>Status</th>
                  <th>Requested</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {requests.map(request => (
                  <tr key={request.id}>
                    <td>
                      <div className="permission-name">
                        <strong>{request.permission_key}</strong>
                        {request.is_temporary && (
                          <span className="temp-badge">Temp ({request.duration_days} days)</span>
                        )}
                      </div>
                    </td>
                    <td className="justification-cell">
                      <div className="justification-text">{request.justification}</div>
                    </td>
                    <td>
                      <span className={`status-badge ${getStatusBadgeClass(request.status)}`}>
                        {request.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>{new Date(request.created_at).toLocaleDateString()}</td>
                    <td>
                      {request.status !== 'pending' && request.manager_notes ? (
                        <div className="decision-notes">
                          <p>{request.manager_notes}</p>
                          {request.decided_at && (
                            <small>{new Date(request.decided_at).toLocaleDateString()}</small>
                          )}
                        </div>
                      ) : (
                        <em className="awaiting-decision">Awaiting decision</em>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Request Modal */}
      {showRequestModal && (
        <PermissionRequestModal
          availablePermissions={unavailablePermissions}
          allPermissions={allPermissions}
          pendingRequests={requests}
          onClose={() => setShowRequestModal(false)}
          onSubmit={handleRequestSubmitted}
        />
      )}
    </div>
  );
};

export default MyPermissions;
