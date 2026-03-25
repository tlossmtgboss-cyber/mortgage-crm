import React from 'react';

const CallIntelligenceButton = ({
  onClick,
  isRecording = false,
  isProcessing = false,
  artifactCount = 0,
  disabled = false
}) => {
  // Determine visual state
  const getState = () => {
    if (isRecording) return 'recording';
    if (isProcessing) return 'processing';
    if (artifactCount > 0) return 'complete';
    return 'idle';
  };

  const state = getState();

  const stateStyles = {
    idle: {
      background: 'linear-gradient(135deg, #1e3a5f, #2563eb)',
      boxShadow: '0 4px 15px rgba(37, 99, 235, 0.3)',
    },
    recording: {
      background: 'linear-gradient(135deg, #dc2626, #ef4444)',
      boxShadow: '0 4px 20px rgba(239, 68, 68, 0.5)',
      animation: 'ci-pulse 1.5s ease-in-out infinite',
    },
    processing: {
      background: 'linear-gradient(135deg, #d97706, #f59e0b)',
      boxShadow: '0 4px 15px rgba(245, 158, 11, 0.4)',
    },
    complete: {
      background: 'linear-gradient(135deg, #059669, #10b981)',
      boxShadow: '0 4px 15px rgba(16, 185, 129, 0.4)',
    },
  };

  // Brain + microphone SVG icon
  const CIIcon = () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      {state === 'recording' ? (
        // Recording: microphone icon
        <>
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" fill="white"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" stroke="white" strokeWidth="2" strokeLinecap="round"/>
          <line x1="12" y1="19" x2="12" y2="23" stroke="white" strokeWidth="2" strokeLinecap="round"/>
          <line x1="8" y1="23" x2="16" y2="23" stroke="white" strokeWidth="2" strokeLinecap="round"/>
        </>
      ) : (
        // Default: brain/analysis icon
        <>
          <path d="M12 2C8.13 2 5 5.13 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.87-3.13-7-7-7z" fill="white" opacity="0.9"/>
          <path d="M9 21v1c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9z" fill="white" opacity="0.7"/>
          <line x1="9" y1="18" x2="15" y2="18" stroke="white" strokeWidth="1" opacity="0.5"/>
        </>
      )}
    </svg>
  );

  return (
    <>
      <style>{`
        @keyframes ci-pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.9; }
        }
        @keyframes ci-spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
      <button
        onClick={onClick}
        disabled={disabled}
        role="button"
        aria-label={
          state === 'recording' ? 'Stop call intelligence recording' :
          state === 'processing' ? 'Processing call...' :
          state === 'complete' ? `View ${artifactCount} call intelligence results` :
          'Start call intelligence'
        }
        style={{
          position: 'relative',
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          border: 'none',
          cursor: disabled ? 'not-allowed' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.3s ease',
          opacity: disabled ? 0.5 : 1,
          ...stateStyles[state],
        }}
      >
        {isProcessing ? (
          <div style={{
            width: '24px',
            height: '24px',
            border: '3px solid rgba(255,255,255,0.3)',
            borderTopColor: 'white',
            borderRadius: '50%',
            animation: 'ci-spin 1s linear infinite',
          }} />
        ) : (
          <CIIcon />
        )}

        {/* Artifact count badge */}
        {artifactCount > 0 && !isRecording && !isProcessing && (
          <span style={{
            position: 'absolute',
            top: '-4px',
            right: '-4px',
            background: '#ef4444',
            color: 'white',
            borderRadius: '50%',
            width: '22px',
            height: '22px',
            fontSize: '12px',
            fontWeight: '700',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '2px solid #0a1628',
          }}>
            {artifactCount > 9 ? '9+' : artifactCount}
          </span>
        )}

        {/* Recording indicator dot */}
        {isRecording && (
          <span style={{
            position: 'absolute',
            top: '-2px',
            right: '-2px',
            width: '12px',
            height: '12px',
            background: '#ff0000',
            borderRadius: '50%',
            border: '2px solid #0a1628',
            animation: 'ci-pulse 1s ease-in-out infinite',
          }} />
        )}
      </button>
    </>
  );
};

export default CallIntelligenceButton;
