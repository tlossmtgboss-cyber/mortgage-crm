import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './StageEmployees.css'; // Reuse same styles

// Mock data for employees by role
const roleEmployeesData = {
  'loan-officers': {
    roleName: 'Loan Officers',
    roleDescription: 'Responsible for lead generation, pre-qualification, and application stages',
    employees: [
      { id: 'LO001', name: 'Timothy Loss', efficiency: 92, avgResponseTime: '1.8 hrs', taskCompletionRate: 95, activeLoans: 8, trend: 12, avatar: 'TL' },
      { id: 'LO002', name: 'Sarah Mitchell', efficiency: 88, avgResponseTime: '2.3 hrs', taskCompletionRate: 91, activeLoans: 5, trend: 8, avatar: 'SM' },
      { id: 'LO003', name: 'Mike Johnson', efficiency: 78, avgResponseTime: '3.1 hrs', taskCompletionRate: 82, activeLoans: 2, trend: -3, avatar: 'MJ' }
    ]
  },
  'processors': {
    roleName: 'Processors',
    roleDescription: 'Handle document collection, verification, and file preparation',
    employees: [
      { id: 'PR001', name: 'Jessica Marlow', efficiency: 72, avgResponseTime: '4.2 hrs', taskCompletionRate: 78, activeLoans: 12, trend: -5, avatar: 'JM' },
      { id: 'PR002', name: 'Jennifer Lopez', efficiency: 58, avgResponseTime: '6.5 hrs', taskCompletionRate: 65, activeLoans: 10, trend: -12, avatar: 'JL' }
    ]
  },
  'underwriters': {
    roleName: 'Underwriters',
    roleDescription: 'Review loan files, assess risk, and issue approvals',
    employees: [
      { id: 'UW201', name: 'Danielle Brooks', efficiency: 82, avgResponseTime: '3.5 hrs', taskCompletionRate: 88, activeLoans: 2, trend: 8, avatar: 'DB' },
      { id: 'UW202', name: 'Samuel Price', efficiency: 75, avgResponseTime: '4.2 hrs', taskCompletionRate: 82, activeLoans: 2, trend: 3, avatar: 'SP' },
      { id: 'UW203', name: 'Helen Rogers', efficiency: 68, avgResponseTime: '5.1 hrs', taskCompletionRate: 76, activeLoans: 1, trend: -2, avatar: 'HR' },
      { id: 'UW204', name: 'Kelvin Abdul', efficiency: 62, avgResponseTime: '5.8 hrs', taskCompletionRate: 72, activeLoans: 2, trend: -5, avatar: 'KA' },
      { id: 'UW205', name: 'Patricia Donovan', efficiency: 70, avgResponseTime: '4.5 hrs', taskCompletionRate: 79, activeLoans: 1, trend: 5, avatar: 'PD' }
    ]
  },
  'closers': {
    roleName: 'Closers',
    roleDescription: 'Manage clear-to-close and closing stages',
    employees: [
      { id: 'CL001', name: 'Tom Wilson', efficiency: 95, avgResponseTime: '1.2 hrs', taskCompletionRate: 98, activeLoans: 5, trend: 18, avatar: 'TW' },
      { id: 'CL002', name: 'Linda Martinez', efficiency: 88, avgResponseTime: '1.8 hrs', taskCompletionRate: 94, activeLoans: 3, trend: 10, avatar: 'LM' }
    ]
  }
};

// Role aggregate metrics
const roleMetricsData = {
  'loan-officers': { efficiency: 82, activeLoans: 15, avgResponseTime: '2.3 hrs', taskCompletionRate: 89, trend: 6 },
  'processors': { efficiency: 68, activeLoans: 22, avgResponseTime: '5.1 hrs', taskCompletionRate: 72, trend: -4 },
  'underwriters': { efficiency: 75, activeLoans: 18, avgResponseTime: '4.2 hrs', taskCompletionRate: 81, trend: 3 },
  'closers': { efficiency: 91, activeLoans: 8, avgResponseTime: '1.5 hrs', taskCompletionRate: 95, trend: 12 }
};

