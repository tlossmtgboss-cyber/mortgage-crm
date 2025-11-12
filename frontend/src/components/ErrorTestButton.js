import React, { useState } from 'react';

function ErrorTestButton() {
  const [shouldError, setShouldError] = useState(false);

  const triggerError = () => {
    setShouldError(true);
  };

  // This will throw an error when shouldError is true
  if (shouldError) {
    throw new Error('TEST ERROR: This is a simulated error to test the AI error handler. Click the "Auto-Fix with AI" button to see the AI analysis.');
  }

  return (
    <div style={{
      position: 'fixed',
      bottom: '20px',
      right: '20px',
      zIndex: 9999,
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      padding: '15px 25px',
      borderRadius: '8px',
      boxShadow: '0 4px 12px rgba(102, 126, 234, 0.4)',
      cursor: 'pointer'
    }}
    onClick={triggerError}
    title="Click to test the AI error handler"
    >
      <span style={{
        color: 'white',
        fontWeight: '600',
        fontSize: '14px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px'
      }}>
        🧪 Test Error Handler
      </span>
    </div>
  );
}

export default ErrorTestButton;
