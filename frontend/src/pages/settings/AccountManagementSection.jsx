import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../../utils/toast';
import { API_BASE_URL, getStatusBadgeStyle, formatDate } from './shared/constants';
import { getToken, getUserData } from '../../utils/tokenStore';

const AccountManagementSection = () => {
  const navigate = useNavigate();

  // Security audit log state
  const [securityAuditLogs, setSecurityAuditLogs] = useState([]);
  const [loadingAuditLogs, setLoadingAuditLogs] = useState(false);
  const [auditLogsError, setAuditLogsError] = useState(null);

  useEffect(() => {
    fetchSecurityAuditLogs();
  }, []);

  const fetchSecurityAuditLogs = async () => {
    setLoadingAuditLogs(true);
    setAuditLogsError(null);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/security-audit-log?limit=10`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success' && data.data && data.data.logs) {
          setSecurityAuditLogs(data.data.logs);
        }
      } else {
        console.error('Failed to fetch security audit logs:', response.status);
        setAuditLogsError('Failed to load security events');
      }
    } catch (error) {
      console.error('Error fetching security audit logs:', error);
      setAuditLogsError('Error loading security events');
    } finally {
      setLoadingAuditLogs(false);
    }
  };

  return (
    <div className="account-management-section">
      <div className="section-header">
        <div>
          <h2>Account Management</h2>
          <p className="section-description">
            Manage company accounts, users, and system settings
          </p>
        </div>
      </div>

      {/* KPI Dashboard */}
      <div className="account-kpi-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '24px' }}>
        <div className="kpi-card" style={{ background: '#f8fafc', borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
          <div style={{ fontSize: '32px', fontWeight: '700', color: '#1e293b' }}>3</div>
          <div style={{ fontSize: '14px', color: '#64748b' }}>Active Accounts</div>
        </div>
        <div className="kpi-card" style={{ background: '#f8fafc', borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
          <div style={{ fontSize: '32px', fontWeight: '700', color: '#1e293b' }}>25</div>
          <div style={{ fontSize: '14px', color: '#64748b' }}>Total Users</div>
        </div>
        <div className="kpi-card" style={{ background: '#f8fafc', borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
          <div style={{ fontSize: '32px', fontWeight: '700', color: '#22c55e' }}>$12,450</div>
          <div style={{ fontSize: '14px', color: '#64748b' }}>Monthly Revenue</div>
        </div>
        <div className="kpi-card" style={{ background: '#f8fafc', borderRadius: '12px', padding: '20px', textAlign: 'center' }}>
          <div style={{ fontSize: '32px', fontWeight: '700', color: '#3b82f6' }}>98%</div>
          <div style={{ fontSize: '14px', color: '#64748b' }}>System Health</div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="quick-actions" style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
        <button className="btn-primary" onClick={() => navigate('/users/create')}>
          + Add New User
        </button>
        <button className="btn-secondary" onClick={() => navigate('/team-members')}>
          View Team Members
        </button>
      </div>

      {/* Accounts List */}
      <div className="accounts-section" style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0', marginBottom: '24px' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Accounts</h3>
        </div>
        <div style={{ padding: '20px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                <th style={{ textAlign: 'left', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Account</th>
                <th style={{ textAlign: 'left', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Users</th>
                <th style={{ textAlign: 'left', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Status</th>
                <th style={{ textAlign: 'left', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Plan</th>
                <th style={{ textAlign: 'right', padding: '12px 0', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ padding: '16px 0' }}>
                  <div style={{ fontWeight: '500', color: '#1e293b' }}>Primary Organization</div>
                  <div style={{ fontSize: '13px', color: '#64748b' }}>admin@perenniaai.com</div>
                </td>
                <td style={{ padding: '16px 0', color: '#1e293b' }}>25</td>
                <td style={{ padding: '16px 0' }}>
                  <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 12px', borderRadius: '20px', fontSize: '13px' }}>Active</span>
                </td>
                <td style={{ padding: '16px 0', color: '#1e293b' }}>Enterprise</td>
                <td style={{ padding: '16px 0', textAlign: 'right' }}>
                  <button style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', marginRight: '8px' }}>View</button>
                  <button style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer' }}>Edit</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Security Overview */}
      <div className="security-section" style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0', marginBottom: '24px' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Security Overview</h3>
          <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 12px', borderRadius: '20px', fontSize: '13px', fontWeight: '500' }}>All Systems Secure</span>
        </div>
        <div style={{ padding: '20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
            {[
              { label: 'SSL Certificate', detail: 'Valid until Dec 2025' },
              { label: '2FA Enabled', detail: 'All admin accounts' },
              { label: 'Data Encryption', detail: 'AES-256 at rest' },
              { label: 'Firewall Active', detail: 'WAF protection' },
            ].map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ color: '#22c55e', fontSize: '20px' }}>&#10003;</span>
                <div>
                  <div style={{ fontWeight: '500', color: '#1e293b' }}>{item.label}</div>
                  <div style={{ fontSize: '13px', color: '#64748b' }}>{item.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Access Control & Compliance */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Access Control</h3>
          </div>
          <div style={{ padding: '20px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {[
                { label: 'Active Sessions', detail: 'Currently logged in users', value: '12', color: '#3b82f6' },
                { label: 'Failed Login Attempts', detail: 'Last 24 hours', value: '0', color: '#22c55e' },
                { label: 'Password Resets', detail: 'Last 7 days', value: '2', color: '#64748b' },
                { label: 'API Keys Active', detail: 'Third-party integrations', value: '5', color: '#64748b' },
              ].map((item, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                  <div>
                    <div style={{ fontWeight: '500', color: '#1e293b' }}>{item.label}</div>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>{item.detail}</div>
                  </div>
                  <div style={{ fontSize: '24px', fontWeight: '700', color: item.color }}>{item.value}</div>
                </div>
              ))}
            </div>
            <button style={{ marginTop: '16px', width: '100%', padding: '10px', background: '#f1f5f9', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '500', color: '#475569' }}>
              Manage Sessions
            </button>
          </div>
        </div>

        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Compliance Status</h3>
          </div>
          <div style={{ padding: '20px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[
                { icon: '🛡️', label: 'SOC 2 Type II', detail: 'Certified compliant' },
                { icon: '🔒', label: 'GLBA Compliant', detail: 'Financial data protection' },
                { icon: '🌐', label: 'CCPA Ready', detail: 'California privacy law' },
                { icon: '📋', label: 'RESPA Compliant', detail: 'Real estate settlement' },
              ].map((item, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '20px' }}>{item.icon}</span>
                    <div>
                      <div style={{ fontWeight: '500', color: '#1e293b' }}>{item.label}</div>
                      <div style={{ fontSize: '13px', color: '#64748b' }}>{item.detail}</div>
                    </div>
                  </div>
                  <span style={{ background: '#dcfce7', color: '#166534', padding: '4px 10px', borderRadius: '20px', fontSize: '12px' }}>Verified</span>
                </div>
              ))}
            </div>
            <button style={{ marginTop: '16px', width: '100%', padding: '10px', background: '#f1f5f9', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '500', color: '#475569' }}>
              View Compliance Reports
            </button>
          </div>
        </div>
      </div>

      {/* Security Audit Log */}
      <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0', marginBottom: '24px' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Recent Security Events</h3>
          <button
            onClick={fetchSecurityAuditLogs}
            style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
          >
            {loadingAuditLogs ? 'Loading...' : 'Refresh'}
          </button>
        </div>
        <div style={{ padding: '0' }}>
          {loadingAuditLogs ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', color: '#64748b' }}>
              Loading security events...
            </div>
          ) : auditLogsError ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', color: '#ef4444' }}>
              {auditLogsError}
            </div>
          ) : securityAuditLogs.length === 0 ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', color: '#64748b' }}>
              No security events recorded yet
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Event</th>
                  <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>User</th>
                  <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>IP Address</th>
                  <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Time</th>
                  <th style={{ textAlign: 'left', padding: '12px 20px', color: '#64748b', fontSize: '12px', fontWeight: '500', textTransform: 'uppercase' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {securityAuditLogs.map((log, index) => (
                  <tr key={log.id || index} style={{ borderBottom: index < securityAuditLogs.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                    <td style={{ padding: '14px 20px', color: '#1e293b' }}>{log.event}</td>
                    <td style={{ padding: '14px 20px', color: '#64748b' }}>{log.actorName || log.targetName || 'System'}</td>
                    <td style={{ padding: '14px 20px', color: '#64748b', fontFamily: 'monospace', fontSize: '13px' }}>{log.ipAddress}</td>
                    <td style={{ padding: '14px 20px', color: '#64748b' }}>{log.timeAgo}</td>
                    <td style={{ padding: '14px 20px' }}>
                      <span style={{
                        ...getStatusBadgeStyle(log.status),
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '12px'
                      }}>
                        {log.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Data Protection & Backup */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Data Protection</h3>
          </div>
          <div style={{ padding: '20px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {[
                { icon: '🔐', label: 'Encryption at Rest', detail: 'AES-256 encryption for all stored data' },
                { icon: '🔒', label: 'Encryption in Transit', detail: 'TLS 1.3 for all connections' },
                { icon: '🗝️', label: 'Key Management', detail: 'AWS KMS managed keys' },
                { icon: '🛡️', label: 'PII Masking', detail: 'Sensitive data automatically masked' },
              ].map((item, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '40px', height: '40px', background: '#dbeafe', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px' }}>{item.icon}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: '500', color: '#1e293b' }}>{item.label}</div>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>{item.detail}</div>
                  </div>
                  <span style={{ color: '#22c55e', fontSize: '18px' }}>&#10003;</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Backup & Recovery</h3>
          </div>
          <div style={{ padding: '20px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ padding: '16px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ fontWeight: '500', color: '#166534' }}>Last Backup</div>
                  <span style={{ color: '#22c55e', fontSize: '14px' }}>&#10003; Successful</span>
                </div>
                <div style={{ fontSize: '24px', fontWeight: '700', color: '#166534' }}>2 hours ago</div>
                <div style={{ fontSize: '13px', color: '#15803d', marginTop: '4px' }}>Next backup in 4 hours</div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                <div>
                  <div style={{ fontWeight: '500', color: '#1e293b' }}>Backup Frequency</div>
                  <div style={{ fontSize: '13px', color: '#64748b' }}>Automatic every 6 hours</div>
                </div>
                <button style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '4px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}>Configure</button>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px', background: '#f8fafc', borderRadius: '8px' }}>
                <div>
                  <div style={{ fontWeight: '500', color: '#1e293b' }}>Retention Period</div>
                  <div style={{ fontSize: '13px', color: '#64748b' }}>90 days of backup history</div>
                </div>
                <button style={{ background: 'transparent', border: '1px solid #e2e8f0', padding: '4px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}>Configure</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Security Recommendations */}
      <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600' }}>Security Recommendations</h3>
        </div>
        <div style={{ padding: '20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: '#fffbeb', borderRadius: '8px', border: '1px solid #fde68a' }}>
              <span style={{ fontSize: '20px' }}>&#9888;&#65039;</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: '500', color: '#92400e' }}>Enable 2FA for 3 remaining users</div>
                <div style={{ fontSize: '13px', color: '#a16207' }}>Some team members haven't enabled two-factor authentication</div>
              </div>
              <button style={{ background: '#f59e0b', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontWeight: '500' }}>Enable Now</button>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: '#f0f9ff', borderRadius: '8px', border: '1px solid #bae6fd' }}>
              <span style={{ fontSize: '20px' }}>&#128161;</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: '500', color: '#0369a1' }}>Review API key permissions</div>
                <div style={{ fontSize: '13px', color: '#0284c7' }}>2 API keys have full admin access - consider limiting scope</div>
              </div>
              <button style={{ background: '#0ea5e9', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontWeight: '500' }}>Review</button>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
              <span style={{ fontSize: '20px' }}>&#10004;&#65039;</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: '500', color: '#166534' }}>Password policy is strong</div>
                <div style={{ fontSize: '13px', color: '#15803d' }}>Minimum 12 characters with complexity requirements</div>
              </div>
              <span style={{ color: '#22c55e', fontWeight: '500' }}>Configured</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AccountManagementSection;