function TeamRoleEmployees() {
  const { roleSlug } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setTimeout(() => setLoading(false), 300);
  }, []);

  const roleData = roleEmployeesData[roleSlug];
  const roleMetrics = roleMetricsData[roleSlug];

  if (loading) {
    return (
      <div className="stage-employees-page">
        <div className="loading-spinner">Loading team data...</div>
      </div>
    );
  }

  if (!roleData) {
    return (
      <div className="stage-employees-page">
        <div className="error-state">
          <h2>Role Not Found</h2>
          <p>The requested role "{roleSlug}" was not found.</p>
          <button onClick={() => navigate('/efficiency')}>← Back to Pipeline Efficiency</button>
        </div>
      </div>
    );
  }

  const getEfficiencyClass = (efficiency) => {
    if (efficiency >= 80) return 'high';
    if (efficiency >= 60) return 'medium';
    return 'low';
  };

  const handleEmployeeClick = (employee) => {
    navigate(`/efficiency/team/${roleSlug}/employee/${employee.id}`);
  };

  return (
    <div className="stage-employees-page">
      {/* Header */}
      <div className="stage-employees-header">
        <div className="header-nav">
          <button className="btn-back" onClick={() => navigate('/efficiency')}>
            ← Back to Pipeline Efficiency
          </button>
        </div>

        <div className="stage-header-content">
          <div className="stage-title-section">
            <h1>{roleData.roleName}</h1>
            <p className="stage-subtitle">{roleData.roleDescription}</p>
          </div>

          <div className="stage-metrics-summary">
            <div className="summary-metric">
              <span className="metric-value">{roleMetrics.efficiency}%</span>
              <span className="metric-label">Efficiency</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{roleMetrics.activeLoans}</span>
              <span className="metric-label">Active Loans</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{roleMetrics.avgResponseTime}</span>
              <span className="metric-label">Avg Response</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{roleMetrics.taskCompletionRate}%</span>
              <span className="metric-label">Task Completion</span>
            </div>
            <div className="summary-metric">
              <span className={`metric-value trend ${roleMetrics.trend >= 0 ? 'positive' : 'negative'}`}>
                {roleMetrics.trend >= 0 ? '↑' : '↓'} {Math.abs(roleMetrics.trend)}%
              </span>
              <span className="metric-label">Trend</span>
            </div>
          </div>
        </div>
      </div>

      {/* Employee Table */}
      <div className="employees-section">
        <h2>Team Members ({roleData.employees.length})</h2>
        <p className="section-description">Click on any employee to view their individual loan performance</p>

        <div className="employees-table-container">
          <table className="employees-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Efficiency</th>
                <th>Avg Response</th>
                <th>Task Completion</th>
                <th>Active Loans</th>
                <th>Trend</th>
              </tr>
            </thead>
            <tbody>
              {roleData.employees.map((employee) => (
                <tr
                  key={employee.id}
                  className="employee-row clickable"
                  onClick={() => handleEmployeeClick(employee)}
                >
                  <td className="employee-name-cell">
                    <div className="employee-info">
                      <div className="employee-avatar">{employee.avatar}</div>
                      <div className="employee-details">
                        <span className="employee-name">{employee.name}</span>
                        <span className="employee-id">{employee.id}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className={`efficiency-badge ${getEfficiencyClass(employee.efficiency)}`}>
                      {employee.efficiency}%
                    </div>
                  </td>
                  <td>{employee.avgResponseTime}</td>
                  <td>{employee.taskCompletionRate}%</td>
                  <td>{employee.activeLoans}</td>
                  <td>
                    <span className={`trend-indicator ${employee.trend >= 0 ? 'positive' : 'negative'}`}>
                      {employee.trend >= 0 ? '↑' : '↓'} {Math.abs(employee.trend)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Performance Insights */}
      <div className="insights-section">
        <h2>Team Insights</h2>
        <div className="insights-grid">
          <div className="insight-card">
            <div className="insight-icon">🏆</div>
            <div className="insight-content">
              <h3>Top Performer</h3>
              <p>{roleData.employees.reduce((a, b) => a.efficiency > b.efficiency ? a : b).name}</p>
              <span className="insight-detail">
                {roleData.employees.reduce((a, b) => a.efficiency > b.efficiency ? a : b).efficiency}% efficiency
              </span>
            </div>
          </div>

          <div className="insight-card">
            <div className="insight-icon">⚡</div>
            <div className="insight-content">
              <h3>Fastest Response</h3>
              <p>{roleData.employees.reduce((a, b) =>
                parseFloat(a.avgResponseTime) < parseFloat(b.avgResponseTime) ? a : b
              ).name}</p>
              <span className="insight-detail">
                {roleData.employees.reduce((a, b) =>
                  parseFloat(a.avgResponseTime) < parseFloat(b.avgResponseTime) ? a : b
                ).avgResponseTime} average
              </span>
            </div>
          </div>

          <div className="insight-card">
            <div className="insight-icon">📈</div>
            <div className="insight-content">
              <h3>Most Improved</h3>
              <p>{roleData.employees.reduce((a, b) => a.trend > b.trend ? a : b).name}</p>
              <span className="insight-detail positive">
                ↑ {roleData.employees.reduce((a, b) => a.trend > b.trend ? a : b).trend}% trend
              </span>
            </div>
          </div>

          <div className="insight-card">
            <div className="insight-icon">📋</div>
            <div className="insight-content">
              <h3>Highest Workload</h3>
              <p>{roleData.employees.reduce((a, b) => a.activeLoans > b.activeLoans ? a : b).name}</p>
              <span className="insight-detail">
                {roleData.employees.reduce((a, b) => a.activeLoans > b.activeLoans ? a : b).activeLoans} active loans
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default TeamRoleEmployees;
