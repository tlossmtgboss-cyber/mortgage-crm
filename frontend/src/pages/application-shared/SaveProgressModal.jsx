import React from 'react';
import Icon from './Icon';

/**
 * Modal for saving application progress via email.
 * Shared between Purchase and Refinance applications.
 */
const SaveProgressModal = ({
  showSaveModal,
  setShowSaveModal,
  saveEmail,
  setSaveEmail,
  userAccount,
  setUserAccount,
  lastSavedAt,
  onSaveEmail, // Optional handler for email save (refinance uses handleSaveProgressEmail)
}) => {
  if (!showSaveModal) return null;

  const handleClose = () => {
    setShowSaveModal(false);
    if (saveEmail && setUserAccount) {
      setUserAccount(prev => ({ ...prev, email: saveEmail }));
    }
  };

  return (
    <div className="modal-overlay" style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div className="save-modal" style={{
        background: 'white',
        borderRadius: '16px',
        padding: '32px',
        maxWidth: '420px',
        width: '90%',
        boxShadow: '0 20px 40px rgba(0, 0, 0, 0.2)'
      }}>
        <h3 style={{ marginTop: 0, marginBottom: '8px', fontSize: '20px', fontWeight: '600', color: '#1a365d' }}>
          Save Your Progress
        </h3>
        <p style={{ color: '#6b7280', marginBottom: '20px', fontSize: '14px' }}>
          Your application is automatically saved to this browser. Enter your email to save to the cloud and access from any device.
        </p>

        {lastSavedAt && (
          <p style={{
            background: '#f0fdf4',
            padding: '10px 14px',
            borderRadius: '8px',
            color: '#166534',
            fontSize: '13px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <Icon name="check" size={16} />
            Auto-saved to browser {lastSavedAt.toLocaleTimeString()}
          </p>
        )}

        <div className="form-group" style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', marginBottom: '6px', fontWeight: 500, fontSize: '14px' }}>
            Email Address (optional)
          </label>
          <input
            type="email"
            value={saveEmail || userAccount?.email || ''}
            onChange={(e) => setSaveEmail(e.target.value)}
            placeholder="you@example.com"
            className="fun-input"
            style={{ width: '100%', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '15px' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={onSaveEmail ? () => { onSaveEmail(); } : handleClose}
            disabled={onSaveEmail && (!saveEmail || !saveEmail.includes('@'))}
            style={{
              flex: 1,
              padding: '12px',
              background: '#0d9488',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontWeight: 500,
              cursor: 'pointer'
            }}
          >
            {saveEmail ? 'Save & Send Magic Link' : 'Got it!'}
          </button>
          <button
            onClick={() => setShowSaveModal(false)}
            style={{
              padding: '12px 20px',
              background: 'transparent',
              color: '#6b7280',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              fontWeight: 500,
              cursor: 'pointer'
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default SaveProgressModal;
