import React, { useState, useEffect } from 'react';
import './AccessAuditTab.css';
import { auditAPI } from '../services/api';
import { toast } from '../utils/toast';

const AccessAuditTab = ({ userId }) => {
  // State for Audit Log
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditFilters, setAuditFilters] = useState({
    startDate: '',
    endDate: '',
    changeType: '',
    search: ''
  });
  const [auditPagination, setAuditPagination] = useState({ limit: 50, offset: 0, total: 0 });

  // State for Active Sessions
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);

  // State for Impersonation History
  const [impersonations, setImpersonations] = useState([]);
  const [impersonationsLoading, setImpersonationsLoading] = useState(true);

  // State for Emergency Revocation
  const [showEmergencyModal, setShowEmergencyModal] = useState(false);
  const [emergencyForm, setEmergencyForm] = useState({
    reason: 'security_incident',
    details: '',
    notify: [],
    reinstateType: 'manual',
    reinstateDate: ''
  });
  const [emergencyLoading, setEmergencyLoading] = useState(false);

  // Active section state
  const [activeSection, setActiveSection] = useState('audit-log');

  // Load data on mount
  useEffect(() => {
    loadAuditLog();
    loadSessions();
    loadImpersonations();
  }, [userId]);

  // Load audit log with filters
  const loadAuditLog = async () => {
    try {
      setAuditLoading(true);
      const params = {
        start_date: auditFilters.startDate,
        end_date: auditFilters.endDate,
        change_type: auditFilters.changeType,
        search: auditFilters.search,
        limit: auditPagination.limit,
        offset: auditPagination.offset
      };
      const response = await auditAPI.getAuditLog(userId, params);
      setAuditLogs(response.logs || []);
      setAuditPagination(prev => ({ ...prev, total: response.total || 0 }));
    } catch (error) {
      console.error('Error loading audit log:', error);
      toast.error('Failed to load audit log');
    } finally {
      setAuditLoading(false);
    }
  };

  // Load active sessions
  const loadSessions = async () => {
    try {
      setSessionsLoading(true);
      const response = await auditAPI.getActiveSessions(userId);
      setSessions(response.sessions || []);
    } catch (error) {
      console.error('Error loading sessions:', error);
      toast.error('Failed to load active sessions');
    } finally {
      setSessionsLoading(false);
    }
  };

  // Load impersonation history
  const loadImpersonations = async () => {
    try {
      setImpersonationsLoading(true);
      const response = await auditAPI.getImpersonationHistory(userId);
      setImpersonations(response.impersonations || []);
    } catch (error) {
      console.error('Error loading impersonation history:', error);
    } finally {
      setImpersonationsLoading(false);
    }
  };

  // Revoke single session
  const handleRevokeSession = async (sessionId) => {
    const reason = prompt('Reason for revoking this session:');
    if (!reason) return;

    try {
      await auditAPI.revokeSession(userId, sessionId, reason);
      toast.success('Session revoked successfully');
      loadSessions();
      loadAuditLog();
    } catch (error) {
      console.error('Error revoking session:', error);
      toast.error('Failed to revoke session');
    }
  };

  // Revoke all sessions
  const handleRevokeAllSessions = async () => {
    const reason = prompt('Reason for revoking ALL sessions (required):');
    if (!reason) return;

    try {
      await auditAPI.revokeAllSessions(userId, reason);
      toast.success('All sessions revoked successfully');
      loadSessions();
      loadAuditLog();
    } catch (error) {
      console.error('Error revoking all sessions:', error);
      toast.error('Failed to revoke all sessions');
    }
  };

  // Handle emergency revocation
  const handleEmergencyRevoke = async () => {
    if (!emergencyForm.details.trim()) {
      toast.error('Please provide details for the emergency revocation');
      return;
    }

    try {
      setEmergencyLoading(true);
      await auditAPI.emergencyRevoke(userId, emergencyForm);
      toast.success('Emergency access revocation completed successfully');
      setShowEmergencyModal(false);
      setEmergencyForm({
        reason: 'security_incident',
        details: '',
        notify: [],
        reinstateType: 'manual',
        reinstateDate: ''
      });
      loadSessions();
      loadAuditLog();
    } catch (error) {
      console.error('Error during emergency revocation:', error);
      toast.error('Failed to complete emergency revocation');
    } finally {
      setEmergencyLoading(false);
    }
  };

  // Format timestamp
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleString();
  };

  // Format change type
  const formatChangeType = (type) => {
    const types = {
      'permission': 'Permission',
      'role': 'Role',
      'profile': 'Profile',
      'workflow': 'Workflow',
      'milestone': 'Milestone',
      'goal': 'Goal',
      'skill': 'Skill',
      'emergency_revocation': 'Emergency Revocation'
    };
    return types[type] || type;
  };

  // Render audit log section
  const renderAuditLog = () => (
    <div className="audit-log-section">
      <div className="section-header">
        <h3>Audit Log</h3>
        <p>All changes to this user's profile and permissions</p>
      </div>

      {/* Filters */}
      <div className="audit-filters">
        <div className="filter-row">
          <div className="filter-group">
            <label>Start Date</label>
            <input
              type="date"
              value={auditFilters.startDate}
              onChange={(e) => setAuditFilters({ ...auditFilters, startDate: e.target.value })}
            />
          </div>
          <div className="filter-group">
            <label>End Date</label>
            <input
              type="date"
              value={auditFilters.endDate}
              onChange={(e) => setAuditFilters({ ...auditFilters, endDate: e.target.value })}
            />
          </div>
          <div className="filter-group">
            <label>Change Type</label>
            <select
              value={auditFilters.changeType}
              onChange={(e) => setAuditFilters({ ...auditFilters, changeType: e.target.value })}
            >
              <option value="">All Types</option>
              <option value="permission">Permission</option>
              <option value="role">Role</option>
              <option value="profile">Profile</option>
              <option value="workflow">Workflow</option>
              <option value="emergency_revocation">Emergency Revocation</option>
            </select>
          </div>
          <div className="filter-group">
            <label>Search</label>
            <input
              type="text"
              placeholder="Search changes..."
              value={auditFilters.search}
              onChange={(e) => setAuditFilters({ ...auditFilters, search: e.target.value })}
            />
          </div>
          <button className="apply-filters-btn" onClick={loadAuditLog}>
            Apply Filters
          </button>
        </div>
      </div>

      {/* Audit Log Table */}
      {auditLoading ? (
        <div className="loading-state">Loading audit log...</div>
      ) : auditLogs.length === 0 ? (
        <div className="empty-state">No audit logs found</div>
      ) : (
        <div className="audit-log-table">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Change Type</th>
                <th>Changed By</th>
                <th>Entity</th>
                <th>Changes</th>
                <th>IP Address</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map((log) => (
                <tr key={log.id}>
                  <td className="timestamp">{formatTimestamp(log.timestamp)}</td>
                  <td>
                    <span className={`change-type-badge ${log.change_type}`}>
                      {formatChangeType(log.change_type)}
                    </span>
                  </td>
                  <td>{log.changed_by_email || `User ${log.changed_by_id}`}</td>
                  <td>{log.entity_type}</td>
                  <td className="changes-cell">
                    <details>
                      <summary>View Changes</summary>
                      <div className="change-details">
                        <div className="before-after">
                          <div className="before">
                            <strong>Before:</strong>
                            <pre>{JSON.stringify(log.before_state, null, 2)}</pre>
                          </div>
                          <div className="after">
                            <strong>After:</strong>
                            <pre>{JSON.stringify(log.after_state, null, 2)}</pre>
                          </div>
                        </div>
                        {log.reason && (
                          <div className="reason">
                            <strong>Reason:</strong> {log.reason}
                          </div>
                        )}
                      </div>
                    </details>
                  </td>
                  <td>{log.ip_address || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {auditLogs.length > 0 && (
        <div className="pagination">
          <button
            onClick={() => {
              setAuditPagination(prev => ({ ...prev, offset: Math.max(0, prev.offset - prev.limit) }));
              loadAuditLog();
            }}
            disabled={auditPagination.offset === 0}
          >
            Previous
          </button>
          <span>
            Showing {auditPagination.offset + 1} - {Math.min(auditPagination.offset + auditPagination.limit, auditPagination.total)} of {auditPagination.total}
          </span>
          <button
            onClick={() => {
              setAuditPagination(prev => ({ ...prev, offset: prev.offset + prev.limit }));
              loadAuditLog();
            }}
            disabled={auditPagination.offset + auditPagination.limit >= auditPagination.total}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );

  // Render active sessions section
  const renderSessions = () => (
    <div className="sessions-section">
      <div className="section-header">
        <h3>Active Sessions</h3>
        <p>Manage user's active login sessions</p>
        {sessions.length > 0 && (
          <button className="revoke-all-btn" onClick={handleRevokeAllSessions}>
            Revoke All Sessions
          </button>
        )}
      </div>

      {sessionsLoading ? (
        <div className="loading-state">Loading sessions...</div>
      ) : sessions.length === 0 ? (
        <div className="empty-state">No active sessions</div>
      ) : (
        <div className="sessions-grid">
          {sessions.map((session) => (
            <div key={session.id} className="session-card">
              <div className="session-header">
                <span className="session-device">{session.device || 'Unknown Device'}</span>
                {session.is_current && <span className="current-session-badge">Current Session</span>}
              </div>
              <div className="session-details">
                <div className="detail-row">
                  <span className="label">Login Time:</span>
                  <span className="value">{formatTimestamp(session.logged_in_at)}</span>
                </div>
                <div className="detail-row">
                  <span className="label">Last Activity:</span>
                  <span className="value">{formatTimestamp(session.last_activity)}</span>
                </div>
                <div className="detail-row">
                  <span className="label">IP Address:</span>
                  <span className="value">{session.ip_address || 'N/A'}</span>
                </div>
                <div className="detail-row">
                  <span className="label">Location:</span>
                  <span className="value">{session.location || 'Unknown'}</span>
                </div>
              </div>
              <button
                className="revoke-session-btn"
                onClick={() => handleRevokeSession(session.session_id)}
              >
                Revoke Session
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Impersonation History */}
      <div className="impersonation-history">
        <h4>Impersonation History</h4>
        {impersonationsLoading ? (
          <div className="loading-state">Loading...</div>
        ) : impersonations.length === 0 ? (
          <div className="empty-state">No impersonation history</div>
        ) : (
          <table className="impersonation-table">
            <thead>
              <tr>
                <th>Impersonated By</th>
                <th>Started</th>
                <th>Ended</th>
                <th>Duration</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {impersonations.map((imp) => (
                <tr key={imp.id}>
                  <td>{imp.impersonated_by_email}</td>
                  <td>{formatTimestamp(imp.started_at)}</td>
                  <td>{formatTimestamp(imp.ended_at)}</td>
                  <td>{imp.duration || 'N/A'}</td>
                  <td>{imp.reason || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );

  // Render emergency revocation section
  const renderEmergencyRevocation = () => (
    <div className="emergency-section">
      <div className="section-header emergency-header">
        <div>
          <h3>Emergency Access Revocation</h3>
          <p>Immediately terminate all access and sessions</p>
        </div>
        <button className="emergency-revoke-btn" onClick={() => setShowEmergencyModal(true)}>
          Emergency Revoke Access
        </button>
      </div>

      <div className="emergency-warning">
        <strong>Warning:</strong> Emergency revocation will immediately terminate all active sessions,
        revoke all permissions, and notify selected parties. Use only in cases of:
        <ul>
          <li>Employee termination</li>
          <li>Security incident or breach</li>
          <li>Policy violation</li>
          <li>Active investigation</li>
        </ul>
      </div>
    </div>
  );

  return (
    <div className="access-audit-tab">
      {/* Section Navigation */}
      <div className="section-nav">
        <button
          className={activeSection === 'audit-log' ? 'active' : ''}
          onClick={() => setActiveSection('audit-log')}
        >
          Audit Log
        </button>
        <button
          className={activeSection === 'sessions' ? 'active' : ''}
          onClick={() => setActiveSection('sessions')}
        >
          Active Sessions ({sessions.length})
        </button>
        <button
          className={activeSection === 'emergency' ? 'active' : ''}
          onClick={() => setActiveSection('emergency')}
        >
          Emergency Revocation
        </button>
      </div>

      {/* Active Section */}
      <div className="section-content">
        {activeSection === 'audit-log' && renderAuditLog()}
        {activeSection === 'sessions' && renderSessions()}
        {activeSection === 'emergency' && renderEmergencyRevocation()}
      </div>

      {/* Emergency Revocation Modal */}
      {showEmergencyModal && (
        <div className="modal-overlay" onClick={() => setShowEmergencyModal(false)}>
          <div className="emergency-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Emergency Access Revocation</h3>
            <p className="modal-warning">This action cannot be undone easily. Proceed with caution.</p>

            <div className="form-group">
              <label>Reason *</label>
              <select
                value={emergencyForm.reason}
                onChange={(e) => setEmergencyForm({ ...emergencyForm, reason: e.target.value })}
              >
                <option value="termination">Employee Termination</option>
                <option value="security_incident">Security Incident</option>
                <option value="policy_violation">Policy Violation</option>
                <option value="investigation">Active Investigation</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div className="form-group">
              <label>Details *</label>
              <textarea
                rows="4"
                placeholder="Provide detailed explanation..."
                value={emergencyForm.details}
                onChange={(e) => setEmergencyForm({ ...emergencyForm, details: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label>Notify</label>
              <div className="checkbox-group">
                {['hr', 'security', 'manager', 'employee'].map((party) => (
                  <label key={party}>
                    <input
                      type="checkbox"
                      checked={emergencyForm.notify.includes(party)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setEmergencyForm({
                            ...emergencyForm,
                            notify: [...emergencyForm.notify, party]
                          });
                        } else {
                          setEmergencyForm({
                            ...emergencyForm,
                            notify: emergencyForm.notify.filter(p => p !== party)
                          });
                        }
                      }}
                    />
                    {party.charAt(0).toUpperCase() + party.slice(1)}
                  </label>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label>Reinstatement</label>
              <select
                value={emergencyForm.reinstateType}
                onChange={(e) => setEmergencyForm({ ...emergencyForm, reinstateType: e.target.value })}
              >
                <option value="manual">Manual (Requires admin approval)</option>
                <option value="automatic">Automatic (Set date)</option>
              </select>
            </div>

            {emergencyForm.reinstateType === 'automatic' && (
              <div className="form-group">
                <label>Reinstate Date</label>
                <input
                  type="datetime-local"
                  value={emergencyForm.reinstateDate}
                  onChange={(e) => setEmergencyForm({ ...emergencyForm, reinstateDate: e.target.value })}
                />
              </div>
            )}

            <div className="modal-actions">
              <button onClick={() => setShowEmergencyModal(false)} disabled={emergencyLoading}>
                Cancel
              </button>
              <button
                className="emergency-confirm-btn"
                onClick={handleEmergencyRevoke}
                disabled={emergencyLoading}
              >
                {emergencyLoading ? 'Revoking...' : 'Confirm Emergency Revocation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AccessAuditTab;
