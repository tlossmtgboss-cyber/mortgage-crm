import React from 'react';

function PipelineReportPreview({ preview, onExecute, onEdit }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      I've generated your pipeline report for December 2024 closings.

      <div className="ai-action-preview">
        <h3>Pipeline Report - December 2024 Closings</h3>

        <div className="ai-daily-summary">
          <div className="ai-summary-item">
            <div className="ai-summary-number">18</div>
            <div className="ai-summary-label">Total Deals</div>
          </div>
          <div className="ai-summary-item">
            <div className="ai-summary-number">$6.2M</div>
            <div className="ai-summary-label">Total Volume</div>
          </div>
          <div className="ai-summary-item">
            <div className="ai-summary-number">12</div>
            <div className="ai-summary-label">Clear to Close</div>
          </div>
          <div className="ai-summary-item">
            <div className="ai-summary-number">2</div>
            <div className="ai-summary-label">At Risk</div>
          </div>
        </div>

        <div className="ai-report-breakdown">
          <strong>Loan Type Breakdown:</strong>
          <ul>
            <li>Conventional: 8 deals</li>
            <li>FHA: 5 deals</li>
            <li>VA: 3 deals</li>
            <li>Jumbo: 2 deals</li>
          </ul>
        </div>

        <div className="ai-send-to">
          <strong>Send To:</strong>
          <ul>
            <li>Your team (5 members)</li>
            <li>Format: PDF + Excel</li>
            <li>Include: Deal-by-deal breakdown, commission projections, and risk analysis</li>
          </ul>
        </div>

        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onEdit}>Customize Report</button>
          <button className="ai-btn ai-btn-approve" onClick={onExecute}>Generate & Send</button>
        </div>
      </div>
    </div>
  );
}

export default PipelineReportPreview;
