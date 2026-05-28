import React from 'react';

/**
 * Email tab — email history and compose button.
 */
function EmailTab({ loan, formData, emailHistory, setShowEmailComposer, setSelectedEmail }) {
  return (
    <div className="info-section">
      <h2>Email</h2>
      <div className="email-content">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <p className="section-description" style={{ color: '#666', margin: 0 }}>
            View all email communications with this borrower.
          </p>
          <button
            className="btn-primary"
            style={{ padding: '8px 16px', fontSize: '14px' }}
            onClick={() => (loan?.borrower_email || formData?.borrower_email) && window.open(`mailto:${loan?.borrower_email || formData?.borrower_email}`, '_blank')}
            disabled={!loan?.borrower_email && !formData?.borrower_email}
          >
            + Compose Email
          </button>
        </div>

        {/* Email History */}
        <div className="email-history-section">
          <h3>Email History</h3>
          <div className="email-list">
            {emailHistory.length > 0 ? (
              emailHistory.map((email) => (
                <div key={email.id} className="email-item">
                  <div className="email-header">
                    <span className="email-subject">
                      {email.subject || 'No subject'}
                    </span>
                    <span className="email-date">
                      {new Date(email.sentAt).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="email-preview">
                    {(email.body || '').substring(0, 100)}...
                  </div>
                </div>
              ))
            ) : (
              <div className="empty-state">No emails yet</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default EmailTab;
