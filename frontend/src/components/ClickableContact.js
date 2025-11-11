import React from 'react';
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

// Clickable phone link
export const ClickablePhone = ({ phone, className = '', showActions = false }) => {
  if (!phone) return <span className="no-value">N/A</span>;

  // Clean phone number for tel: link (remove formatting)
  const cleanPhone = phone.replace(/[^0-9+]/g, '');

  if (showActions) {
    return (
      <div className="phone-with-actions" onClick={(e) => e.stopPropagation()}>
        <span className="phone-number">{phone}</span>
        <div className="phone-action-buttons">
          <a
            href={`tel:${cleanPhone}`}
            className="phone-action-btn call-btn"
            title="Call"
            onClick={(e) => e.stopPropagation()}
          >
            📞
          </a>
          <a
            href={`sms:${cleanPhone}`}
            className="phone-action-btn sms-btn"
            title="Send SMS"
            onClick={(e) => e.stopPropagation()}
          >
            💬
          </a>
        </div>
      </div>
    );
  }

  return (
    <a
      href={`tel:${cleanPhone}`}
      className={`clickable-phone ${className}`}
      onClick={(e) => e.stopPropagation()}
      title="Click to call"
    >
      {phone}
    </a>
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
