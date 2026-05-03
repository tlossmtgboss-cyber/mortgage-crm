import React, { useState } from 'react';
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

// Clickable phone link — opens Teams for click-to-dial
export const ClickablePhone = ({
  phone,
  className = '',
  showActions = false,
  onSMSClick = null,
  contactName = '',
  leadId = null,
  loanId = null
}) => {
  const [callSuccess, setCallSuccess] = useState(false);

  if (!phone) return <span className="no-value">N/A</span>;

  // Clean phone number (remove formatting)
  const cleanPhone = phone.replace(/[^0-9+]/g, '');

  const handleClickToDial = (e) => {
    e.preventDefault();
    e.stopPropagation();

    const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
    window.open(`https://teams.microsoft.com/l/call/0/0?users=4:${encodeURIComponent(dialNumber)}`, '_blank');
    setCallSuccess(true);
    setTimeout(() => setCallSuccess(false), 3000);
  };

  if (showActions) {
    return (
      <div className="phone-with-actions" onClick={(e) => e.stopPropagation()}>
        <span className="phone-number">{phone}</span>
        <div className="phone-action-buttons">
          <button
            className={`phone-action-btn call-btn ${callSuccess ? 'success' : ''}`}
            title={callSuccess ? 'Opening Teams...' : 'Call via Teams'}
            onClick={handleClickToDial}
          >
            {callSuccess ? '✓' : '📞'}
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
      className={`clickable-phone ${className} ${callSuccess ? 'success' : ''}`}
      onClick={handleClickToDial}
      title={callSuccess ? 'Opening Teams...' : 'Call via Teams'}
    >
      {callSuccess ? '✓ ' + phone : phone}
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
