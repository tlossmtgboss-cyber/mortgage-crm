import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './BottleneckLoans.css';
import { toast } from '../utils/toast';

// Mock data for bottlenecks with affected loans
const bottleneckData = {
  '1': {
    id: 1,
    issue: 'Missing Documents',
    stage: 'Processing',
    severity: 'high',
    affectedLoans: 8,
    avgDelay: '4.5 days',
    suggestedAction: 'Send automated document reminder emails',
    loans: [
      { id: 'L-2024-001', borrowerName: 'Sarah Johnson', loanAmount: 425000, processor: 'Jessica Marlow', missingItems: ['Pay Stubs (last 2 months)', 'Bank Statements', 'W-2 Forms (2023)'], daysDelayed: 5, lastContact: '2 days ago' },
      { id: 'L-2024-012', borrowerName: 'Michael Chen', loanAmount: 380000, processor: 'Jennifer Lopez', missingItems: ['Tax Returns (2022-2023)', 'Proof of Assets'], daysDelayed: 4, lastContact: '3 days ago' },
      { id: 'L-2024-018', borrowerName: 'Emily Rodriguez', loanAmount: 295000, processor: 'Jessica Marlow', missingItems: ['Employment Verification', 'HOA Documents'], daysDelayed: 3, lastContact: '1 day ago' },
      { id: 'L-2024-023', borrowerName: 'David Martinez', loanAmount: 550000, processor: 'Jennifer Lopez', missingItems: ['Gift Letter', 'Source of Funds Documentation'], daysDelayed: 6, lastContact: '4 days ago' },
      { id: 'L-2024-029', borrowerName: 'Jennifer Lee', loanAmount: 340000, processor: 'Jessica Marlow', missingItems: ['Divorce Decree', 'Child Support Documentation'], daysDelayed: 4, lastContact: '2 days ago' },
      { id: 'L-2024-031', borrowerName: 'Robert Taylor', loanAmount: 620000, processor: 'Jennifer Lopez', missingItems: ['Business Tax Returns', 'Profit & Loss Statement'], daysDelayed: 5, lastContact: '3 days ago' },
      { id: 'L-2024-035', borrowerName: 'Amanda Wilson', loanAmount: 475000, processor: 'Jessica Marlow', missingItems: ['Homeowners Insurance', 'Property Appraisal'], daysDelayed: 3, lastContact: '1 day ago' },
      { id: 'L-2024-037', borrowerName: 'James Brown', loanAmount: 410000, processor: 'Jennifer Lopez', missingItems: ['Retirement Account Statements', 'Investment Documentation'], daysDelayed: 7, lastContact: '5 days ago' }
    ]
  },
  '2': {
    id: 2,
    issue: 'Income Verification Delays',
    stage: 'Pre-Qualification',
    severity: 'high',
    affectedLoans: 6,
    avgDelay: '3.2 days',
    suggestedAction: 'Follow up with employers directly',
    loans: [
      { id: 'L-2024-008', borrowerName: 'Lisa Anderson', loanAmount: 385000, processor: 'Jessica Marlow', missingItems: ['Employer Verification Response'], daysDelayed: 4, lastContact: '2 days ago' },
      { id: 'L-2024-015', borrowerName: 'Christopher Garcia', loanAmount: 290000, processor: 'Jennifer Lopez', missingItems: ['Employment Letter', 'Salary Confirmation'], daysDelayed: 3, lastContact: '1 day ago' },
      { id: 'L-2024-022', borrowerName: 'Patricia Moore', loanAmount: 445000, processor: 'Jessica Marlow', missingItems: ['Commission Income Verification'], daysDelayed: 5, lastContact: '3 days ago' },
      { id: 'L-2024-026', borrowerName: 'Daniel Thomas', loanAmount: 315000, processor: 'Jennifer Lopez', missingItems: ['Self-Employment Verification'], daysDelayed: 2, lastContact: 'Today' },
      { id: 'L-2024-033', borrowerName: 'Nancy Jackson', loanAmount: 520000, processor: 'Jessica Marlow', missingItems: ['Bonus Income Documentation'], daysDelayed: 3, lastContact: '2 days ago' },
      { id: 'L-2024-039', borrowerName: 'Kevin White', loanAmount: 360000, processor: 'Jennifer Lopez', missingItems: ['Overtime Income Verification'], daysDelayed: 4, lastContact: '3 days ago' }
    ]
  },
  '3': {
    id: 3,
    issue: 'Appraisal Review Backlog',
    stage: 'Underwriting',
    severity: 'medium',
    affectedLoans: 5,
    avgDelay: '2.8 days',
    suggestedAction: 'Escalate to senior underwriters',
    loans: [
      { id: 'L-2024-041', borrowerName: 'George Miller', loanAmount: 525000, processor: 'Danielle Brooks', missingItems: ['Appraisal Review Pending'], daysDelayed: 3, lastContact: '1 day ago' },
      { id: 'L-2024-044', borrowerName: 'Sandra Davis', loanAmount: 480000, processor: 'Samuel Price', missingItems: ['Appraisal Value Dispute'], daysDelayed: 4, lastContact: '2 days ago' },
      { id: 'L-2024-047', borrowerName: 'William Harris', loanAmount: 610000, processor: 'Danielle Brooks', missingItems: ['Comparable Sales Review'], daysDelayed: 2, lastContact: 'Today' },
      { id: 'L-2024-050', borrowerName: 'Betty Robinson', loanAmount: 395000, processor: 'Helen Rogers', missingItems: ['Property Condition Report'], daysDelayed: 3, lastContact: '1 day ago' },
      { id: 'L-2024-053', borrowerName: 'Charles Lewis', loanAmount: 550000, processor: 'Samuel Price', missingItems: ['Second Appraisal Required'], daysDelayed: 2, lastContact: 'Today' }
    ]
  },
  '4': {
    id: 4,
    issue: 'Credit Report Disputes',
    stage: 'Processing',
    severity: 'medium',
    affectedLoans: 4,
    avgDelay: '5.1 days',
    suggestedAction: 'Expedite credit bureau responses',
    loans: [
      { id: 'L-2024-055', borrowerName: 'Dorothy Clark', loanAmount: 365000, processor: 'Jessica Marlow', missingItems: ['Credit Dispute Resolution - Equifax'], daysDelayed: 6, lastContact: '4 days ago' },
      { id: 'L-2024-058', borrowerName: 'Richard Walker', loanAmount: 420000, processor: 'Jennifer Lopez', missingItems: ['Credit Dispute Resolution - TransUnion'], daysDelayed: 5, lastContact: '3 days ago' },
      { id: 'L-2024-061', borrowerName: 'Susan Hall', loanAmount: 510000, processor: 'Jessica Marlow', missingItems: ['Credit Dispute Resolution - Experian'], daysDelayed: 4, lastContact: '2 days ago' },
      { id: 'L-2024-064', borrowerName: 'Joseph Young', loanAmount: 385000, processor: 'Jennifer Lopez', missingItems: ['Multiple Bureau Disputes Pending'], daysDelayed: 5, lastContact: '3 days ago' }
    ]
  },
  '5': {
    id: 5,
    issue: 'Incomplete Applications',
    stage: 'Application',
    severity: 'low',
    affectedLoans: 7,
    avgDelay: '2.1 days',
    suggestedAction: 'Improve application form validation',
    loans: [
      { id: 'L-2024-066', borrowerName: 'Karen King', loanAmount: 295000, processor: 'Timothy Loss', missingItems: ['Property Address Incomplete'], daysDelayed: 2, lastContact: '1 day ago' },
      { id: 'L-2024-068', borrowerName: 'Steven Wright', loanAmount: 445000, processor: 'Sarah Mitchell', missingItems: ['Co-Borrower Information Missing'], daysDelayed: 3, lastContact: '2 days ago' },
      { id: 'L-2024-070', borrowerName: 'Donna Lopez', loanAmount: 380000, processor: 'Timothy Loss', missingItems: ['Employment History Gaps'], daysDelayed: 2, lastContact: 'Today' },
      { id: 'L-2024-072', borrowerName: 'Brian Hill', loanAmount: 520000, processor: 'Mike Johnson', missingItems: ['Asset Declaration Incomplete'], daysDelayed: 1, lastContact: 'Today' },
      { id: 'L-2024-074', borrowerName: 'Michelle Scott', loanAmount: 410000, processor: 'Sarah Mitchell', missingItems: ['Liability Disclosure Missing'], daysDelayed: 2, lastContact: '1 day ago' },
      { id: 'L-2024-076', borrowerName: 'Edward Green', loanAmount: 355000, processor: 'Timothy Loss', missingItems: ['Previous Address History'], daysDelayed: 3, lastContact: '2 days ago' },
      { id: 'L-2024-078', borrowerName: 'Carol Adams', loanAmount: 475000, processor: 'Mike Johnson', missingItems: ['Income Source Details'], daysDelayed: 2, lastContact: '1 day ago' }
    ]
  },
  '6': {
    id: 6,
    issue: 'Title Search Delays',
    stage: 'Underwriting',
    severity: 'low',
    affectedLoans: 3,
    avgDelay: '3.5 days',
    suggestedAction: 'Switch to faster title company',
    loans: [
      { id: 'L-2024-080', borrowerName: 'Ronald Baker', loanAmount: 565000, processor: 'Danielle Brooks', missingItems: ['Title Search In Progress'], daysDelayed: 4, lastContact: '2 days ago' },
      { id: 'L-2024-082', borrowerName: 'Helen Nelson', loanAmount: 425000, processor: 'Samuel Price', missingItems: ['Lien Release Pending'], daysDelayed: 3, lastContact: '1 day ago' },
      { id: 'L-2024-084', borrowerName: 'Kenneth Carter', loanAmount: 490000, processor: 'Patricia Donovan', missingItems: ['Chain of Title Verification'], daysDelayed: 3, lastContact: '2 days ago' }
    ]
  }
};

