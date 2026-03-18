import React from 'react';

function TextCampaignPreview({ textData, onExecute, onEdit }) {
  const audience = textData?.audience || 'pre-approved leads';

  return (
    <div className="ai-message-content-new ai-special-content">
      I've prepared a text message for your {audience}. Here's the preview:

      <div className="ai-action-preview">
        <h3>Text Message Preview</h3>
        <div style={{ marginBottom: '12px' }}>
          <strong>To:</strong> 12 {audience}<br/>
          <strong>Type:</strong> SMS
        </div>

        <div className="ai-preview-content">
          <div style={{ background: '#e8f5e9', padding: '12px', borderRadius: '8px', marginBottom: '12px' }}>
            <strong style={{ color: '#2e7d32' }}>Message Preview:</strong>
          </div>
          <div style={{ background: '#f5f5f5', padding: '16px', borderRadius: '12px', border: '1px solid #e0e0e0' }}>
            Hi [First Name]!<br/><br/>
            Hope you're having a great week! Quick question - are you planning to check out any houses this weekend?<br/><br/>
            With your pre-approval in place, you're ready to make a strong offer when you find the right one. I'd love to help coordinate any showings.<br/><br/>
            Let me know if you'd like some neighborhood recommendations or want me to set up any tours!<br/><br/>
            - Tim
          </div>
        </div>

        <div className="ai-partner-list">
          <strong>Recipients Preview:</strong>
          <div className="ai-partner-item">
            <strong>Sarah Johnson</strong> - (555) 123-4567
          </div>
          <div className="ai-partner-item">
            <strong>Mike Chen</strong> - (555) 234-5678
          </div>
          <div className="ai-partner-item">
            <strong>Amanda Rodriguez</strong> - (555) 345-6789
          </div>
          <div className="ai-partner-item more">... and 9 more leads</div>
        </div>

        <div className="ai-note">
          Each message will be personalized with the lead's first name
        </div>

        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onEdit}>Edit Message</button>
          <button className="ai-btn ai-btn-approve" onClick={onExecute}>Send to 12 Leads</button>
        </div>
      </div>
    </div>
  );
}

export default TextCampaignPreview;
