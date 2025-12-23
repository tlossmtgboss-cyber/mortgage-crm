import React, { useState } from 'react';
import { getAuthHeaders } from '../utils/auth';
import './ClickToDialButton.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

const ClickToDialButton = ({
  phoneNumber,
  contactName,
  leadId = null,
  loanId = null,
  taskId = null,
  size = 'medium', // small, medium, large
  showLabel = true,
  onCallStarted = null,
  onCallEnded = null,
  onError = null
}) => {
  const [calling, setCalling] = useState(false);
  const [callSid, setCallSid] = useState(null);

  const initiateCall = async () => {
    if (!phoneNumber) {
      if (onError) onError('No phone number provided');
      return;
    }

    setCalling(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/click-to-dial`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          phone_number: phoneNumber,
          contact_name: contactName || 'Unknown',
          lead_id: leadId,
          loan_id: loanId,
          task_id: taskId
        })
      });

      if (response.ok) {
        const data = await response.json();
        setCallSid(data.call_sid);
        if (onCallStarted) onCallStarted(data);
      } else {
        const error = await response.json();
        setCalling(false);
        if (onError) onError(error.detail || 'Failed to initiate call');
      }
    } catch (err) {
      setCalling(false);
      if (onError) onError('Error initiating call: ' + err.message);
    }
  };

  const endCall = () => {
    // In a real implementation, this would end the call via API
    setCalling(false);
    setCallSid(null);
    if (onCallEnded) onCallEnded();
  };

  if (!phoneNumber) {
    return null;
  }

  return (
    <button
      className={`click-to-dial-btn ${size} ${calling ? 'calling' : ''}`}
      onClick={calling ? endCall : initiateCall}
      title={calling ? 'End call' : `Call ${phoneNumber}`}
    >
      <span className="dial-icon">
        {calling ? '📵' : '📞'}
      </span>
      {showLabel && (
        <span className="dial-label">
          {calling ? 'End Call' : 'Call'}
        </span>
      )}
      {calling && <span className="calling-indicator" />}
    </button>
  );
};

export default ClickToDialButton;
