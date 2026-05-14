import React from 'react';
import Icon from './Icon';

/**
 * Micro-win toast notification shown on stage completion.
 * Shared between Purchase and Refinance applications.
 */
const MicroWinToast = ({ show, message, iconName = 'check' }) => {
  if (!show) return null;

  return (
    <div className="micro-win-toast">
      <span className="micro-win-icon"><Icon name={iconName} size={24} /></span>
      <span className="micro-win-message">{message}</span>
    </div>
  );
};

export default MicroWinToast;
