import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './StageEmployees.css';

// Mock data for employees by stage
const stageEmployeesData = {
  'lead-generation': {
    stageName: 'Lead Generation',
    roleTitle: 'Loan Officers',
    employees: [
      { id: 'LO001', name: 'Timothy Loss', efficiency: 92, avgTime: '1.8 days', conversionRate: 48, volume: 18, bottlenecks: 0, trend: 12, avatar: 'TL' },
      { id: 'LO002', name: 'Sarah Mitchell', efficiency: 88, avgTime: '2.1 days', conversionRate: 45, volume: 15, bottlenecks: 1, trend: 8, avatar: 'SM' },
      { id: 'LO003', name: 'Mike Johnson', efficiency: 78, avgTime: '3.2 days', conversionRate: 35, volume: 12, bottlenecks: 0, trend: -3, avatar: 'MJ' }
    ]
  },
  'pre-qualification': {
    stageName: 'Pre-Qualification',
    roleTitle: 'Loan Officers',
    employees: [
      { id: 'LO001', name: 'Timothy Loss', efficiency: 85, avgTime: '3.5 days', conversionRate: 72, volume: 12, bottlenecks: 1, trend: 5, avatar: 'TL' },
      { id: 'LO002', name: 'Sarah Mitchell', efficiency: 70, avgTime: '4.8 days', conversionRate: 65, volume: 7, bottlenecks: 2, trend: -5, avatar: 'SM' }
    ]
  },
  'application': {
    stageName: 'Application',
    roleTitle: 'Loan Officers',
    employees: [
      { id: 'LO001', name: 'Timothy Loss', efficiency: 88, avgTime: '4.5 days', conversionRate: 82, volume: 8, bottlenecks: 1, trend: 15, avatar: 'TL' },
      { id: 'LO002', name: 'Sarah Mitchell', efficiency: 75, avgTime: '6.2 days', conversionRate: 74, volume: 5, bottlenecks: 1, trend: 8, avatar: 'SM' }
    ]
  },
  'processing': {
    stageName: 'Processing',
    roleTitle: 'Processors',
    employees: [
      { id: 'PR001', name: 'Jessica Marlow', efficiency: 72, avgTime: '10.5 days', conversionRate: 88, volume: 6, bottlenecks: 3, trend: -5, avatar: 'JM' },
      { id: 'PR002', name: 'Jennifer Lopez', efficiency: 58, avgTime: '15.2 days', conversionRate: 82, volume: 4, bottlenecks: 2, trend: -12, avatar: 'JL' }
    ]
  },
  'underwriting': {
    stageName: 'Underwriting',
    roleTitle: 'Underwriters',
    employees: [
      { id: 'UW201', name: 'Danielle Brooks', efficiency: 82, avgTime: '6.5 days', conversionRate: 95, volume: 2, bottlenecks: 0, trend: 8, avatar: 'DB' },
      { id: 'UW202', name: 'Samuel Price', efficiency: 75, avgTime: '8.2 days', conversionRate: 92, volume: 2, bottlenecks: 1, trend: 3, avatar: 'SP' },
      { id: 'UW203', name: 'Helen Rogers', efficiency: 68, avgTime: '9.5 days', conversionRate: 90, volume: 1, bottlenecks: 2, trend: -2, avatar: 'HR' },
      { id: 'UW204', name: 'Kelvin Abdul', efficiency: 62, avgTime: '11.2 days', conversionRate: 88, volume: 2, bottlenecks: 1, trend: -5, avatar: 'KA' },
      { id: 'UW205', name: 'Patricia Donovan', efficiency: 70, avgTime: '8.8 days', conversionRate: 91, volume: 1, bottlenecks: 0, trend: 5, avatar: 'PD' }
    ]
  },
  'clear-to-close': {
    stageName: 'Clear to Close',
    roleTitle: 'Closers',
    employees: [
      { id: 'CL001', name: 'Tom Wilson', efficiency: 92, avgTime: '2.8 days', conversionRate: 98, volume: 5, bottlenecks: 0, trend: 18, avatar: 'TW' },
      { id: 'CL002', name: 'Linda Martinez', efficiency: 85, avgTime: '3.8 days', conversionRate: 94, volume: 2, bottlenecks: 1, trend: 10, avatar: 'LM' }
    ]
  },
  'closing': {
    stageName: 'Closing',
    roleTitle: 'Closers',
    employees: [
      { id: 'CL001', name: 'Tom Wilson', efficiency: 95, avgTime: '1.5 days', conversionRate: 99, volume: 5, bottlenecks: 0, trend: 12, avatar: 'TW' },
      { id: 'CL002', name: 'Linda Martinez', efficiency: 88, avgTime: '2.2 days', conversionRate: 97, volume: 2, bottlenecks: 0, trend: 8, avatar: 'LM' }
    ]
  }
};

