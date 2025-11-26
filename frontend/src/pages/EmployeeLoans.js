import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './EmployeeLoans.css';

// Mock employee data with their loans - keyed by employee ID
const employeeLoanData = {
  // Loan Officers
  'LO001': {
    name: 'Timothy Loss',
    role: 'Loan Officer',
    employeeId: 'LO001',
    efficiency: 92,
    avgTime: '1.8 days',
    conversionRate: 48,
    volume: 18,
    bottlenecks: 0,
    trend: 12,
    avatar: 'TL',
    loans: [
      { id: 'TST-0003', borrowerName: 'Sandra & Robert Chen', loanAmount: 650000, program: 'Conventional 30yr Fixed', stage: 'In Processing', daysInStage: 15, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0005', borrowerName: 'Jennifer Martinez', loanAmount: 520000, program: 'FHA 30yr Fixed', stage: 'In Processing', daysInStage: 8, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0009', borrowerName: 'David & Lisa Thompson', loanAmount: 580000, program: 'VA 30yr Fixed', stage: 'Conditional Approval', daysInStage: 5, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0015', borrowerName: 'Richard & Carol White', loanAmount: 425000, program: 'Conventional 30yr Fixed', stage: 'Clear to Close', daysInStage: 2, status: 'Ready', issue: null, outcome: null },
      { id: 'TST-0020', borrowerName: 'Thomas & Helen Garcia', loanAmount: 385000, program: 'FHA 30yr Fixed', stage: 'Funded', daysInStage: 0, status: 'Closed', issue: null, outcome: 'positive' },
      { id: 'TST-0022', borrowerName: 'Mark & Laura Taylor', loanAmount: 710000, program: 'Jumbo 30yr Fixed', stage: 'Funded', daysInStage: 0, status: 'Closed', issue: null, outcome: 'positive' }
    ]
  },
  'LO002': {
    name: 'Sarah Mitchell',
    role: 'Loan Officer',
    employeeId: 'LO002',
    efficiency: 88,
    avgTime: '2.1 days',
    conversionRate: 45,
    volume: 15,
    bottlenecks: 1,
    trend: 8,
    avatar: 'SM',
    loans: [
      { id: 'TST-0004', borrowerName: 'Michael & Amy Johnson', loanAmount: 485000, program: 'Conventional 30yr Fixed', stage: 'In Processing', daysInStage: 22, status: 'Delayed', issue: 'Missing employment verification - 3rd request sent', outcome: 'negative' },
      { id: 'TST-0010', borrowerName: 'Brandon & Jessica Lee', loanAmount: 390000, program: 'FHA 30yr Fixed', stage: 'Conditional Approval', daysInStage: 8, status: 'Needs Attention', issue: 'Gift letter documentation incomplete', outcome: null },
      { id: 'TST-0016', borrowerName: 'Eric & Diana Harris', loanAmount: 445000, program: 'Conventional 15yr Fixed', stage: 'Clear to Close', daysInStage: 3, status: 'Ready', issue: null, outcome: null },
      { id: 'TST-0021', borrowerName: 'Steven & Nancy Brown', loanAmount: 550000, program: 'VA 30yr Fixed', stage: 'Funded', daysInStage: 0, status: 'Closed', issue: null, outcome: 'positive' }
    ]
  },
  'LO003': {
    name: 'Mike Johnson',
    role: 'Loan Officer',
    employeeId: 'LO003',
    efficiency: 78,
    avgTime: '3.2 days',
    conversionRate: 35,
    volume: 12,
    bottlenecks: 0,
    trend: -3,
    avatar: 'MJ',
    loans: [
      { id: 'TST-0006', borrowerName: 'Kevin & Rebecca Wilson', loanAmount: 315000, program: 'FHA 30yr Fixed', stage: 'In Processing', daysInStage: 18, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0011', borrowerName: 'Andrew & Patricia Moore', loanAmount: 620000, program: 'Conventional 30yr Fixed', stage: 'Conditional Approval', daysInStage: 12, status: 'Delayed', issue: 'Appraisal came in low - contesting value', outcome: 'negative' },
      { id: 'TST-0023', borrowerName: 'Joseph & Virginia Adams', loanAmount: 475000, program: 'Conventional 30yr Fixed', stage: 'Funded', daysInStage: 0, status: 'Closed', issue: null, outcome: 'positive' }
    ]
  },
  // Processors
  'PR001': {
    name: 'Jessica Marlow',
    role: 'Processor',
    employeeId: 'PR001',
    efficiency: 72,
    avgTime: '10.5 days',
    conversionRate: 88,
    volume: 6,
    bottlenecks: 3,
    trend: -5,
    avatar: 'JM',
    loans: [
      { id: 'TST-0003', borrowerName: 'Sandra & Robert Chen', loanAmount: 650000, program: 'Conventional 30yr Fixed', stage: 'In Processing', daysInStage: 15, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0004', borrowerName: 'Michael & Amy Johnson', loanAmount: 485000, program: 'Conventional 30yr Fixed', stage: 'In Processing', daysInStage: 22, status: 'Delayed', issue: 'Missing VOE - employer unresponsive', outcome: 'negative' },
      { id: 'TST-0005', borrowerName: 'Jennifer Martinez', loanAmount: 520000, program: 'FHA 30yr Fixed', stage: 'In Processing', daysInStage: 8, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0006', borrowerName: 'Kevin & Rebecca Wilson', loanAmount: 315000, program: 'FHA 30yr Fixed', stage: 'In Processing', daysInStage: 18, status: 'Delayed', issue: 'Bank statements have unexplained deposits', outcome: 'negative' },
      { id: 'TST-0007', borrowerName: 'Jason & Michelle Scott', loanAmount: 725000, program: 'Jumbo 30yr Fixed', stage: 'In Processing', daysInStage: 12, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0008', borrowerName: 'Christopher & Amanda Davis', loanAmount: 395000, program: 'Conventional 30yr Fixed', stage: 'In Processing', daysInStage: 5, status: 'On Track', issue: null, outcome: null }
    ]
  },
  'PR002': {
    name: 'Jennifer Lopez',
    role: 'Processor',
    employeeId: 'PR002',
    efficiency: 58,
    avgTime: '15.2 days',
    conversionRate: 82,
    volume: 4,
    bottlenecks: 2,
    trend: -12,
    avatar: 'JL',
    loans: [
      { id: 'TST-0025', borrowerName: 'William & Dorothy Clark', loanAmount: 435000, program: 'Conventional 30yr Fixed', stage: 'In Processing', daysInStage: 25, status: 'Critical', issue: 'Title search revealed undisclosed lien - working with attorney', outcome: 'negative' },
      { id: 'TST-0026', borrowerName: 'Daniel & Elizabeth Martin', loanAmount: 510000, program: 'VA 30yr Fixed', stage: 'In Processing', daysInStage: 18, status: 'Delayed', issue: 'Waiting on VA COE verification', outcome: 'negative' },
      { id: 'TST-0027', borrowerName: 'Charles & Mary Robinson', loanAmount: 380000, program: 'FHA 30yr Fixed', stage: 'In Processing', daysInStage: 14, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0028', borrowerName: 'Matthew & Sarah Walker', loanAmount: 590000, program: 'Conventional 30yr Fixed', stage: 'In Processing', daysInStage: 8, status: 'On Track', issue: null, outcome: null }
    ]
  },
  // Underwriters
  'UW201': {
    name: 'Danielle Brooks',
    role: 'Underwriter',
    employeeId: 'UW201',
    efficiency: 82,
    avgTime: '6.5 days',
    conversionRate: 95,
    volume: 2,
    bottlenecks: 0,
    trend: 8,
    avatar: 'DB',
    loans: [
      { id: 'TST-0009', borrowerName: 'David & Lisa Thompson', loanAmount: 580000, program: 'VA 30yr Fixed', stage: 'Conditional Approval', daysInStage: 5, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0010', borrowerName: 'Brandon & Jessica Lee', loanAmount: 390000, program: 'FHA 30yr Fixed', stage: 'Conditional Approval', daysInStage: 8, status: 'On Track', issue: null, outcome: null }
    ]
  },
  'UW202': {
    name: 'Samuel Price',
    role: 'Underwriter',
    employeeId: 'UW202',
    efficiency: 75,
    avgTime: '8.2 days',
    conversionRate: 92,
    volume: 2,
    bottlenecks: 1,
    trend: 3,
    avatar: 'SP',
    loans: [
      { id: 'TST-0011', borrowerName: 'Andrew & Patricia Moore', loanAmount: 620000, program: 'Conventional 30yr Fixed', stage: 'Conditional Approval', daysInStage: 12, status: 'Delayed', issue: 'Appraisal review - value dispute in progress', outcome: 'negative' },
      { id: 'TST-0012', borrowerName: 'Ryan & Katherine Young', loanAmount: 455000, program: 'Conventional 30yr Fixed', stage: 'Conditional Approval', daysInStage: 6, status: 'On Track', issue: null, outcome: null }
    ]
  },
  'UW203': {
    name: 'Helen Rogers',
    role: 'Underwriter',
    employeeId: 'UW203',
    efficiency: 68,
    avgTime: '9.5 days',
    conversionRate: 90,
    volume: 1,
    bottlenecks: 2,
    trend: -2,
    avatar: 'HR',
    loans: [
      { id: 'TST-0017', borrowerName: 'Paul & Linda Jackson', loanAmount: 680000, program: 'Jumbo 30yr Fixed', stage: 'Suspended', daysInStage: 15, status: 'Critical', issue: 'DTI too high - borrower needs to pay off car loan', outcome: 'negative' }
    ]
  },
  'UW204': {
    name: 'Kelvin Abdul',
    role: 'Underwriter',
    employeeId: 'UW204',
    efficiency: 62,
    avgTime: '11.2 days',
    conversionRate: 88,
    volume: 2,
    bottlenecks: 1,
    trend: -5,
    avatar: 'KA',
    loans: [
      { id: 'TST-0013', borrowerName: 'George & Jennifer Anderson', loanAmount: 545000, program: 'Conventional 30yr Fixed', stage: 'Conditional Approval', daysInStage: 10, status: 'On Track', issue: null, outcome: null },
      { id: 'TST-0018', borrowerName: 'Larry & Susan Baker', loanAmount: 410000, program: 'FHA 30yr Fixed', stage: 'Suspended', daysInStage: 8, status: 'Delayed', issue: 'Credit score dropped - new inquiry appeared', outcome: 'negative' }
    ]
  },
  'UW205': {
    name: 'Patricia Donovan',
    role: 'Underwriter',
    employeeId: 'UW205',
    efficiency: 70,
    avgTime: '8.8 days',
    conversionRate: 91,
    volume: 1,
    bottlenecks: 0,
    trend: 5,
    avatar: 'PD',
    loans: [
      { id: 'TST-0014', borrowerName: 'Kenneth & Barbara Collins', loanAmount: 365000, program: 'VA 30yr Fixed', stage: 'Conditional Approval', daysInStage: 4, status: 'On Track', issue: null, outcome: null }
    ]
  },
  // Closers
  'CL001': {
    name: 'Tom Wilson',
    role: 'Closer',
    employeeId: 'CL001',
    efficiency: 92,
    avgTime: '2.8 days',
    conversionRate: 98,
    volume: 5,
    bottlenecks: 0,
    trend: 18,
    avatar: 'TW',
    loans: [
      { id: 'TST-0015', borrowerName: 'Richard & Carol White', loanAmount: 425000, program: 'Conventional 30yr Fixed', stage: 'Clear to Close', daysInStage: 2, status: 'Ready', issue: null, outcome: null },
      { id: 'TST-0016', borrowerName: 'Eric & Diana Harris', loanAmount: 445000, program: 'Conventional 15yr Fixed', stage: 'Clear to Close', daysInStage: 3, status: 'Ready', issue: null, outcome: null },
      { id: 'TST-0019', borrowerName: 'Roger & Betty Lewis', loanAmount: 495000, program: 'Conventional 30yr Fixed', stage: 'Clear to Close', daysInStage: 1, status: 'Ready', issue: null, outcome: null },
      { id: 'TST-0020', borrowerName: 'Thomas & Helen Garcia', loanAmount: 385000, program: 'FHA 30yr Fixed', stage: 'Funded', daysInStage: 0, status: 'Closed', issue: null, outcome: 'positive' },
      { id: 'TST-0021', borrowerName: 'Steven & Nancy Brown', loanAmount: 550000, program: 'VA 30yr Fixed', stage: 'Funded', daysInStage: 0, status: 'Closed', issue: null, outcome: 'positive' }
    ]
  },
  'CL002': {
    name: 'Linda Martinez',
    role: 'Closer',
    employeeId: 'CL002',
    efficiency: 85,
    avgTime: '3.8 days',
    conversionRate: 94,
    volume: 2,
    bottlenecks: 1,
    trend: 10,
    avatar: 'LM',
    loans: [
      { id: 'TST-0022', borrowerName: 'Mark & Laura Taylor', loanAmount: 710000, program: 'Jumbo 30yr Fixed', stage: 'Funded', daysInStage: 0, status: 'Closed', issue: null, outcome: 'positive' },
      { id: 'TST-0023', borrowerName: 'Joseph & Virginia Adams', loanAmount: 475000, program: 'Conventional 30yr Fixed', stage: 'Funded', daysInStage: 0, status: 'Closed', issue: null, outcome: 'positive' }
    ]
  }
};

// Stage name mapping from slug
const stageNameFromSlug = {
  'lead-generation': 'Lead Generation',
  'pre-qualification': 'Pre-Qualification',
  'application': 'Application',
  'processing': 'Processing',
  'underwriting': 'Underwriting',
  'clear-to-close': 'Clear to Close',
  'closing': 'Closing'
};

function EmployeeLoans() {
  const { stageSlug, employeeId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setTimeout(() => setLoading(false), 300);
  }, []);

  const employeeData = employeeLoanData[employeeId];
  const stageName = stageNameFromSlug[stageSlug] || stageSlug;

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const getStatusClass = (status) => {
    switch (status) {
      case 'On Track':
      case 'Ready':
      case 'Closed':
        return 'status-good';
      case 'Needs Attention':
      case 'Delayed':
        return 'status-warning';
      case 'Critical':
        return 'status-critical';
      default:
        return '';
    }
  };

  const getOutcomeIcon = (outcome) => {
    if (outcome === 'positive') return '✓';
    if (outcome === 'negative') return '⚠';
    return '';
  };

  const getEfficiencyClass = (efficiency) => {
    if (efficiency >= 80) return 'high';
    if (efficiency >= 60) return 'medium';
    return 'low';
  };

  if (loading) {
    return (
      <div className="employee-loans-page">
        <div className="loading-spinner">Loading loan data...</div>
      </div>
    );
  }

  if (!employeeData) {
    return (
      <div className="employee-loans-page">
        <div className="error-state">
          <h2>Employee Not Found</h2>
          <p>The requested employee "{employeeId}" was not found.</p>
          <button onClick={() => navigate(`/efficiency/stage/${stageSlug}`)}>
            ← Back to {stageName}
          </button>
        </div>
      </div>
    );
  }

  // Calculate loan stats
  const totalLoans = employeeData.loans.length;
  const issueLoans = employeeData.loans.filter(l => l.issue).length;
  const closedLoans = employeeData.loans.filter(l => l.status === 'Closed').length;
  const avgDaysInStage = Math.round(
    employeeData.loans.filter(l => l.status !== 'Closed').reduce((sum, l) => sum + l.daysInStage, 0) /
    employeeData.loans.filter(l => l.status !== 'Closed').length || 0
  );

  return (
    <div className="employee-loans-page">
      {/* Header */}
      <div className="employee-loans-header">
        <div className="header-nav">
          <button className="btn-back" onClick={() => navigate(`/efficiency/stage/${stageSlug}`)}>
            ← Back to {stageName}
          </button>
        </div>

        <div className="employee-header-content">
          <div className="employee-profile">
            <div className="employee-avatar-large">{employeeData.avatar}</div>
            <div className="employee-title-section">
              <h1>{employeeData.name}</h1>
              <p className="employee-role">{employeeData.role} • {employeeData.employeeId}</p>
            </div>
          </div>

          <div className="employee-metrics-summary">
            <div className="summary-metric">
              <span className={`metric-value efficiency-badge ${getEfficiencyClass(employeeData.efficiency)}`}>
                {employeeData.efficiency}%
              </span>
              <span className="metric-label">Efficiency</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{employeeData.avgTime}</span>
              <span className="metric-label">Avg. Time</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{employeeData.conversionRate}%</span>
              <span className="metric-label">Conv. Rate</span>
            </div>
            <div className="summary-metric">
              <span className="metric-value">{employeeData.volume}</span>
              <span className="metric-label">Volume</span>
            </div>
            <div className="summary-metric">
              <span className={`metric-value trend ${employeeData.trend >= 0 ? 'positive' : 'negative'}`}>
                {employeeData.trend >= 0 ? '↑' : '↓'} {Math.abs(employeeData.trend)}%
              </span>
              <span className="metric-label">Trend</span>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="quick-stats-bar">
        <div className="quick-stat">
          <span className="stat-number">{totalLoans}</span>
          <span className="stat-label">Total Loans</span>
        </div>
        <div className="quick-stat">
          <span className="stat-number good">{closedLoans}</span>
          <span className="stat-label">Closed</span>
        </div>
        <div className="quick-stat">
          <span className="stat-number warning">{issueLoans}</span>
          <span className="stat-label">With Issues</span>
        </div>
        <div className="quick-stat">
          <span className="stat-number">{avgDaysInStage}</span>
          <span className="stat-label">Avg Days in Stage</span>
        </div>
      </div>

      {/* Loans Table */}
      <div className="loans-section">
        <h2>Loan Files ({totalLoans})</h2>
        <p className="section-description">
          Review individual loan performance to identify what drove positive or negative outcomes
        </p>

        <div className="loans-table-container">
          <table className="loans-table">
            <thead>
              <tr>
                <th>Loan #</th>
                <th>Borrower</th>
                <th>Loan Amount</th>
                <th>Program</th>
                <th>Stage</th>
                <th>Days</th>
                <th>Status</th>
                <th>Issue/Notes</th>
              </tr>
            </thead>
            <tbody>
              {employeeData.loans.map((loan) => (
                <tr
                  key={loan.id}
                  className={`loan-row ${loan.issue ? 'has-issue' : ''} ${loan.outcome === 'positive' ? 'positive-outcome' : ''}`}
                >
                  <td className="loan-number-cell">
                    <span className="loan-number">{loan.id}</span>
                    {loan.outcome && (
                      <span className={`outcome-icon ${loan.outcome}`}>
                        {getOutcomeIcon(loan.outcome)}
                      </span>
                    )}
                  </td>
                  <td className="borrower-cell">
                    <span className="borrower-name">{loan.borrowerName}</span>
                  </td>
                  <td className="amount-cell">{formatCurrency(loan.loanAmount)}</td>
                  <td className="program-cell">{loan.program}</td>
                  <td className="stage-cell">
                    <span className="stage-badge">{loan.stage}</span>
                  </td>
                  <td className="days-cell">
                    <span className={loan.daysInStage > 14 ? 'days-warning' : ''}>
                      {loan.daysInStage}
                    </span>
                  </td>
                  <td className="status-cell">
                    <span className={`status-badge ${getStatusClass(loan.status)}`}>
                      {loan.status}
                    </span>
                  </td>
                  <td className="issue-cell">
                    {loan.issue ? (
                      <div className="issue-text">{loan.issue}</div>
                    ) : (
                      <span className="no-issue">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Performance Summary */}
      <div className="performance-summary-section">
        <h2>Performance Analysis</h2>
        <div className="analysis-grid">
          <div className="analysis-card positive">
            <div className="analysis-header">
              <span className="analysis-icon">✓</span>
              <h3>Positive Factors</h3>
            </div>
            <ul>
              {employeeData.loans.filter(l => l.outcome === 'positive').length > 0 && (
                <li>{employeeData.loans.filter(l => l.outcome === 'positive').length} loans closed successfully</li>
              )}
              {employeeData.efficiency >= 80 && <li>Efficiency rating above 80%</li>}
              {employeeData.trend > 0 && <li>Trending upward by {employeeData.trend}%</li>}
              {employeeData.bottlenecks === 0 && <li>No active bottlenecks</li>}
            </ul>
          </div>

          <div className="analysis-card negative">
            <div className="analysis-header">
              <span className="analysis-icon">⚠</span>
              <h3>Areas for Improvement</h3>
            </div>
            <ul>
              {issueLoans > 0 && <li>{issueLoans} loans with active issues requiring attention</li>}
              {employeeData.efficiency < 70 && <li>Efficiency below 70% - review workflow</li>}
              {employeeData.trend < 0 && <li>Trending downward by {Math.abs(employeeData.trend)}%</li>}
              {employeeData.bottlenecks > 0 && <li>{employeeData.bottlenecks} bottleneck(s) to address</li>}
              {avgDaysInStage > 10 && <li>Average time in stage exceeds 10 days</li>}
            </ul>
          </div>

          <div className="analysis-card recommendations">
            <div className="analysis-header">
              <span className="analysis-icon">💡</span>
              <h3>Recommendations</h3>
            </div>
            <ul>
              {issueLoans > 0 && (
                <li>Prioritize resolving issues on {issueLoans} stalled loans</li>
              )}
              {employeeData.efficiency < 80 && (
                <li>Schedule coaching session to improve processing time</li>
              )}
              {employeeData.conversionRate < 85 && (
                <li>Review conversion rate factors - follow-up cadence may need adjustment</li>
              )}
              <li>Weekly pipeline review recommended for proactive issue detection</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export default EmployeeLoans;
