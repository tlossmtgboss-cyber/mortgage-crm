import React from 'react';

function LeadPreviewComponent({ leadData, onConfirm, onCancel }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      I found the following lead information from the screenshot:

      <div className="ai-action-preview">
        <h3>Lead Information</h3>
        <div className="ai-lead-preview-data">
          {leadData.first_name && (
            <div className="ai-lead-field">
              <strong>First Name:</strong> {leadData.first_name}
            </div>
          )}
          {leadData.last_name && (
            <div className="ai-lead-field">
              <strong>Last Name:</strong> {leadData.last_name}
            </div>
          )}
          {leadData.email && (
            <div className="ai-lead-field">
              <strong>Email:</strong> {leadData.email}
            </div>
          )}
          {leadData.phone && (
            <div className="ai-lead-field">
              <strong>Phone:</strong> {leadData.phone}
            </div>
          )}
          {leadData.referral_source && (
            <div className="ai-lead-field">
              <strong>Referral Source:</strong> {leadData.referral_source}
            </div>
          )}
          {leadData.property_address && (
            <div className="ai-lead-field">
              <strong>Property Address:</strong> {leadData.property_address}
            </div>
          )}
          {leadData.loan_type && (
            <div className="ai-lead-field">
              <strong>Loan Type:</strong> {leadData.loan_type}
            </div>
          )}
          {leadData.notes && (
            <div className="ai-lead-field">
              <strong>Notes:</strong> {leadData.notes}
            </div>
          )}
        </div>

        <div className="ai-note">
          This lead will be created in the <strong>"Attempted Contact"</strong> stage
        </div>

        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onCancel}>Cancel</button>
          <button className="ai-btn ai-btn-approve" onClick={onConfirm}>Create Lead</button>
        </div>
      </div>
    </div>
  );
}

export default LeadPreviewComponent;
