import React, { useState } from 'react';
import { dialerAPI } from '../services/api';
import './ClickableContact.css';

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

// Clickable phone link with Telnyx click-to-dial
export const ClickablePhone = ({
  phone,
  className = '',
  showActions = false,
  onSMSClick = null,
  contactName = '',
  leadId = null,
  loanId = null
}) => {
  const [calling, setCalling] = useState(false);
  const [callError, setCallError] = useState(null);
  const [callSuccess, setCallSuccess] = useState(false);

  if (!phone) return <span className="no-value">N/A</span>;

  // Clean phone number (remove formatting)
  const cleanPhone = phone.replace(/[^0-9+]/g, '');

  const handleClickToDial = async (e) => {
    e.preventDefault();
    e.stopPropagation();

    if (calling) return;

    setCalling(true);
    setCallError(null);
    setCallSuccess(false);

    try {
      const response = await dialerAPI.clickToDial({
        phone_number: cleanPhone,
        contact_name: contactName || '',
        lead_id: leadId,
        loan_id: loanId
      });

      if (response.success) {
        setCallSuccess(true);
        // Reset success state after 3 seconds
        setTimeout(() => setCallSuccess(false), 3000);
      } else {
        setCallError(response.error || 'Failed to initiate call');
        setTimeout(() => setCallError(null), 5000);
      }
    } catch (error) {
      console.error('Click-to-dial error:', error);
      setCallError(error.response?.data?.detail || 'Failed to connect call');
      setTimeout(() => setCallError(null), 5000);
    } finally {
      setCalling(false);
    }
  };

  if (showActions) {
    return (
      <div className="phone-with-actions" onClick={(e) => e.stopPropagation()}>
        <span className="phone-number">{phone}</span>
        <div className="phone-action-buttons">
          <button
            className={`phone-action-btn call-btn ${calling ? 'calling' : ''} ${callSuccess ? 'success' : ''} ${callError ? 'error' : ''}`}
            title={calling ? 'Calling...' : callSuccess ? 'Call initiated!' : callError || 'Click to call'}
            onClick={handleClickToDial}
            disabled={calling}
          >
            {calling ? '📱' : callSuccess ? '✓' : '📞'}
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
        {callError && <span className="call-error-tooltip">{callError}</span>}
      </div>
    );
  }

  return (
    <button
      className={`clickable-phone ${className} ${calling ? 'calling' : ''} ${callSuccess ? 'success' : ''}`}
      onClick={handleClickToDial}
      disabled={calling}
      title={calling ? 'Calling your phone...' : callSuccess ? 'Call initiated!' : 'Click to call'}
    >
      {calling ? '📱 Calling...' : callSuccess ? '✓ ' + phone : phone}
      {callError && <span className="call-error-inline"> - {callError}</span>}
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
