import React, { useState, useEffect, useCallback } from 'react';
import {
  getCapacityOverview,
  getCapacityByRole,
  getAllUserCapacities,
  getCapacityAlerts,
  recalculateCapacities,
  updateUserAvailability,
  initializeCapacities,
  runMigration
} from '../../services/masterManagerApi';
import './MasterManager.css';

const CapacityCommandCenter = () => {
  const [overview, setOverview] = useState(null);
  const [byRole, setByRole] = useState([]);
  const [users, setUsers] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [showInitModal, setShowInitModal] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [overviewData, roleData, userData, alertData] = await Promise.all([
        getCapacityOverview().catch(() => null),
        getCapacityByRole().catch(() => ({ roles: [] })),
        getAllUserCapacities({ status: statusFilter, role: roleFilter }).catch(() => ({ users: [] })),
        getCapacityAlerts('open').catch(() => ({ alerts: [] }))
      ]);

      setOverview(overviewData);
      setByRole(roleData.roles || []);
      setUsers(userData.users || []);
      setAlerts(alertData.alerts || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, roleFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await recalculateCapacities();
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  };

  const handleInitialize = async () => {
    try {
      await runMigration();
      await initializeCapacities();
      await loadData();
      setShowInitModal(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleToggleAvailability = async (userId, currentAvailable) => {
    try {
      await updateUserAvailability(userId, {
        is_available: !currentAvailable,
        status: !currentAvailable ? 'active' : 'on_leave'
      });
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'available': return '#22c55e';
      case 'near_capacity': return '#f59e0b';
      case 'at_capacity': return '#f97316';
      case 'over_capacity': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const getCapacityBarColor = (pct) => {
    if (pct >= 100) return '#ef4444';
    if (pct >= 90) return '#f97316';
    if (pct >= 75) return '#f59e0b';
    return '#22c55e';
  };

  if (loading && !overview) {
    return (
      <div className="mm-loading">
        <div className="mm-spinner"></div>
        <p>Loading Capacity Command Center...</p>
      </div>
    );
  }

  return (
    <div className="mm-container">
      {/* Header */}
      <div className="mm-header">
        <div className="mm-header-left">
          <h1>Capacity Command Center</h1>
          <p>Real-time workload visibility and assignment optimization</p>
        </div>
        <div className="mm-header-actions">
          <button
            className="mm-btn mm-btn-secondary"
            onClick={() => setShowInitModal(true)}
          >
            Initialize
          </button>
          <button
            className="mm-btn mm-btn-primary"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Recalculate All'}
          </button>
        </div>
      </div>

      {error && (
        <div className="mm-error">
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Overview Cards */}
      {overview && (
        <div className="mm-overview-grid">
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value">{overview.total_members}</div>
            <div className="mm-stat-label">Team Members</div>
          </div>
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value" style={{ color: '#22c55e' }}>
              {overview.status_breakdown?.available || 0}
            </div>
            <div className="mm-stat-label">Available</div>
          </div>
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value" style={{ color: '#f59e0b' }}>
              {(overview.status_breakdown?.near_capacity || 0) + (overview.status_breakdown?.at_capacity || 0)}
            </div>
            <div className="mm-stat-label">Near/At Capacity</div>
          </div>
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value" style={{ color: '#ef4444' }}>
              {overview.status_breakdown?.over_capacity || 0}
            </div>
            <div className="mm-stat-label">Over Capacity</div>
          </div>
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value">{overview.avg_capacity_pct?.toFixed(0)}%</div>
            <div className="mm-stat-label">Avg Utilization</div>
          </div>
          <div className="mm-card mm-stat-card">
            <div className="mm-stat-value">
              {overview.file_capacity?.available || 0}
            </div>
            <div className="mm-stat-label">Available File Slots</div>
          </div>
        </div>
      )}

      {/* Alerts Banner */}
      {overview?.alerts?.surge_risk && (
        <div className="mm-alert-banner mm-alert-warning">
          <span className="mm-alert-icon">!</span>
          <span>Surge Risk Detected - Team capacity is running high</span>
        </div>
      )}

      {overview?.alerts?.bottleneck_roles?.length > 0 && (
        <div className="mm-alert-banner mm-alert-error">
          <span className="mm-alert-icon">!</span>
          <span>Bottleneck Roles: {overview.alerts.bottleneck_roles.join(', ')}</span>
        </div>
      )}

      {/* Capacity by Role */}
      <div className="mm-section">
        <h2>Capacity by Role</h2>
        <div className="mm-role-grid">
          {byRole.map((role) => (
            <div key={role.role_name} className="mm-card mm-role-card">
              <div className="mm-role-header">
                <span className="mm-role-name">{role.role_name}</span>
                <span className="mm-role-category">{role.role_category}</span>
              </div>
              <div className="mm-role-stats">
                <div className="mm-role-stat">
                  <span className="mm-role-stat-value">{role.member_count}</span>
                  <span className="mm-role-stat-label">Members</span>
                </div>
                <div className="mm-role-stat">
                  <span className="mm-role-stat-value" style={{ color: getCapacityBarColor(role.avg_capacity_pct) }}>
                    {role.avg_capacity_pct?.toFixed(0)}%
                  </span>
                  <span className="mm-role-stat-label">Avg Capacity</span>
                </div>
                <div className="mm-role-stat">
                  <span className="mm-role-stat-value" style={{ color: '#22c55e' }}>
                    {role.available_count}
                  </span>
                  <span className="mm-role-stat-label">Available</span>
                </div>
                <div className="mm-role-stat">
                  <span className="mm-role-stat-value" style={{ color: '#ef4444' }}>
                    {role.at_risk_count}
                  </span>
                  <span className="mm-role-stat-label">At Risk</span>
                </div>
              </div>
              <div className="mm-capacity-bar-container">
                <div
                  className="mm-capacity-bar"
                  style={{
                    width: `${Math.min(role.utilization_pct, 100)}%`,
                    backgroundColor: getCapacityBarColor(role.utilization_pct)
                  }}
                />
              </div>
              <div className="mm-role-footer">
                {role.used_capacity} / {role.total_capacity} file slots used
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Team Member Capacity Table */}
      <div className="mm-section">
        <div className="mm-section-header">
          <h2>Team Member Capacity</h2>
          <div className="mm-filters">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="mm-select"
            >
              <option value="">All Statuses</option>
              <option value="available">Available</option>
              <option value="near_capacity">Near Capacity</option>
              <option value="at_capacity">At Capacity</option>
              <option value="over_capacity">Over Capacity</option>
            </select>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="mm-select"
            >
              <option value="">All Roles</option>
              {byRole.map((r) => (
                <option key={r.role_name} value={r.role_name}>{r.role_name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="mm-table-container">
          <table className="mm-table">
            <thead>
              <tr>
                <th>Team Member</th>
                <th>Role</th>
                <th>Files</th>
                <th>Leads</th>
                <th>Tasks</th>
                <th>Overall</th>
                <th>Status</th>
                <th>Risk</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan="9" className="mm-table-empty">
                    No capacity data found. Click "Initialize" to set up capacity tracking.
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.user_id}>
                    <td>
                      <div className="mm-user-cell">
                        <div className="mm-user-avatar">
                          {user.user_name?.charAt(0) || '?'}
                        </div>
                        <div>
                          <div className="mm-user-name">{user.user_name}</div>
                          <div className="mm-user-email">{user.email}</div>
                        </div>
                      </div>
                    </td>
                    <td>{user.role_name || 'Unassigned'}</td>
                    <td>
                      <div className="mm-capacity-cell">
                        <span>{user.current_files} / {user.max_files}</span>
                        <div className="mm-mini-bar-container">
                          <div
                            className="mm-mini-bar"
                            style={{
                              width: `${Math.min(user.file_capacity_pct, 100)}%`,
                              backgroundColor: getCapacityBarColor(user.file_capacity_pct)
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="mm-capacity-cell">
                        <span>{user.current_leads} / {user.max_leads}</span>
                        <div className="mm-mini-bar-container">
                          <div
                            className="mm-mini-bar"
                            style={{
                              width: `${Math.min(user.lead_capacity_pct, 100)}%`,
                              backgroundColor: getCapacityBarColor(user.lead_capacity_pct)
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="mm-capacity-cell">
                        <span>{user.current_tasks} / {user.max_tasks}</span>
                        <div className="mm-mini-bar-container">
                          <div
                            className="mm-mini-bar"
                            style={{
                              width: `${Math.min(user.task_capacity_pct, 100)}%`,
                              backgroundColor: getCapacityBarColor(user.task_capacity_pct)
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="mm-overall-cell">
                        <span
                          className="mm-overall-value"
                          style={{ color: getCapacityBarColor(user.overall_capacity_pct) }}
                        >
                          {user.overall_capacity_pct?.toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td>
                      <span
                        className="mm-status-badge"
                        style={{ backgroundColor: getStatusColor(user.capacity_status) }}
                      >
                        {user.capacity_status?.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      {(user.burnout_risk > 50 || user.attrition_risk > 50) && (
                        <div className="mm-risk-indicators">
                          {user.burnout_risk > 50 && (
                            <span className="mm-risk-badge mm-risk-burnout" title="Burnout Risk">
                              B: {user.burnout_risk?.toFixed(0)}
                            </span>
                          )}
                          {user.attrition_risk > 50 && (
                            <span className="mm-risk-badge mm-risk-attrition" title="Attrition Risk">
                              A: {user.attrition_risk?.toFixed(0)}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td>
                      <button
                        className={`mm-btn mm-btn-small ${user.is_available ? 'mm-btn-danger' : 'mm-btn-success'}`}
                        onClick={() => handleToggleAvailability(user.user_id, user.is_available)}
                      >
                        {user.is_available ? 'Set OOO' : 'Set Active'}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Active Alerts */}
      {alerts.length > 0 && (
        <div className="mm-section">
          <h2>Active Alerts ({alerts.length})</h2>
          <div className="mm-alerts-list">
            {alerts.slice(0, 5).map((alert) => (
              <div key={alert.id} className={`mm-alert-item mm-alert-${alert.severity}`}>
                <div className="mm-alert-content">
                  <div className="mm-alert-title">{alert.title}</div>
                  <div className="mm-alert-description">{alert.description}</div>
                  {alert.user_name && (
                    <div className="mm-alert-user">
                      Related to: {alert.user_name} ({alert.role_name})
                    </div>
                  )}
                </div>
                <div className="mm-alert-meta">
                  <span className={`mm-severity-badge mm-severity-${alert.severity}`}>
                    {alert.severity}
                  </span>
                  <span className="mm-alert-time">
                    {new Date(alert.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Initialize Modal */}
      {showInitModal && (
        <div className="mm-modal-overlay">
          <div className="mm-modal">
            <h3>Initialize Master Manager</h3>
            <p>This will:</p>
            <ul>
              <li>Create capacity tracking tables</li>
              <li>Initialize capacity records for all active users</li>
              <li>Calculate initial capacity metrics</li>
            </ul>
            <div className="mm-modal-actions">
              <button
                className="mm-btn mm-btn-secondary"
                onClick={() => setShowInitModal(false)}
              >
                Cancel
              </button>
              <button
                className="mm-btn mm-btn-primary"
                onClick={handleInitialize}
              >
                Initialize
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CapacityCommandCenter;
