import React, { useState } from 'react';
import html2canvas from 'html2canvas';

function ErrorTestButton() {
  const [shouldError, setShouldError] = useState(false);

  const triggerError = async () => {
    try {
      // First, capture the screenshot of the current screen
      console.log('Capturing screenshot before error...');
      const canvas = await html2canvas(document.body, {
        allowTaint: true,
        useCORS: true,
        logging: false,
        width: window.innerWidth,
        height: window.innerHeight
      });

      const screenshot = canvas.toDataURL('image/png');

      // Store the screenshot so ErrorBoundary can access it
      window.__preErrorScreenshot = screenshot;
      console.log('Screenshot captured and stored!');

      // Small delay to ensure screenshot is saved
      setTimeout(() => {
        // Now trigger the error
        setShouldError(true);
      }, 100);
    } catch (error) {
      console.error('Failed to capture screenshot:', error);
      // Still trigger error even if screenshot fails
      setShouldError(true);
    }
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
