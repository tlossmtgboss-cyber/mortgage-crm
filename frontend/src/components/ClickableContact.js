import React, { useState } from 'react';
import { getAuthHeaders } from '../utils/auth';
import { toast } from '../utils/toast';
import './ClickableContact.css';

const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Clickable email link
export const ClickableEmail = ({ email, className = '' }) => {
  if (!email) return <span className="no-value">N/A</span>;

  return (
    <a
      href={`mailto:${email}`}
      className={`clickable-email ${className}`}
      onClick={(e) => e.stopPropagation()}
    >
      {email}
    </a>
  );
};

// Clickable phone link — calls via backend dialer API
export const ClickablePhone = ({
  phone,
  className = '',
  showActions = false,
  onSMSClick = null,
  contactName = '',
  leadId = null,
  loanId = null,
}) => {
  const [callState, setCallState] = useState('idle'); // idle | calling | success | error

  if (!phone) return <span className="no-value">N/A</span>;

  // Clean phone number (remove formatting)
  const cleanPhone = phone.replace(/[^0-9+]/g, '');

  const handleClickToDial = async (e) => {
    e.preventDefault();
    e.stopPropagation();

    if (callState === 'calling') return;

    setCallState('calling');

    const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
    const payload = {
      phone_number: dialNumber,
      contact_name: contactName || '',
    };
    if (leadId) payload.lead_id = leadId;
    if (loanId) payload.loan_id = loanId;

    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/click-to-dial`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok || data.success === false) {
        throw new Error(data.error || data.detail || `Call failed (${response.status})`);
      }

      const debugTo = data?.debug?.to || '';
      setCallState('success');
      toast.success(debugTo ? `Calling ${debugTo}` : 'Call initiated');
      setTimeout(() => setCallState('idle'), 3000);
    } catch (err) {
      setCallState('error');
      const message = err.message || 'Failed to initiate call';
      toast.error(message);
      setTimeout(() => setCallState('idle'), 3000);
    }
  };

  const isCalling = callState === 'calling';
  const isSuccess = callState === 'success';

  const getButtonTitle = () => {
    if (isCalling) return 'Calling...';
    if (isSuccess) return 'Call initiated';
    return 'Click to call';
  };

  const getButtonContent = () => {
    if (isCalling) return '...';
    if (isSuccess) return '✓';
    return '📞';
  };

  if (showActions) {
    return (
      <div className="phone-with-actions" onClick={(e) => e.stopPropagation()}>
        <span className="phone-number">{phone}</span>
        <div className="phone-action-buttons">
          <button
            className={`phone-action-btn call-btn ${isSuccess ? 'success' : ''} ${isCalling ? 'calling' : ''}`}
            title={getButtonTitle()}
            onClick={handleClickToDial}
            disabled={isCalling}
          >
            {getButtonContent()}
          </button>
          {onSMSClick ? (
            <button
              className="phone-action-btn sms-btn"
              title="Send SMS in CRM"
              onClick={(e) => {
                e.stopPropagation();
                onSMSClick();
              }}
            >
              💬
            </button>
          ) : (
            <a
              href={`sms:${cleanPhone}`}
              className="phone-action-btn sms-btn"
              title="Send SMS"
              onClick={(e) => e.stopPropagation()}
            >
              💬
            </a>
          )}
        </div>
      </div>
    );
  }

  return (
    <button
      className={`clickable-phone ${className} ${isSuccess ? 'success' : ''} ${isCalling ? 'calling' : ''}`}
      onClick={handleClickToDial}
      disabled={isCalling}
      title={getButtonTitle()}
    >
      {isCalling ? '... ' + phone : isSuccess ? '✓ ' + phone : phone}
    </button>
  );
};

// Format phone number for display (optional utility)
export const formatPhoneNumber = (phone) => {
  if (!phone) return '';

  // Remove all non-numeric characters
  const cleaned = phone.replace(/\D/g, '');

  // Format as (XXX) XXX-XXXX for 10-digit US numbers
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }

  // Return original if not a standard 10-digit number
  return phone;
};
