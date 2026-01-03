import React from 'react';
import './MarketingSettings.css';

function VoicemailSettings() {
  return (
    <div className="marketing-settings-page">
      <div className="settings-header">
        <h2>Voicemail Drops</h2>
        <p>Create and manage ringless voicemail campaigns</p>
      </div>

      <div className="empty-state">
        <div className="icon">🎙️</div>
        <h4>Voicemail Templates Coming Soon</h4>
        <p>
          Record voicemail templates for ringless voicemail drops and automated outreach
        </p>
        <button className="btn-add">
          + Record Voicemail
        </button>
      </div>
    </div>
  );
}

export default VoicemailSettings;
