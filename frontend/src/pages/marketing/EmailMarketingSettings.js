import React from 'react';
import './MarketingSettings.css';

function EmailMarketingSettings() {
  return (
    <div className="marketing-settings-page">
      <div className="settings-header">
        <h2>Email Templates</h2>
        <p>Create and manage email marketing templates</p>
      </div>

      <div className="empty-state">
        <div className="icon">📧</div>
        <h4>Email Templates Coming Soon</h4>
        <p>
          Create email templates for drip campaigns, newsletters, and automated follow-ups
        </p>
        <button className="btn-add">
          + Create Email Template
        </button>
      </div>
    </div>
  );
}

export default EmailMarketingSettings;