// Stage aggregate data for header
const stageMetricsData = {
  'lead-generation': { efficiency: 85, avgTime: '2.3 days', conversionRate: 42, volume: 45, bottlenecks: 1, trend: 8 },
  'pre-qualification': { efficiency: 72, avgTime: '4.1 days', conversionRate: 68, volume: 19, bottlenecks: 3, trend: -3 },
  'application': { efficiency: 81, avgTime: '5.2 days', conversionRate: 78, volume: 13, bottlenecks: 2, trend: 12 },
  'processing': { efficiency: 65, avgTime: '12.5 days', conversionRate: 85, volume: 10, bottlenecks: 5, trend: -8 },
  'underwriting': { efficiency: 70, avgTime: '8.7 days', conversionRate: 92, volume: 8, bottlenecks: 4, trend: 2 },
  'clear-to-close': { efficiency: 88, avgTime: '3.2 days', conversionRate: 96, volume: 7, bottlenecks: 1, trend: 15 },
  'closing': { efficiency: 92, avgTime: '1.8 days', conversionRate: 98, volume: 7, bottlenecks: 0, trend: 10 }
};

function StageEmployees() {
  const { stageSlug } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setTimeout(() => setLoading(false), 300);
  }, []);

  const stageData = stageEmployeesData[stageSlug];
  const stageMetrics = stageMetricsData[stageSlug];

  if (loading) {
    return (
      <div className="stage-employees-page">
        <div className="loading-spinner">Loading employee data...</div>
      </div>
    );
  }

  if (!stageData) {
    return (
      <div className="stage-employees-page">
        <div className="error-state">
          <h2>Stage Not Found</h2>
          <p>The requested stage "{stageSlug}" was not found.</p>
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
    navigate(`/efficiency/stage/${stageSlug}/employee/${employee.id}`);
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
            <h1>{stageData.stageName}</h1>
            <p className="stage-subtitle">{stageData.roleTitle} Performance</p>
          </div>

          <div className="stage-metrics-summary">
            <div className="summary-metric">
              <span className="metric-value">{stageMetrics.efficiency}%</span>
              <span className="metric-label">Efficiency</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{stageMetrics.avgTime}</span>
              <span className="metric-label">Avg. Time</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{stageMetrics.conversionRate}%</span>
              <span className="metric-label">Conv. Rate</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{stageMetrics.volume}</span>
              <span className="metric-label">Volume</span>
            </div>
            <div className="summary-metric">
              <span className={`metric-value trend ${stageMetrics.trend >= 0 ? 'positive' : 'negative'}`}>
                {stageMetrics.trend >= 0 ? '↑' : '↓'} {Math.abs(stageMetrics.trend)}%
              </span>
              <span className="metric-label">Trend</span>
            </div>
          </div>
        </div>
      </div>

      {/* Employee Table */}
      <div className="employees-section">
        <h2>{stageData.roleTitle} ({stageData.employees.length})</h2>
        <p className="section-description">Click on any employee to view their individual loan performance</p>

        <div className="employees-table-container">
          <table className="employees-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Efficiency</th>
                <th>Avg. Time</th>
                <th>Conv. Rate</th>
                <th>Volume</th>
                <th>Bottlenecks</th>
                <th>Trend</th>
              </tr>
            </thead>
            <tbody>
              {stageData.employees.map((employee) => (
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
                  <td>{employee.avgTime}</td>
                  <td>{employee.conversionRate}%</td>
                  <td>{employee.volume}</td>
                  <td>
                    <span className={`bottleneck-count ${employee.bottlenecks > 0 ? 'has-issues' : 'no-issues'}`}>
                      {employee.bottlenecks}
                    </span>
                  </td>
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
        <h2>Performance Insights</h2>
        <div className="insights-grid">
          <div className="insight-card">
            <div className="insight-icon">🏆</div>
            <div className="insight-content">
              <h3>Top Performer</h3>
              <p>{stageData.employees.reduce((a, b) => a.efficiency > b.efficiency ? a : b).name}</p>
              <span className="insight-detail">
                {stageData.employees.reduce((a, b) => a.efficiency > b.efficiency ? a : b).efficiency}% efficiency
              </span>
            </div>
          </div>

          <div className="insight-card">
            <div className="insight-icon">⚡</div>
            <div className="insight-content">
              <h3>Fastest Processing</h3>
              <p>{stageData.employees.reduce((a, b) =>
                parseFloat(a.avgTime) < parseFloat(b.avgTime) ? a : b
              ).name}</p>
              <span className="insight-detail">
                {stageData.employees.reduce((a, b) =>
                  parseFloat(a.avgTime) < parseFloat(b.avgTime) ? a : b
                ).avgTime} average
              </span>
            </div>
          </div>

          <div className="insight-card">
            <div className="insight-icon">📈</div>
            <div className="insight-content">
              <h3>Most Improved</h3>
              <p>{stageData.employees.reduce((a, b) => a.trend > b.trend ? a : b).name}</p>
              <span className="insight-detail positive">
                ↑ {stageData.employees.reduce((a, b) => a.trend > b.trend ? a : b).trend}% trend
              </span>
            </div>
          </div>

          <div className="insight-card">
            <div className="insight-icon">🎯</div>
            <div className="insight-content">
              <h3>Highest Volume</h3>
              <p>{stageData.employees.reduce((a, b) => a.volume > b.volume ? a : b).name}</p>
              <span className="insight-detail">
                {stageData.employees.reduce((a, b) => a.volume > b.volume ? a : b).volume} loans
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default StageEmployees;
