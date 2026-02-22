import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { complianceApi } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import './ComplianceDashboard.css';
import { toast } from '../utils/toast';

const ComplianceDashboard = () => {
  const navigate = useNavigate();
  const { userRole, hasPermission, isAdmin } = usePermissions();

  // Permission check - require compliance access
  // Use isAdmin from context which has robust admin detection (checks permission_role, is_admin flag, legacy role)
  const canViewCompliance = isAdmin || hasPermission('compliance.view') || userRole === 'management' || userRole === 'admin';

  const [overview, setOverview] = useState(null);
  const [departmentData, setDepartmentData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [overviewRes, deptRes] = await Promise.all([
        complianceApi.getOverview(),
        complianceApi.getCertificationsByDepartment()
      ]);

      setOverview(overviewRes.data);
      setDepartmentData(deptRes.data.departments || []);
    } catch (err) {
      console.error('Error loading compliance data:', err);
      toast.error('Failed to load compliance data. Please ensure you have admin/management access.');
    } finally {
      setLoading(false);
    }
  };

  const exportReport = async (format) => {
    try {
      const response = await complianceApi.exportReport(format);
      // Trigger download
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `compliance_report.${format}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      toast.error('Failed to export report');
      console.error(err);
    }
  };

  // Access denied if user doesn't have compliance permissions
  if (!canViewCompliance) {
    return (
      <div className="compliance-dashboard">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to view the Compliance Dashboard.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="compliance-dashboard">
        <div className="loading-state">Loading compliance data...</div>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="compliance-dashboard">
        <div className="error-state">Failed to load compliance data</div>
      </div>
    );
  }

  return (
    <div className="compliance-dashboard">
      <div className="page-header">
        <h1>Compliance Dashboard</h1>
        <div className="header-actions">
          <button onClick={() => exportReport('csv')} className="btn-secondary">
            Export CSV
          </button>
          <button onClick={loadData} className="btn-secondary">
            Refresh
          </button>
        </div>
      </div>

      {/* Overview Metrics */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-value">{overview.users.total}</div>
          <div className="metric-label">Total Active Users</div>
        </div>

        <div className="metric-card">
          <div className="metric-value">
            {overview.certifications.certified_percent}%
          </div>
          <div className="metric-label">Certifications Complete</div>
          <div className="metric-detail">
            {overview.certifications.certified} / {overview.certifications.total}
          </div>
        </div>

        <div className={`metric-card ${overview.certifications.overdue > 0 ? 'warning' : ''}`}>
          <div className="metric-value">{overview.certifications.overdue}</div>
          <div className="metric-label">Overdue Certifications</div>
        </div>

        <div className="metric-card">
          <div className="metric-value">{overview.permissions.high_risk_granted}</div>
          <div className="metric-label">High-Risk Permissions</div>
        </div>
      </div>

      {/* Department Breakdown */}
      <section className="dashboard-section">
        <h2>Certification Status by Department</h2>
        <div className="department-table">
          <table>
            <thead>
              <tr>
                <th>Department</th>
                <th>Employees</th>
                <th>Certified</th>
                <th>Overdue</th>
                <th>Completion Rate</th>
              </tr>
            </thead>
            <tbody>
              {departmentData.map(dept => (
                <tr key={dept.department}>
                  <td><strong>{dept.department}</strong></td>
                  <td>{dept.total_employees}</td>
                  <td>{dept.certified}</td>
                  <td className={dept.overdue > 0 ? 'warning' : ''}>{dept.overdue}</td>
                  <td>
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{ width: `${dept.certified_percent}%` }}
                      />
                      <span className="progress-text">{dept.certified_percent}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {departmentData.length === 0 && (
            <div className="empty-state">
              <p>No department data available</p>
            </div>
          )}
        </div>
      </section>

      {/* Summary Stats */}
      <section className="dashboard-section">
        <h2>System Summary</h2>
        <div className="summary-grid">
          <div className="summary-card">
            <h4>Total Permissions Granted</h4>
            <div className="summary-value">{overview.permissions.total_granted}</div>
          </div>
          <div className="summary-card">
            <h4>Recent Changes (30 days)</h4>
            <div className="summary-value">{overview.permissions.recent_changes_30d}</div>
          </div>
          <div className="summary-card">
            <h4>Pending Certifications</h4>
            <div className="summary-value">{overview.certifications.pending}</div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ComplianceDashboard;
