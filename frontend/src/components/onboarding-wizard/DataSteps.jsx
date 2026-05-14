import React from 'react';

// STEP 6: Data Preview
export const DataPreviewStep = ({ previewEmails, handlePreviewEmailUpload }) => {
  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🔍</div>
        <h2>Data Parsing Demo</h2>
        <p className="step-description">
          Upload up to 3 sample emails to see how our AI parses and extracts lead information. This preview matches what you'll see in the reconciliation page.
        </p>
      </div>

      <div className="data-preview-container">
        <div className="upload-section">
          <h3>Upload Sample Emails</h3>
          <label className="file-upload-label">
            <input
              type="file"
              accept=".eml,.msg,.txt"
              multiple
              className="file-input"
              onChange={handlePreviewEmailUpload}
              style={{ display: 'none' }}
            />
            <div className="upload-button">
              📧 Choose Email Files
            </div>
          </label>
          <p className="upload-hint">Upload up to 3 email files (.eml, .msg, or .txt)</p>
          {previewEmails.length > 0 && (
            <p className="upload-success">✓ {previewEmails.length} email(s) uploaded successfully</p>
          )}
        </div>

        <div className="preview-section">
          <h3>AI Parsing Preview</h3>
          {previewEmails.length > 0 ? (
            <div className="parsed-emails-list">
              {previewEmails.map((email) => (
                <div key={email.id} className="parsed-email-card">
                  <div className="email-header">
                    <span className="email-icon">📧</span>
                    <div className="email-meta">
                      <strong>{email.fileName}</strong>
                      <p className="email-subject">Subject: {email.subject}</p>
                      <p className="email-sender">From: {email.sender}</p>
                    </div>
                  </div>
                  <div className="extracted-data">
                    <h4>Extracted Information:</h4>
                    <div className="data-grid">
                      <div className="data-item">
                        <span className="data-label">Lead Name:</span>
                        <span className="data-value">{email.extractedData.leadName}</span>
                      </div>
                      <div className="data-item">
                        <span className="data-label">Phone:</span>
                        <span className="data-value">{email.extractedData.phone}</span>
                      </div>
                      <div className="data-item">
                        <span className="data-label">Loan Amount:</span>
                        <span className="data-value">{email.extractedData.loanAmount}</span>
                      </div>
                      <div className="data-item">
                        <span className="data-label">Milestone:</span>
                        <span className="data-value milestone-badge">{email.extractedData.milestone}</span>
                      </div>
                      <div className="data-item">
                        <span className="data-label">AI Confidence:</span>
                        <span className="data-value confidence-score">{email.extractedData.confidence}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="preview-placeholder">
              <p>📂 Upload emails to see the AI parsing results here</p>
              <p className="hint-text">The AI will automatically extract lead information, loan amounts, milestones, and more!</p>
            </div>
          )}
        </div>
      </div>

      <div className="preview-note">
        <p><strong>Note:</strong> This is a preview of AI parsing. You can proceed to the next step whether or not you upload emails here. This step is optional.</p>
      </div>
    </div>
  );
};

// STEP 7: Data Upload
export const DataUploadStep = () => {
  const downloadTemplate = (type) => {
    let csvContent = '';
    let filename = '';

    switch(type) {
      case 'leads':
        csvContent = 'Name,Email,Phone,Source,Status,Created Date\nJohn Smith,john@example.com,(555) 123-4567,Website,New,2024-01-15\n';
        filename = 'leads_template.csv';
        break;
      case 'loans':
        csvContent = 'Borrower Name,Loan Number,Loan Amount,Status,Loan Officer,Application Date\nJane Doe,LN-12345,$350000,In Process,John Smith,2024-01-10\n';
        filename = 'active_loans_template.csv';
        break;
      case 'mum':
        csvContent = 'Client Name,Email,Phone,Loan Number,Close Date,Loan Amount,Interest Rate\nBob Johnson,bob@example.com,(555) 987-6543,LN-98765,2023-06-15,$400000,6.5%\n';
        filename = 'closed_clients_template.csv';
        break;
      default:
        return;
    }

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">📊</div>
        <h2>Data Upload Templates</h2>
        <p className="step-description">
          Download the templates, fill them with your data, and upload them back to import your leads, active loans, and closed clients.
        </p>
      </div>

      <div className="data-upload-container">
        <div className="template-card">
          <h3>1. Leads</h3>
          <p>Import your current leads and prospects</p>
          <button className="btn-secondary" onClick={() => downloadTemplate('leads')}>
            📥 Download Template
          </button>
          <label className="btn-primary">
            📤 Upload Data
            <input type="file" accept=".csv,.xlsx" style={{ display: 'none' }} />
          </label>
        </div>

        <div className="template-card">
          <h3>2. Active Loans</h3>
          <p>Import loans currently in your pipeline</p>
          <button className="btn-secondary" onClick={() => downloadTemplate('loans')}>
            📥 Download Template
          </button>
          <label className="btn-primary">
            📤 Upload Data
            <input type="file" accept=".csv,.xlsx" style={{ display: 'none' }} />
          </label>
        </div>

        <div className="template-card">
          <h3>3. Closed Clients (MUM)</h3>
          <p>Import your closed clients for MUM tracking</p>
          <button className="btn-secondary" onClick={() => downloadTemplate('mum')}>
            📥 Download Template
          </button>
          <label className="btn-primary">
            📤 Upload Data
            <input type="file" accept=".csv,.xlsx" style={{ display: 'none' }} />
          </label>
        </div>
      </div>
    </div>
  );
};

// STEP 8: Review Data
export const ReviewDataStep = () => {
  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">📋</div>
        <h2>Review Data to Import</h2>
        <p className="step-description">
          Review all the data you've uploaded before we import it into your CRM.
        </p>
      </div>

      <div className="data-review-container">
        <div className="review-section">
          <h3>Leads to Import</h3>
          <p className="count">0 leads ready for import</p>
        </div>

        <div className="review-section">
          <h3>Active Loans to Import</h3>
          <p className="count">0 active loans ready for import</p>
        </div>

        <div className="review-section">
          <h3>Closed Clients to Import</h3>
          <p className="count">0 closed clients ready for import</p>
        </div>

        <div className="approval-section">
          <label className="checkbox-label">
            <input type="checkbox" />
            <span>I have reviewed the data and approve the import</span>
          </label>
        </div>
      </div>
    </div>
  );
};
