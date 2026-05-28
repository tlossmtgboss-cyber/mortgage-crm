import React from 'react';

/**
 * Marketing tab — campaigns, drip sequences, and marketing history.
 */
function MarketingTab() {
  return (
    <div className="info-section">
      <h2>Marketing</h2>
      <div className="marketing-content">
        <p className="section-description" style={{ color: '#666', marginBottom: '20px' }}>
          View and manage marketing campaigns, drip sequences, and promotional content for this borrower.
        </p>

        <div className="marketing-campaigns" style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0 }}>Active Campaigns</h3>
            <button className="btn-primary" style={{ padding: '8px 16px', fontSize: '14px' }}>
              + Add to Campaign
            </button>
          </div>
          <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px', textAlign: 'center', color: '#666' }}>
            No active campaigns. Add this borrower to a marketing campaign to start automated outreach.
          </div>
        </div>

        <div className="drip-sequences" style={{ marginBottom: '24px' }}>
          <h3 style={{ marginBottom: '16px' }}>Drip Sequences</h3>
          <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px', textAlign: 'center', color: '#666' }}>
            No drip sequences assigned. Set up automated follow-up sequences in Settings.
          </div>
        </div>

        <div className="marketing-history">
          <h3 style={{ marginBottom: '16px' }}>Marketing History</h3>
          <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '20px', textAlign: 'center', color: '#666' }}>
            No marketing activities recorded yet.
          </div>
        </div>
      </div>
    </div>
  );
}

export default MarketingTab;