function BottleneckLoans() {
  const { bottleneckId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setTimeout(() => setLoading(false), 300);
  }, []);

  const data = bottleneckData[bottleneckId];

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const getSeverityClass = (severity) => {
    switch (severity) {
      case 'high': return 'severity-high';
      case 'medium': return 'severity-medium';
      case 'low': return 'severity-low';
      default: return '';
    }
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'high': return '🔴';
      case 'medium': return '🟡';
      case 'low': return '🟢';
      default: return '⚪';
    }
  };

  const handleLoanClick = (loan) => {
    // Navigate to loan detail page
    navigate(`/loans/${loan.id}`);
  };

  const handleCreateTask = (loan) => {
    toast.info(`Creating AI task for ${loan.processor} to follow up on ${loan.borrowerName}'s loan (${loan.id})`);
  };

  if (loading) {
    return (
      <div className="bottleneck-loans-page">
        <div className="loading-spinner">Loading bottleneck data...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bottleneck-loans-page">
        <div className="error-state">
          <h2>Bottleneck Not Found</h2>
          <p>The requested bottleneck was not found.</p>
          <button onClick={() => navigate('/efficiency')}>← Back to Pipeline Efficiency</button>
        </div>
      </div>
    );
  }

  // Group loans by processor
  const loansByProcessor = data.loans.reduce((acc, loan) => {
    if (!acc[loan.processor]) acc[loan.processor] = [];
    acc[loan.processor].push(loan);
    return acc;
  }, {});

  return (
    <div className="bottleneck-loans-page">
      {/* Header */}
      <div className="bottleneck-header-section">
        <div className="header-nav">
          <button className="btn-back" onClick={() => navigate('/efficiency')}>
            ← Back to Pipeline Efficiency
          </button>
        </div>

        <div className="bottleneck-header-content">
          <div className="bottleneck-title-section">
            <div className="bottleneck-badge-row">
              <span className={`severity-badge ${getSeverityClass(data.severity)}`}>
                {getSeverityIcon(data.severity)} {data.severity.toUpperCase()} SEVERITY
              </span>
              <span className="stage-badge">{data.stage}</span>
            </div>
            <h1>{data.issue}</h1>
            <p className="bottleneck-description">{data.suggestedAction}</p>
          </div>

          <div className="bottleneck-metrics">
            <div className="metric-box">
              <span className="metric-number">{data.affectedLoans}</span>
              <span className="metric-label">Affected Loans</span>
            </div>
            <div className="metric-box warning">
              <span className="metric-number">{data.avgDelay}</span>
              <span className="metric-label">Avg. Delay</span>
            </div>
          </div>
        </div>
      </div>

      {/* Affected Loans by Processor */}
      <div className="loans-by-processor">
        <h2>Affected Loans by Team Member</h2>
        <p className="section-description">Click any loan to view full details and take action</p>

        {Object.entries(loansByProcessor).map(([processor, loans]) => (
          <div key={processor} className="processor-group">
            <div className="processor-header">
              <h3>{processor}</h3>
              <span className="loan-count">{loans.length} loans</span>
            </div>

            <div className="loans-grid">
              {loans.map((loan) => (
                <div key={loan.id} className="loan-card" onClick={() => handleLoanClick(loan)}>
                  <div className="loan-card-header">
                    <div className="loan-info">
                      <span className="loan-number">{loan.id}</span>
                      <span className="borrower-name">{loan.borrowerName}</span>
                    </div>
                    <span className="loan-amount">{formatCurrency(loan.loanAmount)}</span>
                  </div>

                  <div className="missing-items">
                    <h4>Missing Items:</h4>
                    <ul>
                      {loan.missingItems.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="loan-card-footer">
                    <div className="delay-info">
                      <span className="delay-badge">{loan.daysDelayed} days delayed</span>
                      <span className="last-contact">Last contact: {loan.lastContact}</span>
                    </div>
                    <button
                      className="btn-create-task"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCreateTask(loan);
                      }}
                    >
                      Create Task
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Action Summary */}
      <div className="action-summary">
        <h2>Recommended Actions</h2>
        <div className="actions-grid">
          <div className="action-card">
            <div className="action-icon">📧</div>
            <h3>Bulk Reminder</h3>
            <p>Send automated reminder emails to all {data.affectedLoans} borrowers with missing documents</p>
            <button className="btn-action">Send Reminders</button>
          </div>

          <div className="action-card">
            <div className="action-icon">📋</div>
            <h3>Create Tasks</h3>
            <p>Generate follow-up tasks for each processor based on their assigned loans</p>
            <button className="btn-action">Create All Tasks</button>
          </div>

          <div className="action-card">
            <div className="action-icon">📊</div>
            <h3>Export Report</h3>
            <p>Download a detailed report of all affected loans for review</p>
            <button className="btn-action">Export CSV</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default BottleneckLoans;
