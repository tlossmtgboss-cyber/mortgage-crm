import React, { useState } from 'react';
import './ClickToDialButton.css';

const ClickToDialButton = ({
  phoneNumber,
  size = 'medium',
  showLabel = true,
}) => {
  const [called, setCalled] = useState(false);

  const initiateCall = () => {
    if (!phoneNumber) return;

    const cleanPhone = phoneNumber.replace(/[^\d+]/g, '');
    const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
    window.open(`https://teams.microsoft.com/l/call/0/0?users=4:${encodeURIComponent(dialNumber)}`, '_blank');
    setCalled(true);
    setTimeout(() => setCalled(false), 3000);
  };

  if (!phoneNumber) {
    return null;
  }

  return (
    <button
      className={`click-to-dial-btn ${size} ${called ? 'success' : ''}`}
      onClick={initiateCall}
      title={called ? 'Opening Teams...' : `Call ${phoneNumber}`}
    >
      <span className="dial-icon">
        {called ? '✓' : '📞'}
      </span>
      {showLabel && (
        <span className="dial-label">
          {called ? 'Opening...' : 'Call'}
        </span>
      )}
    </button>
  );
};

export default ClickToDialButton;
