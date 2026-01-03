import React from 'react';
import './MarketingSettings.css';

function TextMarketingSettings() {
  return (
    <div className="marketing-settings-page">
      <div className="settings-header">
        <h2>SMS Templates</h2>
        <p>Create and manage text message templates</p>
      </div>

      <div className="empty-state">
        <div className="icon">📱</div>
        <h4>SMS Templates Coming Soon</h4>
        <p>
          Create text message templates for quick client communication and marketing blasts
        </p>
        <button className="btn-add">
          + Create SMS Template
        </button>
      </div>
    </div>
  );
}

export default TextMarketingSettings;
